import { render, screen } from '@testing-library/vue';
import { createPinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';
import PatientOverviewView from '../../src/features/patient360/PatientOverviewView.vue';
import { mockApi } from '../../src/services/mockApi';

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    getPatient: (id: string) => mockApi.getPatient(id)
  }
}));

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/patients/:patientId/overview', component: PatientOverviewView }]
});

describe('PatientOverviewView', () => {
  it('surfaces the Patient 360 five-second context', async () => {
    await router.push('/patients/p_101/overview');
    await router.isReady();

    render(PatientOverviewView, { global: { plugins: [router, createPinia()] } });

    expect(await screen.findByText('Elisabeth Keller')).toBeInTheDocument();
    expect(screen.getAllByText(/Penicillin/).length).toBeGreaterThan(0);
    expect(screen.getByText('✦ Clinical Brief')).toBeInTheDocument();
    expect(screen.getByText('Since your last consultation')).toBeInTheDocument();
    expect(screen.getByText('HbA1c')).toBeInTheDocument();
  });
});
