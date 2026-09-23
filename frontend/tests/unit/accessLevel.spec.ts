import { describe, expect, it } from 'vitest';
import {
  ACCESS_LEVEL_BY_ROLE,
  accessLevel,
  accessLevelForUser,
  actorAccessLabel,
  personAccessLabel,
  withAccessLevel
} from '../../src/services/accessLevel';

describe('accessLevel', () => {
  it('maps live demo roles to short clinical labels', () => {
    expect(ACCESS_LEVEL_BY_ROLE).toEqual({
      attending: 'Attending',
      care_team: 'Care team',
      consultant: 'Consultant',
      caregiver: 'Family',
      patient: 'Family',
      dietary_staff: 'Dietary',
      researcher: 'Research',
      auditor: 'Audit'
    });
    expect(accessLevel({ role: 'attending' })).toBe('Attending');
    expect(accessLevel({ role: 'care_team' })).toBe('Care team');
    expect(accessLevel({ role: 'consultant' })).toBe('Consultant');
    expect(accessLevel({ role: 'dietary_staff' })).toBe('Dietary');
    expect(accessLevel({ role: 'researcher' })).toBe('Research');
    expect(accessLevel({ role: 'patient' })).toBe('Family');
    expect(accessLevel({ role: 'caregiver' })).toBe('Family');
    expect(accessLevel({ role: 'auditor' })).toBe('Audit');
  });

  it('does not hide attending as Clinical or mention panels or raw ids', () => {
    expect(accessLevel({ role: 'attending', panels: ['labs', 'notes', 'ask'] })).toBe('Attending');
    expect(accessLevel({ role: 'u_chen' })).toBe('');
    expect(accessLevel({ role: 'attending' })).not.toMatch(/clinical|panels|u_chen|p_/i);
  });

  it('falls back to workspace-style labels from panels when role is missing', () => {
    expect(accessLevel({ panels: ['diet', 'allergies_food'] })).toBe('Dietary');
    expect(accessLevel({ panels: ['aggregate'] })).toBe('Research');
    expect(accessLevel({ panels: ['audit'] })).toBe('Audit');
    expect(accessLevel({ panels: ['portal', 'labs'] })).toBe('Family');
  });
});

describe('person and actor labels', () => {
  const catalog = [
    { user_id: 'u_chen', display: 'Dr. Sarah Chen', role: 'attending' },
    { user_id: 'u_lindqvist', display: 'Tomas Lindqvist', role: 'dietary_staff' },
    { user_id: 'u_maria', display: 'Maria Santos', role: 'patient' },
    { user_id: 'u_nair', display: 'Priya Nair', role: 'researcher' }
  ];

  it('joins a display name with the access level', () => {
    expect(personAccessLabel(catalog[0])).toBe('Dr. Sarah Chen · Attending');
    expect(withAccessLevel('Tomas Lindqvist', 'Dietary')).toBe('Tomas Lindqvist · Dietary');
    expect(accessLevelForUser('u_nair', catalog)).toBe('Research');
  });

  it('resolves audit actors from the catalog without raw keys', () => {
    expect(actorAccessLabel('u_chen', catalog)).toBe('Dr. Sarah Chen · Attending');
    expect(actorAccessLabel('u_maria', catalog)).toBe('Maria Santos · Family');
    expect(actorAccessLabel('u_unknown', catalog)).toBe('Unknown');
    expect(actorAccessLabel('u_chen', catalog)).not.toMatch(/u_chen|p_/);
  });
});
