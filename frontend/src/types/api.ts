export interface SessionInfo {
  expires_at: string;
  absolute_expires_at: string;
  auth_level: number;
  on_duty: boolean;
}

export interface Me {
  user_id: string;
  display: string | null;
  role: string;
  department: string | null;
  credential_level: number;
  self_patient_id: string | null;
  datasets: string[];
  panels: string[];
  policy_version: string;
  session: SessionInfo;
}

export interface LoginOut {
  user_id: string;
  display: string | null;
  role: string;
  department: string | null;
  self_patient_id: string | null;
  panels: string[];
  session: SessionInfo;
}

export interface Persona {
  login: string;
  user_id: string;
  display: string;
  role?: string | null;
  panels?: string[];
}

export interface IdentityBanner {
  patient_key: string;
  given_name: string;
  family_name: string;
  birth_date: string;
  sex: string;
  mrn: string | null;
  purpose_of_event: string;
  compliance_flag: boolean;
  audit_id: string;
  identity_audit_id: string;
}

export interface QueryResponse {
  patient_key: string | null;
  dataset: string;
  rows: Record<string, unknown>[];
  row_count: number;
  redacted_count: number;
  suppressed_cells: number;
  obligations: Record<string, unknown>;
  decision: {
    effect: string;
    reason_code: string;
    policy_id: string;
    policy_version: string;
    relation: string | null;
    purpose_of_event: string;
    compliance_flag: boolean;
  };
  audit_id: string;
}

export interface Consent {
  consent_id: string | null;
  patient_key: string;
  grantee_user_id: string;
  relation: string;
  start: string | null;
  expiry: string | null;
  status: string;
  granted_by: string | null;
  recorded_at: string | null;
  justification: string | null;
  revoked_at: string | null;
  revoked_by: string | null;
  enforced: boolean;
  seeded: boolean;
}

export interface Appointment {
  id: string;
  cite_id?: string | null;
  patient_key: string;
  practitioner_user_id: string;
  status: string;
  start?: string | null;
  end?: string | null;
  dept?: string | null;
  created_by?: string | null;
}

export interface Slot {
  practitioner_user_id: string;
  department: string | null;
  start: string;
  end: string;
}

export interface NotesResponse {
  patient_key: string;
  chunks: Record<string, unknown>[];
  notes: Record<string, unknown>[];
  chunk_count: number;
  obligations: Record<string, unknown>;
  audit_id: string;
}

export interface ImagingResponse {
  patient_key: string;
  studies: Record<string, unknown>[];
  reports: Record<string, unknown>[];
  obligations: Record<string, unknown>;
  audit_id: string;
}

export interface ChatResponse {
  answer: string;
  citations: Array<{ id: string; label: string; sourceId: string; sourceType: string }>;
  retrievalSteps: string[];
  audit_id: string;
  policy_reason: string | null;
  refused: boolean;
  sandbox_stamp?: string | null;
}

export interface ChatSandboxStatus {
  active: boolean;
  stamp?: string;
}

export interface AuditRow {
  id: string;
  recorded_at: string | null;
  event_type: string;
  agent_user: string | null;
  purpose_of_event: string | null;
  entity_patient: string | null;
  entity_resource: string | null;
  outcome: string | null;
  reason_code: string | null;
}

export interface MediaSignOut {
  url: string;
  expires_in: number;
  jti: string;
  audit_id: string;
  study_instance_uid?: string;
}

export interface MediaFetchOut {
  study_uid: string;
  bytes_b64: string;
  length: number;
}

export interface ReprocessOut {
  patient_key: string;
  study_id: string;
  classes: string[];
  report_text: string;
  series_uid: string;
  report_source_id?: string | null;
  audit_id: string;
  decision_audit_id: string;
}

export const DEMO_PATIENT_KEYS = ['p_101', 'p_102', 'p_103', 'p_104', 'p_205'] as const;
