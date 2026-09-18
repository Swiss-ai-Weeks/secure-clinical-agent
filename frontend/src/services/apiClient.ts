import type {
  Appointment,
  AuditRow,
  ChatResponse,
  Consent,
  IdentityBanner,
  ImagingResponse,
  LoginOut,
  Me,
  NotesResponse,
  Persona,
  QueryResponse,
  Slot
} from '../types/api';
import { DEMO_PATIENT_KEYS } from '../types/api';
import type { AiAnswer, AskPatient360Request, ExtractedFact, HomeDashboard, Patient, PatientSummary, TimelineEvent } from '../types/patient360';
import { ApiError, api } from './http';
import { mockApi } from './mockApi';
import { composePatient, composeTimeline, summariesFromKeys } from './patientRecord';

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
    return {
      greeting: me?.display ? `Signed in as ${me.display}` : 'Sign in with a demo persona',
      todaysPatients: patients,
      briefing: [
        { id: 'brief-role', text: me ? `${me.role} · panels gated by /me` : 'No session' },
        { id: 'brief-keys', text: `Demo keys: ${DEMO_PATIENT_KEYS.join(', ')}` }
      ],
      attention: [],
      recentActivity: []
    };
  },

  async getPatients(): Promise<PatientSummary[]> {
    const banners = await Promise.all(DEMO_PATIENT_KEYS.map(async key => {
      try {
        return await this.getIdentity(key);
      } catch (error) {
        if (error instanceof ApiError && (error.notFound || error.status === 401)) return null;
        throw error;
      }
    }));
    return summariesFromKeys(DEMO_PATIENT_KEYS, banners);
  },

  async searchPatients(query: string, mode: 'standard' | 'ai'): Promise<PatientSummary[]> {
    const patients = await this.getPatients();
    const normalized = query.trim().toLowerCase();
    const matches = patients.filter(patient => {
      const haystack = [patient.fullName, patient.id, patient.dateOfBirth].join(' ').toLowerCase();
      return normalized.length === 0 || haystack.includes(normalized) || mode === 'ai';
    });
    return matches.map(patient => ({
      ...patient,
      resultMode: mode,
      reason: mode === 'ai'
        ? `AI matched "${query}" against visible demo keys and identity banners.`
        : 'Matched structured patient fields.'
    }));
  },

  async getPatient(patientId: string): Promise<Patient> {
    const identity = await this.getIdentity(patientId).catch(error => {
      if (error instanceof ApiError && error.notFound) return null;
      throw error;
    });
    const datasets = ['labs', 'conditions', 'meds', 'encounters', 'allergies', 'diet'] as const;
    const results = await Promise.all(datasets.map(async dataset => {
      try {
        return { dataset, query: await this.query(dataset, { patient_key: patientId }) };
      } catch (error) {
        if (error instanceof ApiError && error.notFound) return { dataset, query: null };
        throw error;
      }
    }));
    const byDataset = Object.fromEntries(results.map(item => [item.dataset, item.query]));
    const notes = await this.notes(patientId, 'clinical notes').catch(error => {
      if (error instanceof ApiError && error.notFound) return null;
      throw error;
    });
    const imaging = await this.imaging(patientId).catch(error => {
      if (error instanceof ApiError && error.notFound) return null;
      throw error;
    });
    if (!identity && results.every(item => item.query === null) && !notes && !imaging) {
      throw new ApiError(404, { resourceType: 'OperationOutcome' }, 'Resource not found');
    }
    return composePatient(patientId, identity, byDataset as Record<string, QueryResponse | null>, { notes, imaging });
  },

  async getTimeline(patientId: string): Promise<TimelineEvent[]> {
    try {
      const patient = await this.getPatient(patientId);
      return composeTimeline(patient);
    } catch (error) {
      if (error instanceof ApiError && error.notFound) return [];
      throw error;
    }
  },

  async notes(patientKey: string, question = 'clinical notes'): Promise<NotesResponse> {
    return api('/tools/notes', { method: 'POST', body: JSON.stringify({ patient_key: patientKey, question }) });
  },

  async imaging(patientKey: string): Promise<ImagingResponse> {
    return api('/tools/imaging', { method: 'POST', body: JSON.stringify({ patient_key: patientKey }) });
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
      retrievalSteps: body.retrievalSteps
    };
  },

  async uploadDocument(patientId: string, file: File): Promise<{ documentId: string; status: string }> {
    const data = new FormData();
    data.append('patient_key', patientId);
    data.append('file', file);
    return api('/uploads', { method: 'POST', body: data });
  },

  applyExtractedFact(patientId: string, factId: string, decision: 'accepted' | 'edited' | 'rejected') {
    return mockApi.applyExtractedFact(patientId, factId, decision);
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
