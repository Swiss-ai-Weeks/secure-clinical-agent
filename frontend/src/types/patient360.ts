export type Provenance = 'clinical' | 'patient-reported' | 'ai-generated';
export type TimelineKind = 'visit' | 'lab' | 'medication' | 'patient-update' | 'document' | 'note';
export type ResultMode = 'standard' | 'ai';
export type TaskStatus = 'pending' | 'confirmed' | 'done';
export type ExtractedFactStatus = 'pending' | 'accepted' | 'edited' | 'rejected';

export interface PermissionGate {
  canView: boolean;
  canAct: boolean;
  redactedFields: string[];
}

export interface PatientSummary {
  id: string;
  fullName: string;
  age: number;
  dateOfBirth: string;
  phone: string;
  email: string;
  status: string;
  appointmentTime?: string;
  appointmentType?: string;
  reasonForVisit?: string;
  warning?: string;
  avatarInitials: string;
  assignedClinician: string;
  resultMode?: ResultMode;
  reason?: string;
}

export interface Patient extends PatientSummary {
  sex: string;
  patientId: string;
  bloodType: string;
  majorAllergies: string[];
  majorDiagnoses: string[];
  riskIndicators: string[];
  measurements: Measurement[];
  labs: LabResult[];
  medications: Medication[];
  documents: MedicalDocument[];
  notes: ClinicalNote[];
  /** Demo-only, T3-tagged field — see src/data/accessControl.ts. */
  riskAssessment?: string;
}

/**
 * Frontend-only access-tier model for the role/tier demo (see src/data/accessControl.ts
 * and src/stores/useAccessControlStore.ts). Not a real classification system.
 */
export type AccessTier = 'T0' | 'T1' | 'T2' | 'T3';
export type AccessRole = 'attending' | 'resident' | 'nurse' | 'behavioral' | 'caregiver' | 'frontdesk' | 'compliance';

export interface Measurement {
  id: string;
  label: string;
  value: string;
  date: string;
  provenance: Provenance;
}

export interface LabResult {
  id: string;
  label: string;
  value: string;
  unit: string;
  referenceRange: string;
  previousValue?: string;
  trend: 'up' | 'down' | 'stable';
  abnormal: boolean;
  date: string;
  sourceId: string;
}

export interface Medication {
  id: string;
  name: string;
  dosage: string;
  frequency: string;
  route: string;
  startDate: string;
  stopDate?: string;
  prescriber: string;
  reason: string;
  current: boolean;
}

export interface MedicalDocument {
  id: string;
  title: string;
  type: string;
  date: string;
  source: string;
  processingState: 'processed' | 'pending-review' | 'extracting';
  uploadedBy: string;
  extractedFacts?: ExtractedFact[];
}

export interface ExtractedFact {
  id: string;
  label: string;
  value: string;
  sourceDocumentId: string;
  status: ExtractedFactStatus;
}

export interface ClinicalNote {
  id: string;
  title: string;
  author: string;
  date: string;
  text: string;
}

export interface TimelineEvent {
  id: string;
  kind: TimelineKind;
  date: string;
  title: string;
  summary: string;
  tags: string[];
  provenance: Provenance;
  linkedRecordId?: string;
}

export interface AiCitation {
  id: string;
  label: string;
  sourceId: string;
  sourceType: TimelineKind | 'lab' | 'document' | 'note';
}

export interface AiAnswer {
  id: string;
  answer: string;
  citations: AiCitation[];
  retrievalSteps: string[];
  /**
   * Demo-only: set when every fact this answer would have drawn on was
   * denied by decideAccess() for the requesting role — see
   * mockApi.askPatient360() and src/data/accessControl.ts. When true, the UI
   * should render this as a real denial (see AccessDenialCard.vue), not as
   * an empty or broken answer.
   */
  denied?: boolean;
  deniedField?: string;
  deniedTier?: AccessTier;
}

export interface AskPatient360Request {
  scope: 'patient' | 'clinic';
  patientId?: string;
  question: string;
  /** Sourced from useAccessControlStore's current role — see AskPatient360Panel.vue. */
  role: AccessRole;
}

export interface AttentionItem {
  id: string;
  patientId: string;
  severity: 'review' | 'warning' | 'urgent';
  title: string;
  detail: string;
  provenance: Provenance;
}

export interface HomeDashboard {
  greeting: string;
  todaysPatients: PatientSummary[];
  briefing: Array<{ id: string; text: string; patientId?: string }>;
  attention: AttentionItem[];
  recentActivity: TimelineEvent[];
}
