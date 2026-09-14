import { render, screen } from '@testing-library/vue';
import { createPinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it } from 'vitest';
import PatientOverviewView from '../../src/features/patient360/PatientOverviewView.vue';

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/patients/:patientId/overview', component: PatientOverviewView }]
});

describe('PatientOverviewView', () => {
  it('surfaces the Patient 360 five-second context', async () => {
    await router.push('/patients/emma-laurent/overview');
    await router.isReady();

    render(PatientOverviewView, { global: { plugins: [router, createPinia()] } });

    expect(await screen.findByText('Emma Laurent')).toBeInTheDocument();
    expect(screen.getByText('Penicillin')).toBeInTheDocument();
    expect(screen.getByText('✦ Clinical Brief')).toBeInTheDocument();
    expect(screen.getByText('Since your last consultation')).toBeInTheDocument();
    expect(screen.getByText('LDL cholesterol')).toBeInTheDocument();
  });
});
