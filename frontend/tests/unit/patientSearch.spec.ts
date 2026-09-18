import { describe, expect, it } from 'vitest';
import { patients } from '../../src/data/mockPatient360';
import { filterPatients } from '../../src/services/dashboard';

describe('patient search', () => {
  it('supports structured search by name', () => {
    const results = filterPatients(patients, 'Elisabeth');

    expect(results[0].fullName).toBe('Elisabeth Keller');
    expect(results[0].resultMode).toBe('standard');
  });

  it('does not invent natural-language matches', () => {
    const results = filterPatients(patients, 'patients with diabetes');

    expect(results).toHaveLength(0);
  });
});
