import { render, screen } from '@testing-library/vue';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';
import CohortInsightsView from '../../src/features/clinic/CohortInsightsView.vue';
import { useSessionStore } from '../../src/stores/useSessionStore';

const query = vi.fn();

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    query: (...args: unknown[]) => query(...args)
  }
}));

describe('CohortInsightsView', () => {
  it('shows condition names instead of raw dim JSON', async () => {
    query.mockResolvedValue({
      rows: [
        { dims: { code: '44054006' }, display: 'Type 2 diabetes mellitus', count: 1, suppressed: false },
        { dims: { code: '195967001' }, count: 1, suppressed: false }
      ],
      row_count: 2,
      suppressed_cells: 0,
      obligations: {}
    });
    const pinia = createPinia();
    setActivePinia(pinia);
    const session = useSessionStore();
    session.me = {
      user_id: 'u_chen',
      display: 'Dr. Sarah Chen',
      role: 'attending',
      department: 'internal-medicine',
      credential_level: 2,
      self_patient_id: null,
      datasets: ['conditions'],
      panels: ['aggregate_own_patients'],
      policy_version: 'test',
      session: { expires_at: '', absolute_expires_at: '', auth_level: 2, on_duty: true }
    };
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/cohort', component: CohortInsightsView }]
    });
    await router.push('/cohort');
    await router.isReady();
    render(CohortInsightsView, { global: { plugins: [router, pinia] } });

    expect(await screen.findByText('Type 2 diabetes mellitus')).toBeInTheDocument();
    expect(screen.getByText('Asthma')).toBeInTheDocument();
    expect(screen.getByText('44054006')).toBeInTheDocument();
    expect(screen.queryByText(/\{"code":/)).not.toBeInTheDocument();
  });
});
