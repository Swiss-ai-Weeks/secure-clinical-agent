import { render, screen, waitFor } from '@testing-library/vue';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';
import PatientOverviewView from '../../src/features/patient360/PatientOverviewView.vue';
import { mockApi } from '../../src/services/mockApi';
import { ApiError } from '../../src/services/http';
import { useSessionStore } from '../../src/stores/useSessionStore';
import type { Me } from '../../src/types/api';

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    getPatient: async (id: string) => {
      if (id === 'p_205') throw new ApiError(404, { resourceType: 'OperationOutcome' }, 'Resource not found');
      return mockApi.getPatient(id);
    },
    listConsents: async () => ({ consents: [] })
  }
}));

function sessionMe(role: string, panels: string[]): Me {
  return {
    user_id: `u_${role}`,
    display: role,
    role,
    department: null,
    credential_level: 2,
    self_patient_id: null,
    datasets: [],
    panels,
    policy_version: 'test',
    session: { expires_at: '', absolute_expires_at: '', auth_level: 2, on_duty: true }
  };
}

async function renderOverview(path: string, me?: Me) {
  const pinia = createPinia();
  setActivePinia(pinia);
  if (me) useSessionStore().me = me;
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/patients', component: { template: '<div />' } },
      { path: '/patients/:patientId/overview', component: PatientOverviewView },
      { path: '/patients/:patientId/diet', component: { template: '<div />' } }
    ]
  });
  await router.push(path);
  await router.isReady();
  return render(PatientOverviewView, { global: { plugins: [router, pinia] } });
}

describe('PatientOverviewView', () => {
  it('surfaces the Patient 360 five-second context', async () => {
    await renderOverview('/patients/p_101/overview');

    expect(await screen.findByText('Elisabeth Keller')).toBeInTheDocument();
    expect(screen.getAllByText(/Penicillin/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Location').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Ward w_3b/).length).toBeGreaterThan(0);
    expect(screen.getByText('Clinical brief')).toBeInTheDocument();
    expect(screen.getByText('Since your last consultation')).toBeInTheDocument();
    expect(screen.getByText('HbA1c')).toBeInTheDocument();
  });

  it('does not offer break-glass on a chart the session can already open', async () => {
    await renderOverview(
      '/patients/p_101/overview',
      sessionMe('attending', ['labs', 'consents', 'break_glass'])
    );
    expect(await screen.findByText('Elisabeth Keller')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open break-glass' })).not.toBeInTheDocument();
  });

  it('offers break-glass on a uniform not-found chart for care roles', async () => {
    await renderOverview('/patients/p_205/overview', sessionMe('attending', ['labs', 'break_glass']));
    expect(await screen.findByText('Chart not available')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open break-glass' })).toBeInTheDocument();
    expect(screen.queryByText(/p_205/)).not.toBeInTheDocument();
    expect(screen.getByText(/Emergency access for this chart/)).toBeInTheDocument();
  });

  it('hides break-glass on not-found when the persona cannot activate it', async () => {
    await renderOverview('/patients/p_205/overview', sessionMe('researcher', ['aggregate']));
    expect(await screen.findByText('Chart not available')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open break-glass' })).not.toBeInTheDocument();
  });

  it('sends dietary staff from overview to the diet surface', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const session = useSessionStore();
    session.me = {
      user_id: 'u_lindqvist',
      display: 'Tomas Lindqvist',
      role: 'dietary_staff',
      department: 'ward-3b',
      credential_level: 2,
      self_patient_id: null,
      datasets: ['diet'],
      panels: ['diet', 'allergies_food'],
      policy_version: 'test',
      session: { expires_at: '', absolute_expires_at: '', auth_level: 2, on_duty: true }
    };
    const kitchenRouter = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/patients/:patientId/overview', component: PatientOverviewView },
        { path: '/patients/:patientId/diet', component: { template: '<div>diet-surface</div>' } }
      ]
    });
    await kitchenRouter.push('/patients/p_101/overview');
    await kitchenRouter.isReady();
    render(PatientOverviewView, { global: { plugins: [kitchenRouter, pinia] } });
    await waitFor(() => expect(kitchenRouter.currentRoute.value.path).toBe('/patients/p_101/diet'));
  });
});
