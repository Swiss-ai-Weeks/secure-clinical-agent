import type { IdentityBanner, ImagingResponse, NotesResponse, QueryResponse } from '../types/api';
import type { ClinicalNote, LabResult, MedicalDocument, Medication, Patient, PatientSummary, TimelineEvent } from '../types/patient360';

export function ageFromIso(dateOfBirth: string): number {
  const born = new Date(dateOfBirth);
  if (Number.isNaN(born.getTime())) return 0;
  const now = new Date();
  let age = now.getUTCFullYear() - born.getUTCFullYear();
  const month = now.getUTCMonth() - born.getUTCMonth();
  if (month < 0 || (month === 0 && now.getUTCDate() < born.getUTCDate())) age -= 1;
  return age;
}

function initials(given: string, family: string, fallback: string): string {
  const letters = `${given.charAt(0)}${family.charAt(0)}`.toUpperCase();
  return letters.trim() || fallback.slice(0, 2).toUpperCase();
}

function text(value: unknown): string {
  if (value == null) return '';
  return String(value);
}

function labsFrom(query: QueryResponse | null): LabResult[] {
  return (query?.rows ?? []).map(row => {
    const redacted = Boolean(row.redacted);
    return {
      id: text(row.cite_id) || crypto.randomUUID(),
      label: redacted ? 'Redacted' : text(row.display) || text(row.code),
      value: redacted ? '—' : text(row.value_num ?? row.value_text ?? row.value_display),
      unit: redacted ? '' : text(row.unit),
      referenceRange: redacted ? '' : [row.ref_low, row.ref_high].filter(v => v != null).join('–') || text(row.ref_text),
      trend: 'stable',
      abnormal: !redacted && row.interpretation === 'H',
      date: text(row.effective_at).slice(0, 10),
      sourceId: text(row.cite_id)
    };
  });
}

function medsFrom(query: QueryResponse | null): Medication[] {
  return (query?.rows ?? []).map(row => {
    const redacted = Boolean(row.redacted);
    return {
      id: text(row.cite_id) || crypto.randomUUID(),
      name: redacted ? 'Redacted' : text(row.display) || text(row.code),
      dosage: redacted ? '—' : [row.dose_value, row.dose_unit, row.dosage_text].filter(Boolean).map(text).join(' '),
      frequency: redacted ? '' : text(row.timing_frequency),
      route: '',
      startDate: text(row.authored_at).slice(0, 10),
      stopDate: text(row.status) === 'stopped' ? text(row.authored_at).slice(0, 10) : undefined,
      prescriber: '',
      reason: text(row.reason_condition),
      current: text(row.status) === 'active'
    };
  });
}

function notesFrom(payload: NotesResponse | null): ClinicalNote[] {
  return (payload?.notes ?? []).map(row => ({
    id: text(row.cite_id || row.note_id),
    title: text(row.type_display) || 'Clinical note',
    author: text(row.provenance) || 'clinical',
    date: text(row.authored_at).slice(0, 10),
    text: row.redacted ? 'Redacted' : text(row.text)
  }));
}

function documentsFrom(payload: NotesResponse | null, imaging: ImagingResponse | null): MedicalDocument[] {
  const uploads = (payload?.notes ?? [])
    .filter(row => text(row.provenance) === 'patient-reported')
    .map(row => ({
      id: text(row.cite_id || row.note_id),
      title: text(row.type_display) || 'Uploaded document',
      type: 'patient-reported',
      date: text(row.authored_at).slice(0, 10),
      source: 'upload',
      processingState: row.published ? 'processed' as const : 'pending-review' as const,
      uploadedBy: 'patient',
      objectKey: text(row.sanitized_ref || row.cite_id || row.note_id) || undefined
    }));
  const reports = (imaging?.reports ?? []).map(row => ({
    id: text(row.cite_id),
    title: text(row.display) || 'Imaging report',
    type: text(row.category) || 'RAD',
    date: text(row.issued_at || row.effective_at).slice(0, 10),
    source: 'imaging',
    processingState: 'processed' as const,
    uploadedBy: 'clinical',
    studyId: text(row.study_id || row.cite_id) || undefined,
    objectKey: text(row.report_ref) || undefined
  }));
  return [...uploads, ...reports];
}

export function composePatient(
  patientKey: string,
  identity: IdentityBanner | null,
  queries: Record<string, QueryResponse | null>,
  extras: { notes?: NotesResponse | null; imaging?: ImagingResponse | null } = {}
): Patient {
  const given = identity?.given_name ?? '';
  const family = identity?.family_name ?? '';
  const fullName = identity ? `${given} ${family}`.trim() : `Patient ${patientKey}`;
  const labs = labsFrom(queries.labs);
  const medications = medsFrom(queries.meds);
  const diagnoses = (queries.conditions?.rows ?? [])
    .map(row => (row.redacted ? 'Redacted condition' : text(row.display)))
    .filter(Boolean);
  const allergies = (queries.allergies?.rows ?? [])
    .map(row => (row.redacted ? 'Redacted allergy' : text(row.display)))
    .filter(Boolean);
  const diet = (queries.diet?.rows ?? []).map(row => text(row.ward) && `Ward ${row.ward}`).filter(Boolean);
  return {
    id: patientKey,
    fullName,
    age: identity ? ageFromIso(identity.birth_date) : 0,
    dateOfBirth: identity?.birth_date ?? '',
    phone: '',
    email: '',
    status: identity ? 'Visible' : 'Record without identity banner',
    avatarInitials: initials(given, family, patientKey.replace('p_', 'P')),
    assignedClinician: '',
    sex: identity?.sex ?? '',
    patientId: identity?.mrn ?? patientKey,
    bloodType: '',
    majorAllergies: allergies,
    majorDiagnoses: diagnoses,
    riskIndicators: [
      ...(queries.labs?.redacted_count ? [`${queries.labs.redacted_count} lab row(s) redacted`] : []),
      ...(queries.conditions?.redacted_count ? [`${queries.conditions.redacted_count} condition row(s) redacted`] : []),
      ...diet
    ],
    measurements: [],
    labs,
    medications,
    documents: documentsFrom(extras.notes ?? null, extras.imaging ?? null),
    notes: notesFrom(extras.notes ?? null)
  };
}

export function composeTimeline(patient: Patient): TimelineEvent[] {
  const labs: TimelineEvent[] = patient.labs.map(lab => ({
    id: lab.id,
    kind: 'lab',
    date: lab.date,
    title: lab.label,
    summary: `${lab.value} ${lab.unit}`.trim(),
    tags: ['Laboratory'],
    provenance: 'clinical',
    linkedRecordId: lab.sourceId
  }));
  const meds: TimelineEvent[] = patient.medications.map(med => ({
    id: med.id,
    kind: 'medication',
    date: med.startDate,
    title: med.name,
    summary: [med.dosage, med.frequency].filter(Boolean).join(' · '),
    tags: ['Medication'],
    provenance: 'clinical'
  }));
  return [...labs, ...meds].sort((a, b) => b.date.localeCompare(a.date));
}

export function summariesFromKeys(keys: readonly string[], banners: Array<IdentityBanner | null>): PatientSummary[] {
  return keys.map((key, index) => {
    const identity = banners[index];
    if (!identity) {
      return {
        id: key,
        fullName: `Not visible (${key})`,
        age: 0,
        dateOfBirth: '',
        phone: '',
        email: '',
        status: 'Hidden',
        avatarInitials: key.slice(-2).toUpperCase(),
        assignedClinician: ''
      };
    }
    return {
      id: key,
      fullName: `${identity.given_name} ${identity.family_name}`.trim(),
      age: ageFromIso(identity.birth_date),
      dateOfBirth: identity.birth_date,
      phone: '',
      email: '',
      status: 'Visible',
      avatarInitials: initials(identity.given_name, identity.family_name, key),
      assignedClinician: identity.mrn ?? '',
      warning: identity.compliance_flag ? 'Break-glass active' : undefined
    };
  });
}
