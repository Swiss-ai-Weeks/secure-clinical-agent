import { describe, expect, it } from 'vitest';
import {
  ACCESS_LEVEL_BY_ROLE,
  CREDENTIAL_LEVEL_LABELS,
  accessLevel,
  accessLevelForUser,
  actorAccessLabel,
  credentialLabel,
  personAccessLabel,
  withAccessLevel
} from '../../src/services/accessLevel';

describe('credentialLabel', () => {
  it('maps identity.users.credential_level 0–5', () => {
    expect(CREDENTIAL_LEVEL_LABELS).toEqual({
      0: 'Uncredentialed',
      1: 'Limited',
      2: 'Licensed',
      3: 'Privileged',
      4: 'Senior privileged',
      5: 'Full privileges'
    });
    expect(credentialLabel(3)).toBe('Privileged');
    expect(credentialLabel(2)).toBe('Licensed');
    expect(credentialLabel(1)).toBe('Limited');
    expect(credentialLabel(null)).toBe('');
  });
});

describe('accessLevel', () => {
  it('leads with credential level and keeps a useful role', () => {
    expect(ACCESS_LEVEL_BY_ROLE.attending).toBe('Attending');
    expect(accessLevel({ credential_level: 3, role: 'attending' })).toBe('Privileged · Attending');
    expect(accessLevel({ credential_level: 2, role: 'care_team' })).toBe('Licensed · Care team');
    expect(accessLevel({ credential_level: 2, role: 'researcher' })).toBe('Licensed · Research');
    expect(accessLevel({ credential_level: 1, role: 'patient' })).toBe('Limited · Family');
    expect(accessLevel({ credential_level: 1, role: 'dietary_staff' })).toBe('Limited · Dietary');
  });

  it('does not invent licenses or show raw codes, ids, or panel counts', () => {
    expect(accessLevel({ credential_level: 3, role: 'attending' })).not.toMatch(/board-certified|MD|RN|u_chen|p_|panels|Clinical/i);
    expect(accessLevel({ role: 'u_chen' })).toBe('');
  });

  it('falls back to role or panels when credential_level is missing', () => {
    expect(accessLevel({ role: 'attending' })).toBe('Attending');
    expect(accessLevel({ panels: ['aggregate'] })).toBe('Research');
  });
});

describe('person and actor labels', () => {
  const catalog = [
    { user_id: 'u_chen', display: 'Dr. Sarah Chen', role: 'attending', credential_level: 3 },
    { user_id: 'u_lindqvist', display: 'Tomas Lindqvist', role: 'dietary_staff', credential_level: 1 },
    { user_id: 'u_maria', display: 'Maria Santos', role: 'patient', credential_level: 1 },
    { user_id: 'u_nair', display: 'Priya Nair', role: 'researcher', credential_level: 2 }
  ];

  it('joins a display name with credential then role', () => {
    expect(personAccessLabel(catalog[0])).toBe('Dr. Sarah Chen · Privileged · Attending');
    expect(personAccessLabel(catalog[1])).toBe('Tomas Lindqvist · Limited · Dietary');
    expect(personAccessLabel(catalog[3])).toBe('Priya Nair · Licensed · Research');
    expect(withAccessLevel('Tomas Lindqvist', 'Limited · Dietary')).toBe('Tomas Lindqvist · Limited · Dietary');
    expect(accessLevelForUser('u_nair', catalog)).toBe('Licensed · Research');
  });

  it('resolves audit actors from the catalog without raw keys', () => {
    expect(actorAccessLabel('u_chen', catalog)).toBe('Dr. Sarah Chen · Privileged · Attending');
    expect(actorAccessLabel('u_maria', catalog)).toBe('Maria Santos · Limited · Family');
    expect(actorAccessLabel('u_unknown', catalog)).toBe('Unknown');
    expect(actorAccessLabel('u_chen', catalog)).not.toMatch(/u_chen|p_/);
  });
});
