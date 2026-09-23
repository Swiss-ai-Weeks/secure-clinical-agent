export const SELF_GRANT_RELATIONS = ['caregiver', 'caregiver_notes', 'blocked'] as const;
export const DELEGATE_GRANT_RELATIONS = ['care_team', 'consultant'] as const;

const RELATION_COPY: Record<string, { label: string; hint: string }> = {
  caregiver: { label: 'Caregiver', hint: 'Clinical access for a family caregiver.' },
  caregiver_notes: { label: 'Caregiver notes', hint: 'Notes and updates only — not the full record.' },
  blocked: { label: 'Blocked', hint: 'Deny this person access to the record.' },
  care_team: { label: 'Care team', hint: 'Share with another clinician on the care team.' },
  consultant: { label: 'Consultant', hint: 'Time-limited specialist access.' },
  attending: { label: 'Attending', hint: 'Assigned attending physician.' },
  guardian: { label: 'Guardian', hint: 'Legal guardian for this record.' },
  emergency: { label: 'Emergency', hint: 'Break-glass emergency access.' }
};

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

export function relationLabel(relation: string): string {
  return RELATION_COPY[relation]?.label ?? relation.replace(/_/g, ' ');
}

export function relationHint(relation: string): string {
  return RELATION_COPY[relation]?.hint ?? '';
}

export function consentStatusLabel(status: string): string {
  if (!status) return 'Unknown';
  return status.charAt(0).toUpperCase() + status.slice(1).replace(/_/g, ' ');
}

export function consentStatusTone(status: string): 'neutral' | 'warning' | 'danger' | 'success' {
  if (status === 'active') return 'success';
  if (status === 'expired') return 'warning';
  if (status === 'revoked') return 'danger';
  return 'neutral';
}

export function initialsFor(name: string, userId = ''): string {
  const cleaned = name.trim();
  const looksLikeId = /^u_/.test(cleaned);
  const parts = cleaned.split(/\s+/).filter(Boolean);
  if (!looksLikeId && parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  if (!looksLikeId && parts[0] && /[a-z]/i.test(parts[0][0])) return parts[0].slice(0, 2).toUpperCase();
  const id = (looksLikeId ? cleaned : userId).replace(/^u_/, '');
  return (id.slice(0, 2) || '?').toUpperCase();
}
