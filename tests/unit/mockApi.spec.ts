import { describe, expect, it } from 'vitest';
import { mockApi } from '../../src/services/mockApi';

describe('mockApi', () => {
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

  it('returns cited AI answers for patient-specific questions', async () => {
    const answer = await mockApi.askPatient360({
      scope: 'patient',
      patientId: 'emma-laurent',
      question: "What changed with Emma's migraines over the last six months?"
    });

    expect(answer.citations.map(citation => citation.sourceId)).toEqual(
      expect.arrayContaining(['event-consult-sept-12', 'event-patient-update-sept-02'])
    );
  });

  it('returns extracted facts after a document upload', async () => {
    const result = await mockApi.uploadDocument('emma-laurent', 'neurology-report.pdf');

    expect(result.extractedFacts).toHaveLength(3);
    expect(result.extractedFacts[0].status).toBe('pending');
  });
});
