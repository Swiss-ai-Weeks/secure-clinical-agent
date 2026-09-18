import { describe, expect, it } from 'vitest';
import { defaultExpiryDate, expiryIso, expiryRequired, grantableRelations } from '../../src/services/consents';

describe('grantableRelations', () => {
  it('lets a patient or guardian grant caregiver relations', () => {
    expect(grantableRelations('patient')).toEqual(['caregiver', 'caregiver_notes', 'blocked']);
    expect(grantableRelations('caregiver')).toEqual(['caregiver', 'caregiver_notes', 'blocked']);
  });

  it('lets an attending delegate care_team and consultant', () => {
    expect(grantableRelations('attending')).toEqual(['care_team', 'consultant']);
  });

  it('returns nothing for roles without write authority', () => {
    expect(grantableRelations('researcher')).toEqual([]);
    expect(grantableRelations('dietary_staff')).toEqual([]);
  });
});

describe('consent expiry', () => {
  it('requires expiry except for blocked', () => {
    expect(expiryRequired('caregiver')).toBe(true);
    expect(expiryRequired('blocked')).toBe(false);
  });

  it('serializes a date input as UTC end of day', () => {
    expect(expiryIso('2026-10-01')).toBe('2026-10-01T23:59:59.000Z');
    expect(defaultExpiryDate()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
