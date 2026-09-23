import { defineStore } from 'pinia';
import { apiClient } from '../services/apiClient';
import { ApiError } from '../services/http';
import { workspaceFor } from '../services/workspace';
import type { Me, Persona } from '../types/api';

/** Mirrors identity.users seed: role + credential_level. Used when the catalog omits them. */
const FALLBACK_PERSONAS: Persona[] = [
  { login: 'chen', user_id: 'u_chen', display: 'Dr. Sarah Chen', role: 'attending', credential_level: 3 },
  { login: 'rivera', user_id: 'u_rivera', display: 'Nurse Alex Rivera', role: 'care_team', credential_level: 2 },
  { login: 'okafor', user_id: 'u_okafor', display: 'Dr. James Okafor', role: 'consultant', credential_level: 3 },
  { login: 'nair', user_id: 'u_nair', display: 'Priya Nair', role: 'researcher', credential_level: 2 },
  { login: 'maria', user_id: 'u_maria', display: 'Maria Santos', role: 'patient', credential_level: 1 },
  { login: 'diego', user_id: 'u_diego', display: 'Diego Santos', role: 'caregiver', credential_level: 1 },
  { login: 'lindqvist', user_id: 'u_lindqvist', display: 'Tomas Lindqvist', role: 'dietary_staff', credential_level: 1 },
  { login: 'haller', user_id: 'u_haller', display: 'Nina Haller', role: 'caregiver', credential_level: 1 },
  { login: 'audit', user_id: 'u_audit', display: 'Compliance auditor', role: 'auditor', credential_level: 3 }
];

const ROLE_BY_USER_ID = Object.fromEntries(
  FALLBACK_PERSONAS.map(persona => [persona.user_id, persona.role ?? ''])
);
const CREDENTIAL_BY_USER_ID = Object.fromEntries(
  FALLBACK_PERSONAS.map(persona => [persona.user_id, persona.credential_level])
);

function enrichCatalog(personas: Persona[]): Persona[] {
  return personas.map(persona => ({
    ...persona,
    role: persona.role || ROLE_BY_USER_ID[persona.user_id] || persona.role,
    credential_level: persona.credential_level ?? CREDENTIAL_BY_USER_ID[persona.user_id] ?? persona.credential_level
  }));
}

function applySessionIdentity(personas: Persona[], me: Me | null): Persona[] {
  const catalog = enrichCatalog(personas);
  if (!me) return catalog;
  return catalog.map(persona => (
    persona.user_id === me.user_id
      ? { ...persona, role: me.role, credential_level: me.credential_level, panels: me.panels }
      : persona
  ));
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    me: null as Me | null,
    personas: [] as Persona[],
    ready: false,
    switching: false,
    error: ''
  }),
  getters: {
    panels: state => state.me?.panels ?? [],
    hasPanel: state => (panel: string) => Boolean(state.me?.panels.includes(panel)),
    workspace: state => workspaceFor(state.me?.role),
    display: state => (state.me ? (state.me.display || 'Signed-in user') : 'Not signed in')
  },
  actions: {
    async bootstrap() {
      try {
        this.personas = applySessionIdentity(
          await apiClient.getPersonas().catch(() => FALLBACK_PERSONAS),
          null
        );
        this.me = await apiClient.getMe();
        this.personas = applySessionIdentity(this.personas, this.me);
        this.error = '';
      } catch (error) {
        this.me = null;
        this.error = error instanceof ApiError && error.status === 401 ? '' : (error as Error).message;
      } finally {
        this.ready = true;
      }
    },
    async switchPersona(login: string, opts: { on_duty?: boolean; auth_level?: number } = {}) {
      this.switching = true;
      try {
        await apiClient.login(login, opts);
        this.me = await apiClient.getMe();
        this.personas = applySessionIdentity(this.personas, this.me);
        this.error = '';
      } finally {
        this.switching = false;
      }
    },
    async logout() {
      await apiClient.logout().catch(() => undefined);
      this.me = null;
    }
  }
});
