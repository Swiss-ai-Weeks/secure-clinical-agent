import { describe, expect, it } from 'vitest';
import {
  consentStatusLabel,
  consentStatusTone,
  defaultExpiryDate,
  expiryIso,
  expiryRequired,
  grantableRelations,
  initialsFor,
  relationHint,
  relationLabel
} from '../../src/services/consents';

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

describe('consent copy', () => {
  it('humanizes relations and statuses', () => {
    expect(relationLabel('caregiver_notes')).toBe('Caregiver notes');
    expect(relationHint('blocked')).toContain('Deny');
    expect(consentStatusLabel('expired')).toBe('Expired');
    expect(consentStatusTone('active')).toBe('success');
    expect(consentStatusTone('expired')).toBe('warning');
    expect(initialsFor('Diego Santos', 'u_diego')).toBe('DS');
    expect(initialsFor('u_diego', 'u_diego')).toBe('DI');
  });
});
