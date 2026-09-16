import { describe, expect, it } from 'vitest';
import { mockApi } from '../../src/services/mockApi';

describe('patient search', () => {
  it('supports structured search by name', async () => {
    const results = await mockApi.searchPatients('Emma', 'standard');

    expect(results[0].fullName).toBe('Emma Laurent');
    expect(results[0].resultMode).toBe('standard');
  });

  it('supports AI discovery queries', async () => {
    const results = await mockApi.searchPatients('patients with diabetes who recently reported dizziness', 'ai');

    expect(results.some(patient => patient.fullName === 'Jonas Meier')).toBe(true);
    expect(results[0].reason).toContain('AI matched');
  });
});
