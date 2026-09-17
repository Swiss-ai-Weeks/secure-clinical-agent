import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { mockApi } from '../../src/services/mockApi';
import { useAccessControlStore } from '../../src/stores/useAccessControlStore';

describe('mockApi', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('returns Emma Laurent as the demo anchor patient', async () => {
    const patient = await mockApi.getPatient('emma-laurent');

    expect(patient.fullName).toBe('Emma Laurent');
    expect(patient.majorAllergies).toContain('Penicillin');
  });

  it('labels natural-language search results as AI generated', async () => {
    const results = await mockApi.searchPatients('diabetes dizziness', 'ai');

    expect(results[0].resultMode).toBe('ai');
    expect(results[0].reason).toContain('AI matched');
  });

  it('returns cited AI answers for patient-specific questions, derived from that patient\'s own note and diagnoses', async () => {
    const answer = await mockApi.askPatient360({
      scope: 'patient',
      patientId: 'emma-laurent',
      question: "What changed with Emma's migraines over the last six months?",
      role: 'attending'
    });

    // Emma's own most-recent note + her own problem list — not the old
    // hardcoded event ids from before this branch derived from real data.
    expect(answer.citations.map(citation => citation.sourceId)).toEqual(
      expect.arrayContaining(['note-consult-sept', 'emma-laurent-diagnoses'])
    );
    expect(answer.answer).toContain('Migraine frequency increased');
    expect(answer.denied).toBeFalsy();
  });

  it('derives the default (non-keyword) branch from each patient\'s own data, not a hardcoded Emma narrative', async () => {
    const genericQuestion = "What's changed with this patient recently?";

    const marco = await mockApi.askPatient360({ scope: 'patient', patientId: 'marco-antonelli', question: genericQuestion, role: 'attending' });
    expect(marco.answer).toContain('Recovering well following PCI');
    expect(marco.answer).toContain('ST-elevation myocardial infarction');
    expect(marco.answer).not.toContain('Emma');
    expect(marco.citations.map(c => c.sourceId)).toEqual(expect.arrayContaining(['note-marco-followup', 'marco-antonelli-diagnoses']));

    const klaus = await mockApi.askPatient360({ scope: 'patient', patientId: 'klaus-bergmann', question: genericQuestion, role: 'attending' });
    expect(klaus.answer).toContain('Liver enzymes trending down');
    expect(klaus.answer).toContain('Alcohol use disorder');
    expect(klaus.answer).not.toContain('Emma');

    // Jonas has no notes on file at all — should still surface his own
    // diagnoses (not fall back to Emma's, and not a false "denied").
    const jonas = await mockApi.askPatient360({ scope: 'patient', patientId: 'jonas-meier', question: genericQuestion, role: 'attending' });
    expect(jonas.answer).toContain('Type 2 diabetes');
    expect(jonas.answer).not.toContain('Emma');
    expect(jonas.denied).toBeFalsy();
  });

  it('denies a risk-assessment question for roles without T3 reach, but answers it for attending', async () => {
    const question = 'Has she ever expressed suicidal ideation?';

    const nurseAnswer = await mockApi.askPatient360({ scope: 'patient', patientId: 'emma-laurent', question, role: 'nurse' });
    expect(nurseAnswer.denied).toBe(true);
    expect(nurseAnswer.deniedField).toBe('Risk assessment');
    expect(nurseAnswer.citations).toHaveLength(0);

    const frontdeskAnswer = await mockApi.askPatient360({ scope: 'patient', patientId: 'emma-laurent', question, role: 'frontdesk' });
    expect(frontdeskAnswer.denied).toBe(true);

    const attendingAnswer = await mockApi.askPatient360({ scope: 'patient', patientId: 'emma-laurent', question, role: 'attending' });
    expect(attendingAnswer.denied).toBeFalsy();
    expect(attendingAnswer.answer).toContain('safety plan reviewed');
  });

  it('denies a medications question for front desk but answers it for other clinical roles', async () => {
    const question = 'What are her current medications and why?';

    const frontdeskAnswer = await mockApi.askPatient360({ scope: 'patient', patientId: 'emma-laurent', question, role: 'frontdesk' });
    expect(frontdeskAnswer.denied).toBe(true);
    expect(frontdeskAnswer.deniedField).toBe('Medications');

    const nurseAnswer = await mockApi.askPatient360({ scope: 'patient', patientId: 'emma-laurent', question, role: 'nurse' });
    expect(nurseAnswer.denied).toBeFalsy();
    expect(nurseAnswer.answer).toContain('Sumatriptan');
  });

  it('logs one access-log entry per fact the query touched, via the same checkAccess() every gated field uses', async () => {
    const access = useAccessControlStore();
    expect(access.accessLog).toHaveLength(0);

    await mockApi.askPatient360({
      scope: 'patient',
      patientId: 'emma-laurent',
      question: 'What are her current medications and why?',
      role: 'nurse'
    });

    // Two medications + one diagnosis-context fact for this question.
    expect(access.accessLog).toHaveLength(3);
    expect(access.accessLog.every(entry => entry.allowed)).toBe(true);
    expect(access.accessLog.every(entry => entry.roleLabel === 'Nurse')).toBe(true);
  });

  it('returns extracted facts after a document upload', async () => {
    const result = await mockApi.uploadDocument('emma-laurent', 'neurology-report.pdf');

    expect(result.extractedFacts).toHaveLength(3);
    expect(result.extractedFacts[0].status).toBe('pending');
  });
});
