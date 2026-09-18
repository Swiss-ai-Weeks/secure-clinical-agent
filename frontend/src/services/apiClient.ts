import type {
  Appointment,
  AuditRow,
  ChatResponse,
  Consent,
  IdentityBanner,
  ImagingResponse,
  LoginOut,
  Me,
  MediaFetchOut,
  MediaSignOut,
  NotesResponse,
  Persona,
  QueryResponse,
  Slot
} from '../types/api';
import { DEMO_PATIENT_KEYS } from '../types/api';
import type { AiAnswer, AskPatient360Request, FollowUp, HomeDashboard, Patient, PatientSummary, TimelineEvent } from '../types/patient360';
import { activityFromAudit, attachEncounters, deriveAttention, deriveBriefing, deriveFollowUps, filterPatients } from './dashboard';
import { ApiError, api } from './http';
import { composePatient, composeTimeline, summariesFromKeys } from './patientRecord';

async function ignoreMissing<T>(work: () => Promise<T>): Promise<T | null> {
  try {
    return await work();
  } catch (error) {
    if (error instanceof ApiError && (error.notFound || error.status === 401)) return null;
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
    return {
      greeting: me?.display ? `Signed in as ${me.display}` : 'Sign in with a demo persona',
      todaysPatients: attachEncounters(patients, support.encountersByKey),
      briefing: deriveBriefing(me, patients),
      attention: deriveAttention(patients, support.labsByKey),
      recentActivity: activityFromAudit(audit.events)
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
        labsByKey[patient.id] = await ignoreMissing(() => this.query('labs', { patient_key: patient.id }));
      }
      if (me.panels.includes('appointments') || me.panels.includes('labs') || me.panels.includes('portal')) {
        encountersByKey[patient.id] = await ignoreMissing(() => this.query('encounters', { patient_key: patient.id }));
      }
      if (me.panels.includes('notes')) {
        const notes = await ignoreMissing(() => this.notes(patient.id));
        documentsByKey[patient.id] = notes ? composePatient(patient.id, null, {}, { notes }).documents : [];
      }
    }));
    return { labsByKey, encountersByKey, documentsByKey };
  },

  async getPatients(): Promise<PatientSummary[]> {
    const banners = await Promise.all(DEMO_PATIENT_KEYS.map(key => ignoreMissing(() => this.getIdentity(key))));
    return summariesFromKeys(DEMO_PATIENT_KEYS, banners);
  },

  async searchPatients(query: string): Promise<PatientSummary[]> {
    return filterPatients(await this.getPatients(), query);
  },

  async getPatient(patientId: string): Promise<Patient> {
    const identity = await ignoreMissing(() => this.getIdentity(patientId));
    const datasets = ['labs', 'conditions', 'meds', 'encounters', 'allergies', 'diet'] as const;
    const results = await Promise.all(datasets.map(async dataset => ({
      dataset,
      query: await ignoreMissing(() => this.query(dataset, { patient_key: patientId }))
    })));
    const byDataset = Object.fromEntries(results.map(item => [item.dataset, item.query]));
    const notes = await ignoreMissing(() => this.notes(patientId, 'clinical notes'));
    const imaging = await ignoreMissing(() => this.imaging(patientId));
    if (!identity && results.every(item => item.query === null) && !notes && !imaging) {
      throw new ApiError(404, { resourceType: 'OperationOutcome' }, 'Resource not found');
    }
    return composePatient(patientId, identity, byDataset as Record<string, QueryResponse | null>, { notes, imaging });
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

  async signMedia(body: { patient_key: string; study_id?: string; object_key?: string }): Promise<MediaSignOut> {
    return api('/media/sign', { method: 'POST', body: JSON.stringify(body) });
  },

  async fetchMedia(url: string): Promise<MediaFetchOut> {
    return api(url.startsWith('/media') ? url : `/media/${url}`);
  },

  async askPatient360(request: AskPatient360Request): Promise<AiAnswer> {
    const body = await api<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({ question: request.question, patient_key: request.patientId })
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
      policy_reason: body.policy_reason
    };
  },

  async uploadDocument(patientId: string, file: File): Promise<{ documentId: string; status: string }> {
    const data = new FormData();
    data.append('patient_key', patientId);
    data.append('file', file);
    return api('/uploads', { method: 'POST', body: data });
  },

  async listAudit(): Promise<{ events: AuditRow[] }> {
    return api('/audit');
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
