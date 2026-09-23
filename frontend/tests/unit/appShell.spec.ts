import { cleanup, fireEvent, render, screen } from '@testing-library/vue';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AppShell from '../../src/components/layout/AppShell.vue';
import { useSessionStore } from '../../src/stores/useSessionStore';
import type { Me } from '../../src/types/api';

const state = vi.hoisted(() => ({ me: null as Me | null }));

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    getPersonas: async () => [],
    getMe: async () => state.me,
    login: async () => ({}),
    logout: async () => undefined
  }
}));

vi.mock('../../src/components/layout/AskPatient360Panel.vue', () => ({
  default: { name: 'AskPatient360Panel', template: '<div />' }
}));

function sessionMe(role: string, panels: string[], extra: Partial<Me> = {}): Me {
  return {
    user_id: extra.user_id ?? `u_${role}`,
    display: extra.display ?? role,
    role,
    department: null,
    credential_level: 2,
    self_patient_id: extra.self_patient_id ?? null,
    datasets: [],
    panels,
    policy_version: 'test',
    session: {
      expires_at: '',
      absolute_expires_at: '',
      auth_level: 2,
      on_duty: true,
      ...extra.session
    }
  };
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => cleanup());

async function renderShell(me: Me, path = '/') {
  state.me = me;
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore();
  session.me = me;
  session.personas = [{ login: 'chen', user_id: 'u_chen', display: 'Dr. Sarah Chen' }];
  session.ready = true;
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/patients', component: { template: '<div />' } },
      { path: '/patients/:patientId/overview', component: { template: '<div />' } },
      { path: '/patients/:patientId/diet', component: { template: '<div />' } },
      { path: '/patients/:patientId/labs', component: { template: '<div />' } },
      { path: '/patients/:patientId/appointments', component: { template: '<div />' } },
      { path: '/patients/:patientId/timeline', component: { template: '<div />' } },
      { path: '/patients/:patientId/documents', component: { template: '<div />' } },
      { path: '/tasks', component: { template: '<div />' } },
      { path: '/cohort', component: { template: '<div />' } },
      { path: '/audit', component: { template: '<div />' } },
      { path: '/redteam', component: { template: '<div />' } }
    ]
  });
  await router.push(path);
  await router.isReady();
  return render(AppShell, { global: { plugins: [router, pinia] } });
}

describe('AppShell workspaces', () => {
  it('does not show staff chrome for a caregiver', async () => {
    await renderShell(sessionMe('caregiver', ['portal', 'labs', 'consents', 'appointments', 'ask', 'notes'], {
      user_id: 'u_haller',
      display: 'Nina Haller'
    }));
    expect(screen.getByRole('link', { name: 'My people' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Patients' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Tasks / Follow-ups' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Threat model' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Red team' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Cohort Insights' })).not.toBeInTheDocument();
  });

  it('shows only diet on a kitchen patient and staff tabs for an attending', async () => {
    await renderShell(sessionMe('dietary_staff', ['diet', 'allergies_food', 'aggregate_ward', 'ask'], {
      user_id: 'u_lindqvist',
      display: 'Tomas Lindqvist'
    }), '/patients/p_101/diet');
    expect(screen.getByRole('link', { name: 'Ward trays' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Diet' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Labs' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Overview' })).not.toBeInTheDocument();
  });

  it('shows Documents only in chart tabs, once, when a chart is open', async () => {
    const panels = ['labs', 'notes', 'imaging', 'appointments', 'aggregate_own_patients', 'break_glass'];
    await renderShell(sessionMe('attending', panels, { user_id: 'u_chen', display: 'Dr. Sarah Chen' }));
    expect(screen.queryByRole('link', { name: 'Documents' })).not.toBeInTheDocument();

    cleanup();
    const { container } = await renderShell(
      sessionMe('attending', panels, { user_id: 'u_chen', display: 'Dr. Sarah Chen' }),
      '/patients/p_101/overview'
    );
    expect(screen.getAllByRole('link', { name: 'Documents' })).toHaveLength(1);
    const sidebar = container.querySelector('.nav__list');
    expect(sidebar?.textContent ?? '').not.toMatch(/Documents/);
    expect(screen.getByRole('navigation', { name: 'Patient sections' }).textContent).toMatch(/Documents/);
  });

  it('hides Ask Patient360 unless clinical staff have an open chart', async () => {
    await renderShell(sessionMe('attending', ['labs', 'ask'], { user_id: 'u_chen', display: 'Dr. Sarah Chen' }));
    expect(screen.queryByRole('button', { name: 'Ask Patient360' })).not.toBeInTheDocument();

    cleanup();
    await renderShell(
      sessionMe('attending', ['labs', 'ask'], { user_id: 'u_chen', display: 'Dr. Sarah Chen' }),
      '/patients/p_101/overview'
    );
    expect(screen.getByRole('button', { name: 'Ask Patient360' })).toBeInTheDocument();

    cleanup();
    await renderShell(
      sessionMe('caregiver', ['portal', 'labs', 'ask'], { user_id: 'u_maria', display: 'Maria Santos' }),
      '/patients/p_103/overview'
    );
    expect(screen.queryByRole('button', { name: 'Ask Patient360' })).not.toBeInTheDocument();

    cleanup();
    await renderShell(
      sessionMe('dietary_staff', ['diet', 'allergies_food', 'ask'], {
        user_id: 'u_lindqvist',
        display: 'Tomas Lindqvist'
      }),
      '/patients/p_101/diet'
    );
    expect(screen.queryByRole('button', { name: 'Ask Patient360' })).not.toBeInTheDocument();

    cleanup();
    await renderShell(sessionMe('researcher', ['aggregate', 'ask'], { user_id: 'u_nair', display: 'Priya Nair' }));
    expect(screen.queryByRole('button', { name: 'Ask Patient360' })).not.toBeInTheDocument();

    cleanup();
    await renderShell(
      sessionMe('attending', ['labs', 'ask'], {
        user_id: 'u_chen',
        display: 'Dr. Sarah Chen',
        session: { expires_at: '', absolute_expires_at: '', auth_level: 2, on_duty: false }
      }),
      '/patients/p_101/overview'
    );
    expect(screen.queryByRole('button', { name: 'Ask Patient360' })).not.toBeInTheDocument();
  });

  it('collapses and expands the primary sidebar and remembers the choice', async () => {
    const { container } = await renderShell(sessionMe('attending', ['labs', 'ask'], {
      user_id: 'u_chen',
      display: 'Dr. Sarah Chen'
    }));

    expect(container.querySelector('.shell--nav-collapsed')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Patients' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Collapse sidebar' })).toBeInTheDocument();

    await fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
    expect(container.querySelector('.shell--nav-collapsed')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Expand sidebar' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Patients' })).toBeInTheDocument();
    expect(localStorage.getItem('patient360.navCollapsed')).toBe('1');

    await fireEvent.click(screen.getByRole('button', { name: 'Expand sidebar' }));
    expect(container.querySelector('.shell--nav-collapsed')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Collapse sidebar' })).toBeInTheDocument();
    expect(localStorage.getItem('patient360.navCollapsed')).toBe('0');

    cleanup();
    localStorage.setItem('patient360.navCollapsed', '1');
    const restored = await renderShell(sessionMe('attending', ['labs', 'ask'], {
      user_id: 'u_chen',
      display: 'Dr. Sarah Chen'
    }));
    expect(restored.container.querySelector('.shell--nav-collapsed')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Expand sidebar' })).toBeInTheDocument();
  });
});
