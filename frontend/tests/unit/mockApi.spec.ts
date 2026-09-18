import { describe, expect, it } from 'vitest';
import { mockApi } from '../../src/services/mockApi';

describe('mockApi', () => {
  it('returns Elisabeth Keller as the demo anchor patient', async () => {
    const patient = await mockApi.getPatient('p_101');

    expect(patient.fullName).toBe('Elisabeth Keller');
    expect(patient.majorAllergies).toContain('Penicillin');
  });

  it('labels natural-language search results as AI generated', async () => {
    const results = await mockApi.searchPatients('diabetes', 'ai');

    expect(results[0].resultMode).toBe('ai');
    expect(results[0].reason).toContain('AI matched');
  });

  it('returns cited AI answers for patient-specific questions', async () => {
    const answer = await mockApi.askPatient360({
      scope: 'patient',
      patientId: 'p_101',
      question: 'What changed with this patient since the last visit?'
    });

    expect(answer.citations.map(citation => citation.sourceId)).toEqual(
      expect.arrayContaining(['obs_a1', 'med_a1'])
    );
  });

  it('returns extracted facts after a document upload', async () => {
    const result = await mockApi.uploadDocument('p_101', 'neurology-report.pdf');

    expect(result.extractedFacts).toHaveLength(3);
    expect(result.extractedFacts[0].status).toBe('pending');
  });
});
