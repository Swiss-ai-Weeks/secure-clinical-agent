import { render, screen } from '@testing-library/vue';
import { createPinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import OhifView from '../../src/features/patient360/OhifView.vue';

const signMedia = vi.fn();

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    signMedia: (...args: unknown[]) => signMedia(...args)
  }
}));

async function renderViewer() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/patients/:patientId/imaging', name: 'patient-imaging', component: { template: '<div />' } },
      { path: '/patients/:patientId/imaging/viewer', name: 'patient-ohif', component: OhifView }
    ]
  });
  await router.push({ path: '/patients/p_101/imaging/viewer', query: { study: 'study-1' } });
  await router.isReady();
  return render(OhifView, { global: { plugins: [router, createPinia()] } });
}

describe('OhifView', () => {
  afterEach(() => {
    signMedia.mockReset();
    sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it('iframes OHIF with the signed study UID', async () => {
    signMedia.mockResolvedValue({
      url: '/media/signed-token/study-1',
      expires_in: 300,
      jti: 'j',
      audit_id: 'a',
      study_instance_uid: '1.2.840.study'
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }));
    await renderViewer();
    expect(await screen.findByText(/segmentation panel/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to imaging' })).toHaveAttribute('href', '/patients/p_101/imaging');
    const frame = await screen.findByTitle('OHIF study viewer');
    expect(frame).toHaveAttribute('src', '/ohif/viewer?StudyInstanceUIDs=1.2.840.study');
    expect(sessionStorage.getItem('p360.dicomweb')).toBe('/api/media/signed-token/dicom-web');
  });

  it('says so when the study UID is missing', async () => {
    signMedia.mockResolvedValue({
      url: '/media/signed-token/study-1',
      expires_in: 300,
      jti: 'j',
      audit_id: 'a'
    });
    await renderViewer();
    expect(await screen.findByText('No signed DICOM study UID is stored for this study.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to imaging' })).toHaveAttribute('href', '/patients/p_101/imaging');
    expect(screen.queryByTitle('OHIF study viewer')).not.toBeInTheDocument();
  });
});
