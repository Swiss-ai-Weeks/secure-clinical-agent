import { homeDashboard, patients, timelineEvents } from '../data/mockPatient360';
import type { AiAnswer, AiCitation, AskPatient360Request, ExtractedFact, HomeDashboard, Patient, PatientSummary, TimelineEvent } from '../types/patient360';
import { FIELD_TIERS } from '../data/accessControl';
import { useAccessControlStore } from '../stores/useAccessControlStore';

const delay = (ms = 220) => new Promise<void>(resolve => globalThis.setTimeout(resolve, ms));

/**
 * FRONTEND-ONLY DEMO SIMULATION — see src/data/accessControl.ts. A candidate
 * fact the canned answer *would* draw on, before role gating. Modeling the
 * answer as a list of tagged facts (rather than one opaque paragraph) is
 * what lets askPatient360() apply decideAccess() per fact, the same way the
 * display layer gates each field — so an AI query that touches restricted
 * ground is denied the same way clicking into that field would be, instead
 * of being a separate, ungated code path.
 */
interface CandidateFact {
  fieldKey: string;
  text: string;
  citation: AiCitation;
}

function buildCandidateFacts(question: string, patient?: Patient): { primaryFieldKey: string; facts: CandidateFact[] } {
  const q = question.toLowerCase();

  if (q.includes('suicid') || q.includes('ideation')) {
    const facts: CandidateFact[] = patient?.riskAssessment
      ? [{
          fieldKey: 'riskAssessment',
          text: patient.riskAssessment,
          citation: { id: 'citation-risk-assessment', label: 'Risk-assessment note', sourceId: `${patient.id}-risk-assessment`, sourceType: 'note' }
        }]
      : [];
    return { primaryFieldKey: 'riskAssessment', facts };
  }

  if (q.includes('medication')) {
    const currentMeds = (patient?.medications ?? []).filter(medication => medication.current);
    const facts: CandidateFact[] = currentMeds.map(medication => ({
      fieldKey: 'medications',
      text: `${medication.name} ${medication.dosage}, ${medication.frequency.toLowerCase()}, for ${medication.reason.toLowerCase()}.`,
      citation: { id: `citation-${medication.id}`, label: `${medication.name} medication record`, sourceId: medication.id, sourceType: 'medication' }
    }));
    if (patient?.majorDiagnoses.length) {
      facts.push({
        fieldKey: 'majorDiagnoses',
        text: `Prescribed in the context of ${patient.majorDiagnoses.join(' and ').toLowerCase()}.`,
        citation: { id: 'citation-problem-list', label: 'Problem list', sourceId: `${patient.id}-diagnoses`, sourceType: 'note' }
      });
    }
    return { primaryFieldKey: 'medications', facts };
  }

  if (!patient) return { primaryFieldKey: 'clinicalNarrative', facts: [] };

  // Default: the general clinical-narrative branch (e.g. the panel's own
  // suggested "what changed" question, or any other free-text question).
  return {
    primaryFieldKey: 'clinicalNarrative',
    facts: [
      {
        fieldKey: 'clinicalNarrative',
        text: "Emma's migraine pattern changed from about once per month to about three episodes per month.",
        citation: { id: 'citation-consult', label: '12 Sep consultation', sourceId: 'event-consult-sept-12', sourceType: 'visit' }
      },
      {
        fieldKey: 'clinicalNarrative',
        text: 'The increase is supported by the patient update reporting headaches on four of the previous seven days.',
        citation: { id: 'citation-update', label: '2 Sep patient update', sourceId: 'event-patient-update-sept-02', sourceType: 'patient-update' }
      },
      {
        fieldKey: 'majorDiagnoses',
        text: 'No neurological red flags have been documented.',
        citation: { id: 'citation-problem-list', label: 'Problem list', sourceId: `${patient.id}-diagnoses`, sourceType: 'note' }
      }
    ]
  };
}

function buildClinicCandidateFacts(): { primaryFieldKey: string; facts: CandidateFact[] } {
  return {
    primaryFieldKey: 'labs',
    facts: [
      {
        fieldKey: 'labs',
        text: 'Three patients have outstanding blood tests.',
        citation: { id: 'citation-lab-queue', label: 'Clinic lab queue', sourceId: 'clinic-lab-queue', sourceType: 'lab' }
      },
      {
        fieldKey: 'labs',
        text: 'Emma Laurent is the highest-priority follow-up because her LDL increased.',
        citation: { id: 'citation-att-ldl', label: 'Emma LDL result', sourceId: 'event-lab-aug-18', sourceType: 'lab' }
      },
      {
        fieldKey: 'clinicalNarrative',
        text: 'A neurology report is pending review for Emma.',
        citation: { id: 'citation-neuro-doc', label: 'Neurology report', sourceId: 'doc-neuro-sept', sourceType: 'document' }
      }
    ]
  };
}

/**
 * Filters candidate facts through the same decideAccess()-backed checkAccess()
 * every gated component already calls — so an AI query that touches three
 * fields logs three entries in the access log, exactly like manually viewing
 * those three fields would (see AccessLogPanel.vue).
 */
function gateFacts(facts: CandidateFact[]): CandidateFact[] {
  const access = useAccessControlStore();
  return facts.filter(fact => access.checkAccess(fact.fieldKey).allowed);
}

function composeAnswer(id: string, primaryFieldKey: string, originalFacts: CandidateFact[], retrievalSteps: string[]): AiAnswer {
  const allowedFacts = gateFacts(originalFacts);

  if (originalFacts.length > 0 && allowedFacts.length === 0) {
    const tag = FIELD_TIERS[primaryFieldKey];
    return {
      id,
      answer: `Restricted — ${tag.label} (${tag.tier}). This falls outside what your current role can access.`,
      citations: [],
      retrievalSteps,
      denied: true,
      deniedField: tag.label,
      deniedTier: tag.tier
    };
  }

  if (allowedFacts.length === 0) {
    return { id, answer: 'No information on file for this question.', citations: [], retrievalSteps };
  }

  return {
    id,
    answer: allowedFacts.map(fact => fact.text).join(' '),
    citations: allowedFacts.map(fact => fact.citation),
    retrievalSteps
  };
}

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
    const access = useAccessControlStore();
    // Sync the store to the role the request actually carried before deciding
    // or logging anything: a real backend only ever knows the role a request
    // was made under, not whatever the client's UI has drifted to since (e.g.
    // if the operator flips the role dropdown while this fake delay is
    // in-flight). This also lets checkAccess() below — which reads the
    // store's live role — double as the "decide using the request's role"
    // step and the logging step in one call, with no risk of the two disagreeing.
    access.setRole(request.role);
    const roleLabel = access.currentRole.label;

    if (request.scope === 'clinic') {
      const { primaryFieldKey, facts } = buildClinicCandidateFacts();
      return composeAnswer('answer-clinic-1', primaryFieldKey, facts, [
        'Searching clinic tasks', 'Checking recent laboratory results', `Applying ${roleLabel} permissions`
      ]);
    }

    const patient = patients.find(candidate => candidate.id === request.patientId);
    const { primaryFieldKey, facts } = buildCandidateFacts(request.question, patient);
    return composeAnswer('answer-emma-migraine', primaryFieldKey, facts, [
      `Searching ${patient?.fullName ?? 'patient'} timeline`, 'Comparing symptom entries since last visit',
      'Reading relevant clinical records', `Applying ${roleLabel} permissions`, 'Preparing cited summary'
    ]);
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
