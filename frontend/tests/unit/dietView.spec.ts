import { render, screen } from '@testing-library/vue';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';
import DietView from '../../src/features/patient360/DietView.vue';
import { useSessionStore } from '../../src/stores/useSessionStore';

const query = vi.fn();

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    query: (...args: unknown[]) => query(...args)
  }
}));

describe('DietView', () => {
  it('loads diet and the food-allergy dataset for dietary staff', async () => {
    query.mockImplementation(async (dataset: string) => {
      if (dataset === 'diet') return { rows: [{ cite_id: 'diet1', ward: 'w_3b', diet_codes: ['low-salt'] }] };
      if (dataset === 'allergies') return { rows: [{ cite_id: 'alg1', display: 'Peanut' }] };
      throw new Error(`unexpected dataset ${dataset}`);
    });
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
      datasets: ['diet', 'allergies'],
      panels: ['diet', 'allergies_food', 'aggregate_ward', 'ask'],
      policy_version: 'test',
      session: { expires_at: '', absolute_expires_at: '', auth_level: 2, on_duty: true }
    };
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/patients/:patientId/diet', component: DietView }]
    });
    await router.push('/patients/p_101/diet');
    await router.isReady();
    render(DietView, { global: { plugins: [router, pinia] } });

    expect(await screen.findByText(/Ward w_3b · low salt/)).toBeInTheDocument();
    expect(screen.getByText('Peanut')).toBeInTheDocument();
    expect(screen.getByText('Food allergies')).toBeInTheDocument();
    expect(query).toHaveBeenCalledWith('diet', { patient_key: 'p_101' });
    expect(query).toHaveBeenCalledWith('allergies', { patient_key: 'p_101' });
  });

  it('states when a chart has no diet order and no known allergies', async () => {
    query.mockResolvedValue({ rows: [] });
    const pinia = createPinia();
    setActivePinia(pinia);
    const session = useSessionStore();
    session.me = {
      user_id: 'u_chen',
      display: 'Dr Chen',
      role: 'attending',
      department: null,
      credential_level: 2,
      self_patient_id: null,
      datasets: ['diet', 'allergies'],
      panels: ['diet', 'allergies', 'labs'],
      policy_version: 'test',
      session: { expires_at: '', absolute_expires_at: '', auth_level: 2, on_duty: true }
    };
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/patients/:patientId/diet', component: DietView }]
    });
    await router.push('/patients/p_485ba8c8597d4c5cb0fbda55317119a3/diet');
    await router.isReady();
    render(DietView, { global: { plugins: [router, pinia] } });

    expect(await screen.findByText(/No diet order on this chart/)).toBeInTheDocument();
    expect(screen.getByText('No known allergies.')).toBeInTheDocument();
  });
});
