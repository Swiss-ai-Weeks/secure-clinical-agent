import { render, screen } from '@testing-library/vue';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';
import ImagingView from '../../src/features/patient360/ImagingView.vue';
import { useSessionStore } from '../../src/stores/useSessionStore';

const imaging = vi.fn();
const reprocessStudy = vi.fn();

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    imaging: (...args: unknown[]) => imaging(...args),
    reprocessStudy: (...args: unknown[]) => reprocessStudy(...args)
  }
}));

async function renderImaging() {
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
    datasets: [],
    panels: ['imaging'],
    policy_version: 'test',
    session: { expires_at: '', absolute_expires_at: '', auth_level: 2, on_duty: true }
  };
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/patients/:patientId/imaging', component: ImagingView },
      { path: '/patients/:patientId/imaging/viewer', name: 'patient-ohif', component: { template: '<div />' } }
    ]
  });
  await router.push('/patients/p_101/imaging');
  await router.isReady();
  return render(ImagingView, { global: { plugins: [router, pinia] } });
}

describe('ImagingView', () => {
  it('opens a study in the OHIF route instead of the PNG previewer', async () => {
    imaging.mockResolvedValue({
      studies: [{
        cite_id: 'study-1',
        procedure_display: 'Chest X-ray',
        modality: 'CR',
        orthanc_id: 'orthanc-study-1',
        instance_count: 1
      }],
      reports: []
    });
    await renderImaging();
    const link = await screen.findByRole('link', { name: 'Open in viewer: Chest X-ray' });
    expect(link).toHaveAttribute('href', '/patients/p_101/imaging/viewer?study=orthanc-study-1');
    expect(screen.queryByRole('button', { name: /View full image|Open signed copy/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reprocess CT' })).not.toBeInTheDocument();
  });

  it('offers Reprocess CT only on CT studies', async () => {
    imaging.mockResolvedValue({
      studies: [{
        cite_id: 'study-ct',
        procedure_display: 'CT Chest',
        modality: 'CT',
        orthanc_id: 'orthanc-ct',
        instance_count: 16
      }],
      reports: []
    });
    await renderImaging();
    expect(await screen.findByRole('button', { name: 'Reprocess CT' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open in viewer: CT Chest' })).toBeInTheDocument();
  });
});
