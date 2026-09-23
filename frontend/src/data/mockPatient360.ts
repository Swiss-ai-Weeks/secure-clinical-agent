import type { AttentionItem, HomeDashboard, Patient, TimelineEvent } from '../types/patient360';

export const patients: Patient[] = [
  {
    id: 'p_101', fullName: 'Elisabeth Keller', age: 65, dateOfBirth: '1961-04-17', phone: '', email: '', status: 'Active', appointmentTime: '', appointmentType: '', reasonForVisit: '', warning: 'Peanut and penicillin allergies', avatarInitials: 'EK', assignedClinician: 'Dr. Sarah Chen', sex: 'female', patientId: 'p_101', bloodType: '',
    majorAllergies: ['Peanut', 'Penicillin'],
    majorDiagnoses: ['Type 2 diabetes'],
    placement: 'Ward w_3b · diabetic diet · low sodium diet',
    riskIndicators: ['HbA1c 7.9%'],
    measurements: [],
    labs: [
      { id: 'obs_a1', label: 'HbA1c', value: '7.9', unit: '%', referenceRange: '', trend: 'up', flag: 'high', abnormal: true, date: '2026-09-10', sourceId: 'obs_a1' },
      { id: 'obs_a2', label: 'Creatinine', value: '1.3', unit: 'mg/dL', referenceRange: '', trend: 'stable', flag: 'normal', abnormal: false, date: '2026-09-10', sourceId: 'obs_a2' }
    ],
    medications: [
      { id: 'med_a1', name: 'Metformin', dosage: '', frequency: 'Daily', route: 'Oral', startDate: '2025-01-01', prescriber: '', reason: '', current: true },
      { id: 'med_a3', name: 'Lisinopril', dosage: '', frequency: 'Daily', route: 'Oral', startDate: '2024-01-01', stopDate: '2026-08-01', prescriber: '', reason: '', current: false }
    ],
    documents: [
      { id: 'doc-lab-p101', title: 'Recent labs', type: 'Laboratory report', date: '2026-09-10', source: 'Clinic', processingState: 'processed', uploadedBy: 'Inbox' }
    ],
    notes: []
  },
  {
    id: 'p_102', fullName: 'Marco Bianchi', age: 51, dateOfBirth: '1974-11-02', phone: '', email: '', status: 'Active', avatarInitials: 'MB', assignedClinician: 'Dr. Sarah Chen', sex: 'male', patientId: 'p_102', bloodType: '',
    majorAllergies: [], majorDiagnoses: ['Asthma'], placement: '', riskIndicators: [], measurements: [], labs: [], medications: [], documents: [], notes: []
  },
  {
    id: 'p_103', fullName: 'Maria Santos', age: 68, dateOfBirth: '1958-07-23', phone: '', email: '', status: 'Active', appointmentTime: '09:30', appointmentType: 'Cardiology', reasonForVisit: 'Booked appointment', avatarInitials: 'MS', assignedClinician: 'Dr. James Okafor', sex: 'female', patientId: 'p_103', bloodType: '',
    majorAllergies: [], majorDiagnoses: [], placement: '', riskIndicators: [], measurements: [],
    labs: [],
    medications: [{ id: 'med_c1', name: 'Amlodipine', dosage: '', frequency: 'Daily', route: 'Oral', startDate: '2026-01-01', prescriber: '', reason: '', current: true }],
    documents: [], notes: []
  },
  {
    id: 'p_104', fullName: 'Lea Haller', age: 14, dateOfBirth: '2012-05-03', phone: '', email: '', status: 'Active', avatarInitials: 'LH', assignedClinician: 'Nina Haller', sex: 'female', patientId: 'p_104', bloodType: '',
    majorAllergies: [], majorDiagnoses: ['Asthma'], placement: '', riskIndicators: ['Adolescent-confidential rows redacted for caregivers'], measurements: [], labs: [], medications: [], documents: [], notes: []
  },
  {
    id: 'p_205', fullName: 'Jonas Weber', age: 37, dateOfBirth: '1989-02-09', phone: '', email: '', status: 'Unassigned', avatarInitials: 'JW', assignedClinician: '', sex: 'male', patientId: 'p_205', bloodType: '',
    majorAllergies: [], majorDiagnoses: [], placement: '', riskIndicators: ['No live grant'], measurements: [], labs: [], medications: [], documents: [], notes: []
  }
];

export const timelineEvents: TimelineEvent[] = [
  { id: 'obs_a1', kind: 'lab', date: '2026-09-10', title: 'HbA1c', summary: '7.9 %', tags: ['Laboratory'], provenance: 'clinical', linkedRecordId: 'obs_a1' },
  { id: 'med_a1', kind: 'medication', date: '2025-01-01', title: 'Metformin', summary: 'Active', tags: ['Medication'], provenance: 'clinical' }
];

export const attentionItems: AttentionItem[] = [
  { id: 'att-hba1c', patientId: 'p_101', severity: 'warning', title: 'HbA1c above target', detail: 'Latest HbA1c is 7.9%.', provenance: 'clinical' }
];

export const homeDashboard: HomeDashboard = {
  greeting: 'Demo roster (sign in for live /me gating)',
  todaysPatients: patients,
  briefing: [
    { id: 'brief-1', text: 'Start with the patients on your roster.' },
    { id: 'brief-2', text: 'Elisabeth Keller is Dr. Chen’s assigned patient.', patientId: 'p_101' }
  ],
  attention: attentionItems,
  recentActivity: timelineEvents
};
