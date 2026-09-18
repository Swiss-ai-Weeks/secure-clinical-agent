/**
 * FRONTEND-ONLY DEMO SIMULATION — see src/data/accessControl.ts for the caveat.
 * This store holds the "who's currently acting" role and an in-memory log of
 * client-side access checks. None of this is enforcement: it's a UI
 * simulation of what a real Policy Decision Point (PDP) call would return,
 * so a backend integration can later replace `decideAccess()` without
 * touching the components that consume this store.
 */
import { defineStore } from 'pinia';
import type { AccessRole } from '../types/patient360';
import { ACCESS_ROLES, DEFAULT_ROLE, RESIDENT_SUPERVISOR, decideAccess, roleDefinition } from '../data/accessControl';

export interface AccessLogEntry {
  id: string;
  role: AccessRole;
  roleLabel: string;
  field: string;
  fieldLabel: string;
  tier: string;
  allowed: boolean;
  timestamp: string;
  /**
   * Demo-only: populated for every ALLOW/DENY the Resident/fellow role
   * produces, per Hospital-Data-Access-Roles.md Part 4 ("mirror attending
   * access but require supervising clinician attribution on the audit
   * trail") — carried on the log entry itself, not just rendered
   * conditionally in the display layer, so it survives if this log is ever
   * read back by something other than AccessLogPanel.vue.
   */
  supervisionNote?: string;
}

const MAX_LOG_ENTRIES = 50;

function supervisionNoteFor(role: AccessRole): string | undefined {
  return role === 'resident' ? `supervised by: ${RESIDENT_SUPERVISOR}` : undefined;
}

export const useAccessControlStore = defineStore('accessControl', {
  state: () => ({
    role: DEFAULT_ROLE as AccessRole,
    accessLog: [] as AccessLogEntry[]
  }),
  getters: {
    roleOptions: () => ACCESS_ROLES,
    currentRole: state => roleDefinition(state.role),
    reachableTiers: state => roleDefinition(state.role).reachableTiers
  },
  actions: {
    setRole(role: AccessRole) {
      this.role = role;
    },
    /**
     * Stand-in for a PDP request: decides allow/deny for a field under the
     * current role, and records the attempt. A real integration would await
     * a backend call here instead of a synchronous local lookup.
     */
    checkAccess(fieldKey: string) {
      const decision = decideAccess(this.role, fieldKey);
      const entry: AccessLogEntry = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        role: this.role,
        roleLabel: this.currentRole.label,
        field: decision.field,
        fieldLabel: decision.label,
        tier: decision.tier,
        allowed: decision.allowed,
        timestamp: new Date().toLocaleTimeString(),
        supervisionNote: supervisionNoteFor(this.role)
      };
      this.accessLog.unshift(entry);
      if (this.accessLog.length > MAX_LOG_ENTRIES) this.accessLog.length = MAX_LOG_ENTRIES;
      return decision;
    },
    /**
     * Logs a page-level (role-allowlist, not tier-based) access decision —
     * e.g. whether the current role may open the Audit & Privacy page at
     * all. The allow/deny decision itself is made by the caller (see
     * RoleGate.vue); this only records it, the same way checkAccess()
     * records tier-based decisions.
     */
    logPageAccess(pageKey: string, pageLabel: string, allowed: boolean) {
      const entry: AccessLogEntry = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        role: this.role,
        roleLabel: this.currentRole.label,
        field: pageKey,
        fieldLabel: pageLabel,
        tier: 'PAGE',
        allowed,
        timestamp: new Date().toLocaleTimeString(),
        supervisionNote: supervisionNoteFor(this.role)
      };
      this.accessLog.unshift(entry);
      if (this.accessLog.length > MAX_LOG_ENTRIES) this.accessLog.length = MAX_LOG_ENTRIES;
    }
  }
});
