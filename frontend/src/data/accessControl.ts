/**
 * FRONTEND-ONLY DEMO SIMULATION of a role/tier access-control layer.
 *
 * Nothing here is a real security boundary: every "decision" is made in the
 * browser, from static config, on data the browser already has in full. A
 * real implementation would send the (role, field, patient) tuple to a
 * backend Policy Decision Point (PDP) and let it decide what to return —
 * the server would simply never send restricted fields to a client that
 * isn't entitled to them. This file exists to demonstrate the UI mechanism
 * (role switching, tier badges, denial states, an access log) so that
 * mechanism can later be pointed at a real PDP call instead of this table.
 */
import type { AccessRole, AccessTier } from '../types/patient360';

export interface RoleDefinition {
  key: AccessRole;
  label: string;
  /** Tiers this role can reach. Anything above this is denied client-side, for demo purposes only. */
  reachableTiers: AccessTier[];
}

export const ACCESS_TIERS: AccessTier[] = ['T0', 'T1', 'T2', 'T3'];

export const ACCESS_ROLES: RoleDefinition[] = [
  { key: 'attending', label: 'Attending physician', reachableTiers: ['T0', 'T1', 'T2', 'T3'] },
  // Hospital-Data-Access-Roles.md Part 4: "Resident / student / trainee | T2 (supervised) |
  // Mirror attending access but require supervising clinician attribution on the audit trail."
  { key: 'resident', label: 'Resident / fellow', reachableTiers: ['T0', 'T1', 'T2'] },
  { key: 'nurse', label: 'Nurse', reachableTiers: ['T0', 'T1', 'T2'] },
  // Part 4: "Behavioral health notes specifically | T3, own rule | Never inherits from a
  // general 'clinical staff' grant — its own explicit authorization." This role's general
  // ceiling deliberately stops at T1 — it reaches T3 only via FIELD_ROLE_OVERRIDES below,
  // never by tier ceiling alone, so it can never pick up some OTHER T2/T3 field for free.
  { key: 'behavioral', label: 'Behavioral health', reachableTiers: ['T0', 'T1'] },
  { key: 'caregiver', label: 'Caregiver', reachableTiers: ['T0', 'T1'] },
  { key: 'frontdesk', label: 'Front desk', reachableTiers: ['T0'] },
  // Part 2.F / Part 4: "Compliance Officer / Privacy Officer / DPO — oversight access,
  // typically to audit logs and flagged cases rather than routine full-record browsing —
  // this role audits the Gate, it isn't exempt from it." Its T0-T3 reach in the doc is
  // explicitly "(transactional)" — i.e. scoped to the Audit & Privacy page (see
  // AUDIT_PAGE_ALLOWED_ROLES), never ordinary clinical-chart browsing. Hence T0 only here,
  // the same ceiling shape as Front Desk, though for a different reason (see AppShell.vue /
  // AuditPrivacyView.vue for the separate, role-identity-based audit-page grant).
  { key: 'compliance', label: 'Compliance officer', reachableTiers: ['T0'] }
];

/**
 * Page-level (not field-level) access: which roles may open the Audit &
 * Privacy page at all. Tier reach alone isn't the right check here — an
 * attending has full T0-T3 field reach but still shouldn't browse every
 * clinician's access history, so this is a separate role allowlist rather
 * than a decideAccess() tier comparison.
 */
export const AUDIT_PAGE_ALLOWED_ROLES: AccessRole[] = ['compliance'];

export const DEFAULT_ROLE: AccessRole = 'attending';

/**
 * Demo-only stand-in for "the supervising attending" a Resident/fellow's
 * access is attributed to — see useAccessControlStore.checkAccess() and
 * Hospital-Data-Access-Roles.md Part 4. Reuses the mock data's own
 * assignedClinician value (mockPatient360.ts) rather than inventing a name.
 */
export const RESIDENT_SUPERVISOR = 'Dr. Müller';

export function roleDefinition(role: AccessRole): RoleDefinition {
  return ACCESS_ROLES.find(r => r.key === role) ?? ACCESS_ROLES[0];
}

/** A representative handful of patient fields tagged with an access tier — not the whole schema. */
export interface FieldTierTag {
  field: string;
  label: string;
  tier: AccessTier;
}

export const FIELD_TIERS: Record<string, FieldTierTag> = {
  appointmentTime: { field: 'appointmentTime', label: 'Appointment time', tier: 'T0' },
  majorDiagnoses: { field: 'majorDiagnoses', label: 'Diagnoses', tier: 'T1' },
  medications: { field: 'medications', label: 'Medications', tier: 'T1' },
  riskAssessment: { field: 'riskAssessment', label: 'Risk assessment', tier: 'T3' },
  labs: { field: 'labs', label: 'Lab results', tier: 'T1' },
  // Dashboard-level content — clinical judgment derived from diagnoses/labs/notes,
  // so tagged at the same tier as the underlying clinical fields (T1).
  patientWarning: { field: 'patientWarning', label: 'Patient flag', tier: 'T1' },
  needsAttention: { field: 'needsAttention', label: 'Needs attention', tier: 'T1' },
  recentActivity: { field: 'recentActivity', label: 'Recent patient activity', tier: 'T1' },
  // Free-text synthesized narrative (e.g. the Ask Patient360 answer path) —
  // clinical judgment drawn from notes/timeline, same tier as the fields it's drawn from.
  clinicalNarrative: { field: 'clinicalNarrative', label: 'Clinical narrative', tier: 'T1' },
  // Patient360-Data-Taxonomy.md section 6 (Mental & Behavioral Health Data —
  // T2/T3): the one item in that list not flagged (T3) is substance-use
  // history, making it the doc-grounded T2 example. Family psychiatric
  // history is the same category by analogy.
  familyPsychiatricHistory: { field: 'familyPsychiatricHistory', label: 'Family psychiatric history', tier: 'T2' },
  substanceUseHistory: { field: 'substanceUseHistory', label: 'Substance use history', tier: 'T2' },
  // Per-note classification (see ClinicalNote.category, NotesView.vue):
  // ongoing behavioral-health treatment documentation (session/med-management
  // notes) — distinct from riskAssessment, which is crisis-specific (T3).
  // Taxonomy doc §6 defaults this category to T2 when it isn't one of the
  // explicitly-T3-flagged items (risk assessment, trauma, involuntary treatment).
  behavioralHealthNote: { field: 'behavioralHealthNote', label: 'Behavioral health note', tier: 'T2' },
  // Attending-only T3 fields — deliberately NOT in FIELD_ROLE_OVERRIDES below.
  // Unlike riskAssessment, neither of these has a role whose own domain
  // justifies a named exception, so only the general T3 tier ceiling reaches them.
  legalStatus: { field: 'legalStatus', label: 'Legal status', tier: 'T3' },
  geneticData: { field: 'geneticData', label: 'Genetic data', tier: 'T3' }
};

/**
 * Field-specific "own explicit authorization" — independent of a role's
 * general tier ceiling. This is how Behavioral health reaches the T3
 * risk-assessment field per Hospital-Data-Access-Roles.md Part 4:
 * "Behavioral health notes specifically | T3, own rule | Never inherits
 * from a general 'clinical staff' grant." Behavioral health's own
 * reachableTiers (above) deliberately stops at T1 — it does NOT reach T3
 * via tier ceiling the way Attending/Compliance do — so this override is
 * the *only* path to riskAssessment for that role, and it grants nothing
 * else. (There's no T2-tagged field in the current seed data, so a
 * distinct T2 authorization for this role isn't demonstrable here — see
 * the accompanying summary.)
 *
 * behavioralHealthNote follows the same pattern at T2: Behavioral health's
 * own ceiling stops at T1, so without this override the role couldn't read
 * its own specialty's routine treatment notes on a patient in its care —
 * which would be a self-defeating bug, not a safeguard. Same mechanism as
 * riskAssessment, one tier down.
 */
export const FIELD_ROLE_OVERRIDES: Record<string, AccessRole[]> = {
  riskAssessment: ['behavioral'],
  behavioralHealthNote: ['behavioral']
};

export interface AccessDecision {
  field: string;
  label: string;
  tier: AccessTier;
  allowed: boolean;
}

/**
 * Pure client-side stand-in for a PDP check: given a role and a field's tier,
 * decide allow/deny. In a real system this whole function is replaced by a
 * network call to the backend, which would already have filtered the data
 * before it reached the browser.
 */
export function decideAccess(role: AccessRole, fieldKey: string): AccessDecision {
  const tag = FIELD_TIERS[fieldKey];
  if (!tag) return { field: fieldKey, label: fieldKey, tier: 'T0', allowed: true };
  const viaTierCeiling = roleDefinition(role).reachableTiers.includes(tag.tier);
  const viaOwnDomainOverride = (FIELD_ROLE_OVERRIDES[fieldKey] ?? []).includes(role);
  return { field: tag.field, label: tag.label, tier: tag.tier, allowed: viaTierCeiling || viaOwnDomainOverride };
}
