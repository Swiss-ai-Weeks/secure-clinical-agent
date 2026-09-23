/** Human-readable access levels from role / workspace / panels. Never raw ids or panel counts. */

export const ACCESS_LEVEL_BY_ROLE: Record<string, string> = {
  attending: 'Attending',
  care_team: 'Care team',
  consultant: 'Consultant',
  caregiver: 'Family',
  patient: 'Family',
  dietary_staff: 'Dietary',
  researcher: 'Research',
  auditor: 'Audit'
};

export interface AccessLevelSource {
  role?: string | null;
  panels?: readonly string[] | null;
}

export interface CatalogPerson extends AccessLevelSource {
  user_id: string;
  display?: string | null;
}

const OPAQUE_ID = /^(u_|p_)/i;

function text(value: string | null | undefined): string {
  return (value ?? '').trim();
}

function looksLikeOpaqueId(value: string): boolean {
  return OPAQUE_ID.test(value) || /^[0-9a-f]{8}-[0-9a-f-]{20,}$/i.test(value);
}

function titleCaseWords(value: string): string {
  return value
    .split(/[_\s]+/)
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ');
}

function fromPanels(panels: readonly string[]): string {
  const has = (panel: string) => panels.includes(panel);
  const chart = has('labs') || has('notes') || has('meds') || has('imaging') || has('imaging_metadata');
  if (has('aggregate') && !chart) return 'Research';
  if (has('audit') && !chart) return 'Audit';
  if ((has('diet') || has('allergies_food')) && !chart) return 'Dietary';
  if (has('portal') && !has('break_glass')) return 'Family';
  return '';
}

/** Short clinical label for a session or catalog person. */
export function accessLevel(source?: AccessLevelSource | null): string {
  const role = text(source?.role);
  if (role && !looksLikeOpaqueId(role)) {
    return ACCESS_LEVEL_BY_ROLE[role] || titleCaseWords(role);
  }
  return fromPanels(source?.panels ?? []);
}

export function accessLevelForUser(
  userId: string | null | undefined,
  people: readonly CatalogPerson[],
  me?: (AccessLevelSource & { user_id?: string }) | null
): string {
  if (me?.user_id && userId && me.user_id === userId) return accessLevel(me);
  return accessLevel(people.find(person => person.user_id === userId));
}

export function withAccessLevel(name: string, level: string): string {
  const display = text(name);
  const access = text(level);
  if (!display) return access;
  if (!access) return display;
  if (display === access || display.endsWith(` · ${access}`)) return display;
  return `${display} · ${access}`;
}

export function personAccessLabel(
  person: CatalogPerson | null | undefined,
  fallbackName = ''
): string {
  const name = text(person?.display) || fallbackName;
  return withAccessLevel(name, accessLevel(person));
}

export function actorAccessLabel(
  agentUser: string | null | undefined,
  people: readonly CatalogPerson[],
  me?: (AccessLevelSource & { user_id?: string; display?: string | null }) | null
): string {
  if (!agentUser) return 'System';
  if (me?.user_id === agentUser) {
    return withAccessLevel(text(me.display) || 'Signed-in user', accessLevel(me));
  }
  const person = people.find(entry => entry.user_id === agentUser);
  if (person) return personAccessLabel(person);
  if (looksLikeOpaqueId(agentUser)) {
    return titleCaseWords(agentUser.replace(/^u_/, '').replace(/_/g, ' '));
  }
  return agentUser;
}
