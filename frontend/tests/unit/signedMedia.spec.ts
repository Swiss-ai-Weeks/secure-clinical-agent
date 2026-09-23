import { fireEvent, render, screen, waitFor } from '@testing-library/vue';
import { createMemoryHistory, createRouter } from 'vue-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SignedMediaButton from '../../src/components/ui/SignedMediaButton.vue';
import { presentSignedMedia } from '../../src/services/signedMedia';

const signMedia = vi.fn();
const fetchMedia = vi.fn();

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    signMedia: (...args: unknown[]) => signMedia(...args),
    fetchMedia: (...args: unknown[]) => fetchMedia(...args)
  }
}));

function latin1(bytes: number[]): string {
  return String.fromCharCode(...bytes);
}

const png = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

async function renderButton(props: Record<string, unknown>) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/patients/:patientId/imaging/viewer', name: 'patient-ohif', component: { template: '<div>ohif</div>' } }
    ]
  });
  await router.push('/');
  await router.isReady();
  const view = render(SignedMediaButton, { props, global: { plugins: [router] } });
  return { ...view, router };
}

describe('presentSignedMedia', () => {
  it('treats the media payload as Latin-1 bytes and recognizes a PNG preview', () => {
    const opened = presentSignedMedia({ bytes_b64: latin1(png), length: png.length });
    expect(opened.kind).toBe('image');
    expect(opened.mime).toBe('image/png');
    expect([...opened.bytes]).toEqual(png);
  });

  it('shows a stored report as text', () => {
    const report = 'No acute cardiopulmonary process.';
    const opened = presentSignedMedia({ bytes_b64: report, length: report.length });
    expect(opened.kind).toBe('text');
    expect(opened.text).toBe(report);
  });
});

describe('SignedMediaButton', () => {
  beforeEach(() => {
    signMedia.mockReset();
    fetchMedia.mockReset();
  });

  it('opens a DICOM study in the OHIF route instead of the PNG dialog', async () => {
    const { router } = await renderButton({ patientKey: 'p_101', studyId: 'study-1', label: 'Chest X-ray' });

    await fireEvent.click(screen.getByRole('button', { name: 'Open signed copy' }));

    await waitFor(() => expect(router.currentRoute.value.name).toBe('patient-ohif'));
    expect(router.currentRoute.value.query.study).toBe('study-1');
    expect(signMedia).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('keeps long text inside a scrollable body instead of widening the sheet', async () => {
    const report = `Impression: ${'pneumonia-follow-up-note-'.repeat(40)}`;
    signMedia.mockResolvedValue({ url: '/media/token/note-1', expires_in: 300, jti: 'j', audit_id: 'a' });
    fetchMedia.mockResolvedValue({ study_uid: 'note-1', bytes_b64: report, length: report.length });
    const { container } = await renderButton({
      patientKey: 'p_101',
      objectKey: 'notes/p_101/long.pdf',
      label: 'Consult note'
    });

    await fireEvent.click(screen.getByRole('button', { name: 'Open signed copy' }));

    const body = container.querySelector('.sheet__body') as HTMLElement;
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(body).toBeTruthy();
    expect(container.querySelector('.sheet__header')).toBeTruthy();
    expect(body.querySelector('pre')?.textContent).toContain('Impression:');
    expect(body.querySelector('pre')?.textContent?.length).toBeGreaterThan(200);
  });

  it('sends a study row to the viewer without a list preview image', async () => {
    const { container, router } = await renderButton({
      patientKey: 'p_101',
      studyId: 'study-1',
      label: 'Chest X-ray',
      variant: 'thumbnail',
      eyebrow: 'CR'
    });

    const row = await screen.findByRole('button', { name: 'Open in viewer: Chest X-ray' });
    expect(container.querySelector('.study-row img')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText('CR')).toBeInTheDocument();
    expect(screen.getByText('Open in viewer')).toBeInTheDocument();

    await fireEvent.click(row);

    await waitFor(() => expect(router.currentRoute.value.name).toBe('patient-ohif'));
    expect(router.currentRoute.value.query.study).toBe('study-1');
    expect(container.querySelector('dialog[open]')).toBeNull();
    expect(signMedia).not.toHaveBeenCalled();
  });
});
