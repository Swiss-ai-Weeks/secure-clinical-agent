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
}

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
}

export interface AskPatient360Request {
  scope: 'patient' | 'clinic';
  patientId?: string;
  question: string;
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
