import type { AttentionItem, HomeDashboard, Patient, TimelineEvent } from '../types/patient360';

export const patients: Patient[] = [
  {
    id: 'emma-laurent', fullName: 'Emma Laurent', age: 34, dateOfBirth: '1992-04-18', phone: '+41 79 555 0134', email: 'emma.laurent@example.ch', status: 'Active', appointmentTime: '09:30', appointmentType: 'Follow-up consultation', reasonForVisit: 'Migraine review and new LDL result', warning: 'Penicillin allergy; LDL increased 12%', avatarInitials: 'EL', assignedClinician: 'Dr. Müller', sex: 'Female', patientId: 'P360-1042', bloodType: 'O+',
    majorAllergies: ['Penicillin'],
    majorDiagnoses: ['Migraine without aura', 'Hyperlipidemia'],
    riskIndicators: ['Elevated LDL', 'Worsening headache frequency'],
    measurements: [
      { id: 'm-bp', label: 'Blood pressure', value: '128/82 mmHg', date: '2026-09-12', provenance: 'clinical' },
      { id: 'm-hr', label: 'Heart rate', value: '74 bpm', date: '2026-09-12', provenance: 'clinical' },
      { id: 'm-weight', label: 'Weight', value: '68 kg', date: '2026-09-02', provenance: 'patient-reported' }
    ],
    labs: [
      { id: 'lab-ldl-sept', label: 'LDL cholesterol', value: '4.2', unit: 'mmol/L', referenceRange: '< 3.0', previousValue: '3.7', trend: 'up', abnormal: true, date: '2026-08-18', sourceId: 'event-lab-aug-18' },
      { id: 'lab-hba1c-sept', label: 'HbA1c', value: '5.4', unit: '%', referenceRange: '4.0-5.6', previousValue: '5.3', trend: 'stable', abnormal: false, date: '2026-08-18', sourceId: 'event-lab-aug-18' }
    ],
    medications: [
      { id: 'med-sumatriptan', name: 'Sumatriptan', dosage: '50 mg', frequency: 'As needed', route: 'Oral', startDate: '2026-03-11', prescriber: 'Dr. Müller', reason: 'Migraine attacks', current: true },
      { id: 'med-magnesium', name: 'Magnesium', dosage: '300 mg', frequency: 'Daily', route: 'Oral', startDate: '2026-09-02', prescriber: 'Patient-reported', reason: 'Migraine prevention', current: true }
    ],
    documents: [
      { id: 'doc-lab-aug', title: 'August lipid panel', type: 'Laboratory report', date: '2026-08-18', source: 'Limmat Lab', processingState: 'processed', uploadedBy: 'Clinic inbox' },
      { id: 'doc-neuro-sept', title: 'Neurology report', type: 'External medical report', date: '2026-09-14', source: 'Neurology Zentrum Zürich', processingState: 'pending-review', uploadedBy: 'Emma Laurent' }
    ],
    notes: [{ id: 'note-consult-sept', title: 'Migraine follow-up', author: 'Dr. Müller', date: '2026-09-12', text: 'Migraine frequency increased to three episodes per month. No neurological red flags documented.' }],
    // Demo-only T3 example field — see src/data/accessControl.ts.
    riskAssessment: 'Risk-assessment screening on 3 Aug 2026: no acute risk identified; safety plan reviewed and current.'
  },
  {
    id: 'jonas-meier', fullName: 'Jonas Meier', age: 58, dateOfBirth: '1968-01-09', phone: '+41 79 555 0199', email: 'jonas.meier@example.ch', status: 'Active', appointmentTime: '11:00', appointmentType: 'Diabetes check', reasonForVisit: 'Dizziness reported after medication change', warning: 'New dizziness questionnaire', avatarInitials: 'JM', assignedClinician: 'Dr. Müller', sex: 'Male', patientId: 'P360-1068', bloodType: 'A+',
    majorAllergies: [], majorDiagnoses: ['Type 2 diabetes', 'Hypertension'], riskIndicators: ['Reported dizziness'], measurements: [], labs: [], medications: [], documents: [], notes: []
  }
];

export const timelineEvents: TimelineEvent[] = [
  { id: 'event-consult-sept-12', kind: 'visit', date: '2026-09-12', title: 'Consultation', summary: 'Migraine frequency increased to approximately three episodes per month. No neurological red flags documented.', tags: ['Dr. Müller', 'Consultation'], provenance: 'clinical', linkedRecordId: 'note-consult-sept' },
  { id: 'event-patient-update-sept-02', kind: 'patient-update', date: '2026-09-02', title: 'Patient update', summary: 'Reported headaches on four of the previous seven days and starting magnesium 300 mg daily.', tags: ['Patient reported'], provenance: 'patient-reported' },
  { id: 'event-lab-aug-18', kind: 'lab', date: '2026-08-18', title: 'Laboratory result', summary: 'LDL cholesterol measured at 4.2 mmol/L, up from 3.7 mmol/L.', tags: ['Laboratory', 'Abnormal LDL'], provenance: 'clinical', linkedRecordId: 'lab-ldl-sept' },
  { id: 'event-doc-july-21', kind: 'document', date: '2026-07-21', title: 'External neurology letter', summary: 'Previous neurologist documented migraine without aura and recommended continued symptom diary.', tags: ['Document', 'AI processed'], provenance: 'ai-generated' }
];

export const attentionItems: AttentionItem[] = [
  { id: 'att-ldl', patientId: 'emma-laurent', severity: 'warning', title: 'New abnormal lab result', detail: 'LDL cholesterol increased 12% since the previous result.', provenance: 'clinical' },
  { id: 'att-migraine', patientId: 'emma-laurent', severity: 'review', title: 'Worsening symptoms reported', detail: 'Emma reported headaches on four of the previous seven days.', provenance: 'patient-reported' },
  { id: 'att-doc', patientId: 'emma-laurent', severity: 'review', title: 'Uploaded report waiting for review', detail: 'Neurology report has extracted information pending clinician approval.', provenance: 'ai-generated' }
];

export const homeDashboard: HomeDashboard = {
  greeting: 'Good morning, Dr. Müller',
  todaysPatients: patients,
  briefing: [
    { id: 'brief-1', text: 'You have 8 patients today.' },
    { id: 'brief-2', text: '2 have new lab results.', patientId: 'emma-laurent' },
    { id: 'brief-3', text: '1 patient reported worsening symptoms overnight.', patientId: 'emma-laurent' },
    { id: 'brief-4', text: '3 follow-ups are overdue.' }
  ],
  attention: attentionItems,
  recentActivity: timelineEvents
};
