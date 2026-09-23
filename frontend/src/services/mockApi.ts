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
      const haystack = [patient.fullName, patient.patientId, patient.id, patient.majorDiagnoses.join(' '), patient.medications.map(medication => medication.name).join(' ')].join(' ').toLowerCase();
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
    return patientId === 'p_101' ? timelineEvents : [];
  },

  async askPatient360(request: AskPatient360Request): Promise<AiAnswer> {
    await delay(700);
    if (request.scope === 'clinic') {
      return {
        id: 'answer-clinic-1',
        answer: 'Ask is mocked until chat is available. In the live roster, Elisabeth Keller has an elevated HbA1c and is the assigned follow-up for Dr. Chen.',
        retrievalSteps: ['Searching clinic tasks', 'Checking recent laboratory results', 'Applying role panels'],
        citations: [{ id: 'citation-att-hba1c', label: 'Elisabeth HbA1c', sourceId: 'obs_a1', sourceType: 'lab' }]
      };
    }

    return {
      id: 'answer-patient-mock',
      answer: 'Ask is mocked until chat is available. The live chart comes from authorized query rows; this panel does not call the model.',
      retrievalSteps: ['Searching selected patient chart', 'Reading visible clinical rows', 'Preparing cited summary'],
      citations: [
        { id: 'citation-hba1c', label: 'Recent HbA1c', sourceId: 'obs_a1', sourceType: 'lab' },
        { id: 'citation-metformin', label: 'Metformin', sourceId: 'med_a1', sourceType: 'medication' }
      ]
    };
  },

  async uploadDocument(patientId: string, fileName: string): Promise<{ documentId: string; extractedFacts: ExtractedFact[] }> {
    await delay(900);
    const documentId = `${patientId}-${fileName}`;
    return {
      documentId,
      extractedFacts: [
        { id: 'fact-diagnosis', label: 'Diagnosis', value: 'Type 2 diabetes', sourceDocumentId: documentId, status: 'pending' },
        { id: 'fact-medication', label: 'Medication', value: 'Metformin', sourceDocumentId: documentId, status: 'pending' },
        { id: 'fact-followup', label: 'Follow-up', value: 'Review HbA1c in 8 weeks', sourceDocumentId: documentId, status: 'pending' }
      ]
    };
  },

  async applyExtractedFact(patientId: string, factId: string, decision: 'accepted' | 'edited' | 'rejected') {
    await delay(260);
    return { patientId, factId, decision };
  }
};
