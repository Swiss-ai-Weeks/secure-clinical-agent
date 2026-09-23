import { cleanup, render, screen } from '@testing-library/vue';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import HomeView from '../../src/features/home/HomeView.vue';
import { useSessionStore } from '../../src/stores/useSessionStore';
import type { Me } from '../../src/types/api';

const query = vi.fn();
const getPatients = vi.fn();
const getHomeDashboard = vi.fn();
const listConsents = vi.fn();
const listAudit = vi.fn();

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    query: (...args: unknown[]) => query(...args),
    getPatients: (...args: unknown[]) => getPatients(...args),
    getHomeDashboard: (...args: unknown[]) => getHomeDashboard(...args),
    listConsents: (...args: unknown[]) => listConsents(...args),
    listAudit: (...args: unknown[]) => listAudit(...args)
  }
}));

function sessionMe(role: string, panels: string[], extra: Partial<Me> = {}): Me {
  return {
    user_id: extra.user_id ?? `u_${role}`,
    display: extra.display ?? role,
    role,
    department: null,
    credential_level: 2,
    self_patient_id: extra.self_patient_id ?? null,
    datasets: extra.datasets ?? [],
    panels,
    policy_version: 'test',
    session: { expires_at: '', absolute_expires_at: '', auth_level: 2, on_duty: true }
  };
}

async function renderHome(me: Me) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore();
  session.me = me;
  session.personas = [];
  session.ready = true;
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: HomeView },
      { path: '/patients/:patientId/overview', component: { template: '<div />' } },
      { path: '/patients/:patientId/diet', component: { template: '<div />' } },
      { path: '/patients/:patientId/appointments', component: { template: '<div />' } }
    ]
  });
  await router.push('/');
  await router.isReady();
  return render(HomeView, { global: { plugins: [router, pinia] } });
}

describe('role home workspaces', () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    query.mockReset();
    getPatients.mockReset();
    getHomeDashboard.mockReset();
    listConsents.mockReset();
    listAudit.mockReset();
    query.mockResolvedValue({ rows: [], row_count: 0, suppressed_cells: 0, obligations: {} });
    getPatients.mockResolvedValue([]);
    listConsents.mockResolvedValue({ consents: [] });
    listAudit.mockResolvedValue({ events: [] });
    getHomeDashboard.mockResolvedValue({
      greeting: 'Signed in as Dr. Chen',
      todaysPatients: [],
      briefing: [],
      attention: [],
      recentActivity: []
    });
  });

  it('shows the family portal instead of Today for a caregiver', async () => {
    getPatients.mockResolvedValue([{
      id: 'p_104',
      fullName: 'Jonas Haller',
      age: 16,
      dateOfBirth: '',
      phone: '',
      email: '',
      status: 'Visible',
      avatarInitials: 'JH',
      assignedClinician: ''
    }]);
    await renderHome(sessionMe('caregiver', ['portal', 'consents', 'labs', 'appointments', 'ask'], {
      user_id: 'u_haller',
      display: 'Nina Haller'
    }));
    expect(await screen.findByRole('heading', { name: /Welcome, Nina Haller/ })).toBeInTheDocument();
    expect(await screen.findByText('Jonas Haller')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Today' })).not.toBeInTheDocument();
  });

  it('shows the kitchen board instead of Today for dietary staff', async () => {
    query.mockResolvedValue({
      rows: [{ dims: { ward: 'w_3b' }, count: 1, suppressed: false }],
      row_count: 1,
      suppressed_cells: 0,
      obligations: { k_min: 1 }
    });
    getPatients.mockResolvedValue([{
      id: 'p_101',
      fullName: 'Ward w_3b',
      age: 0,
      dateOfBirth: '',
      phone: '',
      email: '',
      status: 'Visible',
      avatarInitials: '3B',
      assignedClinician: '',
      reason: 'diabetic diet'
    }]);
    await renderHome(sessionMe('dietary_staff', ['diet', 'allergies_food', 'aggregate_ward', 'ask'], {
      user_id: 'u_lindqvist',
      display: 'Tomas Lindqvist'
    }));
    expect(await screen.findByRole('heading', { name: 'Ward diet board' })).toBeInTheDocument();
    expect(await screen.findByText('Ward w_3b')).toBeInTheDocument();
    expect(screen.queryByText(/p_101/)).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Today' })).not.toBeInTheDocument();
  });

  it('shows cohort insights for a researcher', async () => {
    await renderHome(sessionMe('researcher', ['aggregate', 'ask'], { user_id: 'u_nair', display: 'Priya Nair' }));
    expect(await screen.findByRole('heading', { name: 'Cohort insights' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Today' })).not.toBeInTheDocument();
  });

  it('keeps Today for an attending', async () => {
    await renderHome(sessionMe('attending', ['labs', 'appointments', 'break_glass'], { user_id: 'u_chen', display: 'Dr. Sarah Chen' }));
    expect(await screen.findByRole('heading', { name: 'Today' })).toBeInTheDocument();
  });
});
