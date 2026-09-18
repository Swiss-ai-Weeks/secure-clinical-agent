import { defineStore } from 'pinia';
import { apiClient } from '../services/apiClient';
import { ApiError } from '../services/http';
import type { Me, Persona } from '../types/api';

export const useSessionStore = defineStore('session', {
  state: () => ({
    me: null as Me | null,
    personas: [] as Persona[],
    ready: false,
    error: ''
  }),
  getters: {
    panels: state => state.me?.panels ?? [],
    hasPanel: state => (panel: string) => Boolean(state.me?.panels.includes(panel)),
    display: state => state.me?.display ?? state.me?.user_id ?? 'Not signed in'
  },
  actions: {
    async bootstrap() {
      try {
        this.personas = await apiClient.getPersonas().catch(() => [
          { login: 'chen', user_id: 'u_chen', display: 'Dr. Sarah Chen' },
          { login: 'rivera', user_id: 'u_rivera', display: 'Nurse Alex Rivera' },
          { login: 'okafor', user_id: 'u_okafor', display: 'Dr. James Okafor' },
          { login: 'nair', user_id: 'u_nair', display: 'Priya Nair' },
          { login: 'maria', user_id: 'u_maria', display: 'Maria Santos' },
          { login: 'diego', user_id: 'u_diego', display: 'Diego Santos' },
          { login: 'lindqvist', user_id: 'u_lindqvist', display: 'Tomas Lindqvist' },
          { login: 'haller', user_id: 'u_haller', display: 'Nina Haller' }
        ]);
        this.me = await apiClient.getMe();
        this.error = '';
      } catch (error) {
        this.me = null;
        this.error = error instanceof ApiError && error.status === 401 ? '' : (error as Error).message;
      } finally {
        this.ready = true;
      }
    },
    async switchPersona(login: string, opts: { on_duty?: boolean; auth_level?: number } = {}) {
      await apiClient.login(login, opts);
      this.me = await apiClient.getMe();
      this.error = '';
    },
    async logout() {
      await apiClient.logout().catch(() => undefined);
      this.me = null;
    }
  }
});
