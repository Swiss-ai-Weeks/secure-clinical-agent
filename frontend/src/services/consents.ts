export const SELF_GRANT_RELATIONS = ['caregiver', 'caregiver_notes', 'blocked'] as const;
export const DELEGATE_GRANT_RELATIONS = ['care_team', 'consultant'] as const;

export function grantableRelations(role: string): string[] {
  if (role === 'attending') return [...DELEGATE_GRANT_RELATIONS];
  if (role === 'patient' || role === 'caregiver') return [...SELF_GRANT_RELATIONS];
  return [];
}

export function expiryRequired(relation: string): boolean {
  return relation !== 'blocked';
}

export function defaultExpiryDate(days = 30): string {
  const when = new Date();
  when.setUTCDate(when.getUTCDate() + days);
  return when.toISOString().slice(0, 10);
}

export function expiryIso(date: string): string {
  return new Date(`${date}T23:59:59.000Z`).toISOString();
}
