import { defineStore } from 'pinia';
import { apiClient } from '../services/apiClient';
import { ApiError } from '../services/http';
import { workspaceFor } from '../services/workspace';
import type { Me, Persona } from '../types/api';

const FALLBACK_PERSONAS: Persona[] = [
  { login: 'chen', user_id: 'u_chen', display: 'Dr. Sarah Chen', role: 'attending' },
  { login: 'rivera', user_id: 'u_rivera', display: 'Nurse Alex Rivera', role: 'care_team' },
  { login: 'okafor', user_id: 'u_okafor', display: 'Dr. James Okafor', role: 'consultant' },
  { login: 'nair', user_id: 'u_nair', display: 'Priya Nair', role: 'researcher' },
  { login: 'maria', user_id: 'u_maria', display: 'Maria Santos', role: 'patient' },
  { login: 'diego', user_id: 'u_diego', display: 'Diego Santos', role: 'caregiver' },
  { login: 'lindqvist', user_id: 'u_lindqvist', display: 'Tomas Lindqvist', role: 'dietary_staff' },
  { login: 'haller', user_id: 'u_haller', display: 'Nina Haller', role: 'caregiver' },
  { login: 'audit', user_id: 'u_audit', display: 'Compliance auditor', role: 'auditor' }
];

const ROLE_BY_USER_ID = Object.fromEntries(
  FALLBACK_PERSONAS.map(persona => [persona.user_id, persona.role ?? ''])
);

function fillCatalogRoles(personas: Persona[]): Persona[] {
  return personas.map(persona => (
    persona.role
      ? persona
      : { ...persona, role: ROLE_BY_USER_ID[persona.user_id] || persona.role }
  ));
}

function applySessionRole(personas: Persona[], me: Me | null): Persona[] {
  const catalog = fillCatalogRoles(personas);
  if (!me) return catalog;
  return catalog.map(persona => (
    persona.user_id === me.user_id
      ? { ...persona, role: me.role, panels: me.panels }
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
        this.personas = applySessionRole(
          await apiClient.getPersonas().catch(() => FALLBACK_PERSONAS),
          null
        );
        this.me = await apiClient.getMe();
        this.personas = applySessionRole(this.personas, this.me);
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
        this.personas = applySessionRole(this.personas, this.me);
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
