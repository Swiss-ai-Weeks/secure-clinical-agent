import { createPinia, setActivePinia } from 'pinia';
import { describe, expect, it, vi } from 'vitest';
import { useSessionStore } from '../../src/stores/useSessionStore';
import type { Me } from '../../src/types/api';

const login = vi.fn();
const getMe = vi.fn();

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    login: (...args: unknown[]) => login(...args),
    getMe: (...args: unknown[]) => getMe(...args),
    getPersonas: async () => [],
    logout: async () => undefined
  }
}));

const me: Me = {
  user_id: 'u_chen',
  display: 'Dr. Sarah Chen',
  role: 'attending',
  department: null,
  credential_level: 2,
  self_patient_id: null,
  datasets: [],
  panels: ['labs'],
  policy_version: 'test',
  session: { expires_at: '', absolute_expires_at: '', auth_level: 2, on_duty: true }
};

describe('session store', () => {
  it('sets switching while switchPersona is in flight', async () => {
    setActivePinia(createPinia());
    const session = useSessionStore();
    let release!: (value: unknown) => void;
    login.mockImplementation(() => new Promise(resolve => { release = resolve; }));
    getMe.mockResolvedValue(me);

    const pending = session.switchPersona('chen');
    expect(session.switching).toBe(true);

    release({});
    await pending;

    expect(session.switching).toBe(false);
    expect(session.me?.user_id).toBe('u_chen');
    expect(login).toHaveBeenCalledWith('chen', {});
  });
});
