import { render, screen } from '@testing-library/vue';
import { createPinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import DocumentsView from '../../src/features/patient360/DocumentsView.vue';

const getPatient = vi.fn();
const uploadDocument = vi.fn();

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    getPatient: () => getPatient(),
    uploadDocument: (patientId: string, file: File) => uploadDocument(patientId, file)
  }
}));

afterEach(() => {
  getPatient.mockReset();
  uploadDocument.mockReset();
});

async function renderDocuments() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/patients/:patientId/documents', component: DocumentsView }]
  });
  await router.push('/patients/p_101/documents');
  await router.isReady();
  return render(DocumentsView, { global: { plugins: [router, createPinia()] } });
}

describe('DocumentsView', () => {
  it('hides upload when notes for this chart are not granted', async () => {
    getPatient.mockResolvedValue({ documents: [], canUpload: false });
    await renderDocuments();
    expect(await screen.findByText('No uploaded or imaging documents are visible.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Upload document')).not.toBeInTheDocument();
  });

  it('shows upload when notes for this chart are granted', async () => {
    getPatient.mockResolvedValue({ documents: [], canUpload: true });
    await renderDocuments();
    expect(await screen.findByLabelText('Upload document')).toBeInTheDocument();
  });

  it('says a safety block was not added to the chart', async () => {
    getPatient.mockResolvedValue({ documents: [], canUpload: true });
    uploadDocument.mockResolvedValue({
      documentId: 'quarantine/p_101/note.txt',
      status: 'quarantine',
      reason: 'content_safety'
    });
    await renderDocuments();
    const input = await screen.findByLabelText('Upload document');
    const file = new File(['unsafe'], 'note.txt', { type: 'text/plain' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    input.dispatchEvent(new Event('change', { bubbles: true }));
    expect(await screen.findByText('note.txt was blocked and was not added to the chart.')).toBeInTheDocument();
  });
});
