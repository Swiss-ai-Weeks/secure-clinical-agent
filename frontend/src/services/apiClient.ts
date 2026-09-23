import type {
  Appointment,
  AuditRow,
  ChatResponse,
  ChatSandboxStatus,
  Consent,
  IdentityBanner,
  ImagingResponse,
  LoginOut,
  Me,
  MediaFetchOut,
  MediaSignOut,
  NotesResponse,
  ReprocessOut,
  Persona,
  QueryResponse,
  Slot
} from '../types/api';
import { DEMO_PATIENT_KEYS } from '../types/api';
import type { AiAnswer, AskPatient360Request, FollowUp, HomeDashboard, Patient, PatientSummary, TimelineEvent } from '../types/patient360';
import { activityFromAudit, attachEncounters, deriveAttention, deriveBriefing, deriveFollowUps, filterPatients } from './dashboard';
import { ApiError, api } from './http';
import { composePatient, composeTimeline, kitchenCardFromDiet, sessionCanOpenSignedFiles, summariesFromKeys } from './patientRecord';
import { chartQueryDatasets, workspaceFor } from './workspace';

async function ignoreMissing<T>(work: () => Promise<T>): Promise<T | null> {
  try {
    return await work();
  } catch (error) {
    if (error instanceof ApiError && (error.notFound || error.status === 401 || error.status === 503)) return null;
    throw error;
  }
}

export const apiClient = {
  async login(login: string, opts: { on_duty?: boolean; auth_level?: number } = {}): Promise<LoginOut> {
    return api('/auth/dev-login', { method: 'POST', body: JSON.stringify({ login, on_duty: opts.on_duty ?? true, auth_level: opts.auth_level ?? 2 }) });
  },

  async logout(): Promise<void> {
    await api('/auth/logout', { method: 'POST' });
  },

  async getMe(): Promise<Me> {
    return api('/me');
  },

  async getPersonas(): Promise<Persona[]> {
    return api('/auth/dev-personas');
  },

  async query(dataset: string, body: { patient_key?: string; filters?: Record<string, unknown>; aggregate?: { group_by: string[]; project_id?: string } }): Promise<QueryResponse> {
    return api('/tools/query', { method: 'POST', body: JSON.stringify({ dataset, ...body }) });
  },

  async getIdentity(patientKey: string): Promise<IdentityBanner> {
    return api(`/patients/${patientKey}/identity`);
  },

  async listConsents(patientKey: string): Promise<{ patient_key: string; consents: Consent[]; audit_id: string }> {
    return api(`/consents?patient=${encodeURIComponent(patientKey)}`);
  },

  async revokeConsent(consentId: string): Promise<{ consent_id: string; revoked_at: string; tuple_removed: boolean }> {
    return api(`/consents/${consentId}/revoke`, { method: 'POST' });
  },

  async grantConsent(body: { patient_key: string; grantee_user_id: string; relation: string; expiry?: string; justification?: string }): Promise<Consent> {
    return api('/consents', { method: 'POST', body: JSON.stringify(body) });
  },

  async breakGlass(patientKey: string, justification: string): Promise<{ identity: IdentityBanner | null; expiry: string; compliance_flag: boolean }> {
    return api('/break-glass', { method: 'POST', body: JSON.stringify({ patient_key: patientKey, justification }) });
  },

  async bookAppointment(body: { patient_key: string; practitioner_user_id: string; start: string; end?: string; dept?: string }): Promise<Appointment> {
    return api('/appointments', { method: 'POST', body: JSON.stringify(body) });
  },

  async cancelAppointment(id: string): Promise<Appointment> {
    return api(`/appointments/${id}`, { method: 'PATCH', body: JSON.stringify({ status: 'cancelled' }) });
  },

  async availability(opts: { department?: string; practitioner_user_id?: string } = {}): Promise<{ slots: Slot[]; count: number }> {
    return api('/tools/availability', { method: 'POST', body: JSON.stringify(opts) });
  },

  async getHomeDashboard(): Promise<HomeDashboard> {
    const me = await this.getMe().catch(() => null);
    const patients = me ? await this.getPatients().catch(() => []) : [];
    const visible = patients.filter(patient => patient.status === 'Visible');
    const support = me ? await this.loadVisibleSupport(visible, me) : { labsByKey: {}, encountersByKey: {}, documentsByKey: {} };
    const audit = me ? await this.listAudit().catch(() => ({ events: [] as AuditRow[] })) : { events: [] };
    const personas = await this.getPersonas().catch(() => []);
    return {
      greeting: me?.display ? `Signed in as ${me.display}` : 'Sign in to load live charts',
      todaysPatients: attachEncounters(visible, support.encountersByKey),
      briefing: deriveBriefing(me, visible),
      attention: deriveAttention(visible, support.labsByKey),
      recentActivity: activityFromAudit(audit.events, visible, personas)
    };
  },

  async getFollowUps(): Promise<FollowUp[]> {
    const me = await this.getMe().catch(() => null);
    if (!me) return [];
    const patients = await this.getPatients().catch(() => []);
    const support = await this.loadVisibleSupport(patients.filter(patient => patient.status === 'Visible'), me);
    return deriveFollowUps({ patients, ...support });
  },

  async loadVisibleSupport(patients: PatientSummary[], me: Me) {
    const labsByKey: Record<string, QueryResponse | null> = {};
    const encountersByKey: Record<string, QueryResponse | null> = {};
    const documentsByKey: Record<string, ReturnType<typeof composePatient>['documents']> = {};
    await Promise.all(patients.map(async patient => {
      if (me.panels.includes('labs')) {
        labsByKey[patient.id] = await ignoreMissing(() => this.query('labs', {
          patient_key: patient.id,
          filters: { limit: 80 }
        }));
      }
      if (me.panels.includes('appointments') || me.panels.includes('labs') || me.panels.includes('portal')) {
        encountersByKey[patient.id] = await ignoreMissing(() => this.query('encounters', { patient_key: patient.id }));
      }
      if (me.panels.includes('notes')) {
        const notes = await ignoreMissing(() => this.notes(patient.id));
        documentsByKey[patient.id] = notes
          ? composePatient(patient.id, null, {}, { notes, canOpenSignedFiles: sessionCanOpenSignedFiles(me) }).documents
          : [];
      }
    }));
    return { labsByKey, encountersByKey, documentsByKey };
  },

  async visiblePatientKeys(): Promise<string[]> {
    const listed = await ignoreMissing(() => api<{ patient_keys: string[] }>('/patients'));
    const keys = listed?.patient_keys ?? [];
    const live = keys.filter(key => !(DEMO_PATIENT_KEYS as readonly string[]).includes(key));
    // Prefer Synthea / granted live keys. Fall back to self/demo only when FGA has nothing else.
    return live.length ? live : keys;
  },

  async getPatients(): Promise<PatientSummary[]> {
    const me = await this.getMe().catch(() => null);
    if (me && workspaceFor(me.role) === 'kitchen') return this.getKitchenRoster();
    const keys = await this.visiblePatientKeys();
    const banners = await Promise.all(keys.map(key => ignoreMissing(() => this.getIdentity(key))));
    return summariesFromKeys(keys, banners);
  },

  async getKitchenRoster(): Promise<PatientSummary[]> {
    const keys = await this.visiblePatientKeys();
    const cards = await Promise.all(keys.map(async key => {
      const diet = await ignoreMissing(() => this.query('diet', { patient_key: key }));
      return diet ? kitchenCardFromDiet(key, diet) : null;
    }));
    return cards.filter((card): card is PatientSummary => card !== null);
  },

  async searchPatients(query: string): Promise<PatientSummary[]> {
    return filterPatients(await this.getPatients(), query);
  },

  async getPatient(patientId: string): Promise<Patient> {
    const me = await this.getMe().catch(() => null);
    const identity = await ignoreMissing(() => this.getIdentity(patientId));
    const datasets = me
      ? chartQueryDatasets(me.panels)
      : (['labs', 'conditions', 'meds', 'encounters', 'allergies', 'diet'] as const);
    const results = await Promise.all(datasets.map(async dataset => ({
      dataset,
      query: await ignoreMissing(() => this.query(dataset, {
        patient_key: patientId,
        filters: { limit: dataset === 'labs' || dataset === 'conditions' ? 400 : 100 }
      }))
    })));
    const byDataset = Object.fromEntries(results.map(item => [item.dataset, item.query]));
    const notes = !me || me.panels.includes('notes')
      ? await ignoreMissing(() => this.notes(patientId, 'clinical notes'))
      : null;
    const imaging = !me || me.panels.includes('imaging') || me.panels.includes('imaging_metadata')
      ? await ignoreMissing(() => this.imaging(patientId))
      : null;
    if (!identity && results.every(item => item.query === null) && !notes && !imaging) {
      throw new ApiError(404, { resourceType: 'OperationOutcome' }, 'Resource not found');
    }
    const patient = composePatient(patientId, identity, byDataset as Record<string, QueryResponse | null>, {
      notes,
      imaging,
      canOpenSignedFiles: sessionCanOpenSignedFiles(me)
    });
    patient.canUpload = Boolean(me?.panels.includes('notes') && notes);
    return patient;
  },

  async getTimeline(patientId: string): Promise<TimelineEvent[]> {
    return composeTimeline(await this.getPatient(patientId));
  },

  async notes(patientKey: string, question = 'clinical notes'): Promise<NotesResponse> {
    return api('/tools/notes', { method: 'POST', body: JSON.stringify({ patient_key: patientKey, question }) });
  },

  async imaging(patientKey: string): Promise<ImagingResponse> {
    return api('/tools/imaging', { method: 'POST', body: JSON.stringify({ patient_key: patientKey }) });
  },

  async reprocessStudy(patientKey: string, studyId: string, classes?: string[]): Promise<ReprocessOut> {
    return api(`/patients/${encodeURIComponent(patientKey)}/studies/${encodeURIComponent(studyId)}/reprocess`, {
      method: 'POST',
      body: JSON.stringify(classes?.length ? { classes } : {})
    });
  },

  async signMedia(body: { patient_key: string; study_id?: string; object_key?: string }): Promise<MediaSignOut> {
    return api('/media/sign', { method: 'POST', body: JSON.stringify(body) });
  },

  async fetchMedia(url: string): Promise<MediaFetchOut> {
    return api(url.startsWith('/media') ? url : `/media/${url}`);
  },

  async askPatient360(request: AskPatient360Request): Promise<AiAnswer> {
    const history = (request.history ?? []).slice(-8).map(turn => ({
      role: turn.role,
      content: turn.content.slice(0, 2000)
    }));
    const body = await api<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({
        question: request.question,
        patient_key: request.patientId,
        ...(history.length ? { history } : {})
      })
    });
    return {
      id: body.audit_id,
      answer: body.answer,
      citations: body.citations.map(citation => ({
        id: citation.id,
        label: citation.label,
        sourceId: citation.sourceId,
        sourceType: citation.sourceType as AiAnswer['citations'][number]['sourceType']
      })),
      retrievalSteps: body.retrievalSteps,
      refused: body.refused,
      policy_reason: body.policy_reason,
      ...(body.sandbox_stamp ? { sandboxStamp: body.sandbox_stamp } : {})
    };
  },

  async chatSandbox(): Promise<ChatSandboxStatus> {
    return api('/chat/sandbox');
  },

  async uploadDocument(patientId: string, file: File): Promise<{ documentId: string; status: string; reason?: string }> {
    const data = new FormData();
    data.append('patient_key', patientId);
    data.append('file', file);
    return api('/uploads', { method: 'POST', body: data });
  },

  async deleteDocument(patientId: string, documentId: string): Promise<{ documentId: string; status: string }> {
    return api('/uploads', {
      method: 'DELETE',
      body: JSON.stringify({ patient_key: patientId, document_id: documentId })
    });
  },

  async listAudit(): Promise<{ events: AuditRow[] }> {
    return api('/audit');
  },

  async listRedteam(): Promise<{
    cases: Array<Record<string, unknown>>;
    count?: number;
    pass?: number;
    fail?: number;
    partial?: number;
    asr?: number;
  }> {
    return api('/redteam');
  },

  async redteam(): Promise<{
    cases: Array<Record<string, unknown>>;
    count?: number;
    pass?: number;
    fail?: number;
    partial?: number;
    asr?: number;
  }> {
    return api('/redteam/run', { method: 'POST' });
  }
};
