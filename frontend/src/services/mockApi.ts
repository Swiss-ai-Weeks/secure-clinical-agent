import { homeDashboard, patients, timelineEvents } from '../data/mockPatient360';
import type { AiAnswer, AskPatient360Request, ExtractedFact, HomeDashboard, Patient, PatientSummary, TimelineEvent } from '../types/patient360';

const delay = (ms = 220) => new Promise<void>(resolve => globalThis.setTimeout(resolve, ms));

export const mockApi = {
  async getHomeDashboard(): Promise<HomeDashboard> {
    await delay();
    return homeDashboard;
  },

  async getPatients(): Promise<PatientSummary[]> {
    await delay();
    return patients;
  },

  async searchPatients(query: string, mode: 'standard' | 'ai'): Promise<PatientSummary[]> {
    await delay(280);
    const normalized = query.trim().toLowerCase();
    const matches = patients.filter(patient => {
      const haystack = [patient.fullName, patient.patientId, patient.dateOfBirth, patient.phone, patient.email, patient.assignedClinician, patient.majorDiagnoses.join(' '), patient.medications.map(medication => medication.name).join(' ')].join(' ').toLowerCase();
      return normalized.length === 0 || haystack.includes(normalized) || mode === 'ai';
    });

    return matches.map(patient => ({
      ...patient,
      resultMode: mode,
      reason: mode === 'ai'
        ? `AI matched "${query}" against conditions, medications, recent activity, and notes.`
        : 'Matched structured patient fields.'
    }));
  },

  async getPatient(patientId: string): Promise<Patient> {
    await delay();
    const patient = patients.find(candidate => candidate.id === patientId);
    if (!patient) throw new Error(`Patient ${patientId} was not found`);
    return patient;
  },

  async getTimeline(patientId: string): Promise<TimelineEvent[]> {
    await delay();
    return patientId === 'emma-laurent' ? timelineEvents : [];
  },

  async askPatient360(request: AskPatient360Request): Promise<AiAnswer> {
    await delay(700);
    if (request.scope === 'clinic') {
      return {
        id: 'answer-clinic-1',
        answer: 'Three patients have outstanding blood tests, with Emma Laurent the highest-priority follow-up because her LDL increased and a neurology report is pending review.',
        retrievalSteps: ['Searching clinic tasks', 'Checking recent laboratory results', 'Applying Clinical Staff permissions'],
        citations: [{ id: 'citation-att-ldl', label: 'Emma LDL result', sourceId: 'event-lab-aug-18', sourceType: 'lab' }]
      };
    }

    return {
      id: 'answer-emma-migraine',
      answer: "Emma's migraine pattern changed from about once per month to about three episodes per month. The increase is supported by her September consultation and the patient update reporting headaches on four of the previous seven days. No neurological red flags have been documented.",
      retrievalSteps: ['Searching Emma Laurent timeline', 'Comparing symptom entries since last visit', 'Reading relevant consultation note', 'Preparing cited summary'],
      citations: [
        { id: 'citation-consult', label: '12 Sep consultation', sourceId: 'event-consult-sept-12', sourceType: 'visit' },
        { id: 'citation-update', label: '2 Sep patient update', sourceId: 'event-patient-update-sept-02', sourceType: 'patient-update' }
      ]
    };
  },

  async uploadDocument(patientId: string, fileName: string): Promise<{ documentId: string; extractedFacts: ExtractedFact[] }> {
    await delay(900);
    const documentId = `${patientId}-${fileName}`;
    return {
      documentId,
      extractedFacts: [
        { id: 'fact-diagnosis', label: 'Diagnosis', value: 'Migraine without aura', sourceDocumentId: documentId, status: 'pending' },
        { id: 'fact-medication', label: 'Medication', value: 'Magnesium 300 mg daily', sourceDocumentId: documentId, status: 'pending' },
        { id: 'fact-followup', label: 'Follow-up', value: 'Review headache diary in 8 weeks', sourceDocumentId: documentId, status: 'pending' }
      ]
    };
  },

  async applyExtractedFact(patientId: string, factId: string, decision: 'accepted' | 'edited' | 'rejected') {
    await delay(260);
    return { patientId, factId, decision };
  }
};
