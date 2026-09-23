import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/vue';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import AskPatient360Panel from '../../src/components/layout/AskPatient360Panel.vue';
import { useSessionStore } from '../../src/stores/useSessionStore';
import { useUiStore } from '../../src/stores/useUiStore';
import type { Me } from '../../src/types/api';
import type { AiAnswer } from '../../src/types/patient360';

const askPatient360 = vi.fn();
const uploadDocument = vi.fn();
const chatSandbox = vi.fn(async () => ({ active: false }));
async function chartHeader(): Promise<{ fullName: string; avatarInitials: string; canUpload: boolean }> {
  return { fullName: 'Elisabeth Keller', avatarInitials: 'EK', canUpload: false };
}
const getPatient = vi.fn(chartHeader);

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    getPatient: () => getPatient(),
    askPatient360: (request: unknown) => askPatient360(request),
    chatSandbox: () => chatSandbox(),
    uploadDocument: (patientId: string, file: File) => uploadDocument(patientId, file)
  }
}));

afterEach(() => {
  cleanup();
  askPatient360.mockReset();
  uploadDocument.mockReset();
  chatSandbox.mockReset();
  chatSandbox.mockResolvedValue({ active: false });
  getPatient.mockReset();
  getPatient.mockImplementation(chartHeader);
});

const attendingPanels = [
  'labs',
  'conditions',
  'meds',
  'encounters',
  'allergies',
  'diet',
  'notes',
  'imaging',
  'ask'
];

function sessionMe(panels: string[] = attendingPanels): Me {
  return {
    user_id: 'u_chen',
    display: 'Dr. Sarah Chen',
    role: 'attending',
    department: null,
    credential_level: 2,
    self_patient_id: null,
    datasets: [],
    panels,
    policy_version: 'test',
    session: { expires_at: '', absolute_expires_at: '', auth_level: 2, on_duty: true }
  };
}

const STARTER = 'What changed with this patient since the last visit?';

async function submitAsk(text = STARTER) {
  await fireEvent.update(screen.getByLabelText('Question'), text);
  await fireEvent.click(screen.getByRole('button', { name: 'Ask with sources' }));
}

async function openPanel(panels: string[] = attendingPanels) {
  const pinia = createPinia();
  setActivePinia(pinia);
  useSessionStore().me = sessionMe(panels);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/patients/:patientId/overview', component: { template: '<div />' } },
      { path: '/patients/:patientId/notes', component: { template: '<div />' } }
    ]
  });
  await router.push('/patients/p_101/overview');
  await router.isReady();
  const ui = useUiStore();
  ui.openAskPanel('p_101');
  const view = render(AskPatient360Panel, { global: { plugins: [pinia, router] } });
  return { ui, router, ...view };
}

const unusedLabs: AiAnswer['citations'] = [
  { id: 'obs_co2', label: 'Carbon dioxide, total', sourceId: 'obs_co2', sourceType: 'lab' },
  { id: 'obs_sbp', label: 'Systolic BP', sourceId: 'obs_sbp', sourceType: 'lab' },
  { id: 'cond_1', label: 'Prediabetes (finding)', sourceId: 'cond_1', sourceType: 'condition' }
];

describe('AskPatient360Panel', () => {
  it('shows the open chart instead of a generic context label', async () => {
    await openPanel();
    expect(await screen.findByRole('heading', { name: 'Elisabeth Keller' })).toBeInTheDocument();
    expect(screen.queryByText('Patient context active')).not.toBeInTheDocument();
  });

  it('does not dump unused retrieved labs under a no-evidence answer', async () => {
    askPatient360.mockResolvedValue({
      id: 'a1',
      answer: 'There is no authorized evidence about a patient named Elizabeth.',
      citations: unusedLabs,
      retrievalSteps: ['Minted run token', 'Searched authorized structured rows'],
      refused: false
    } satisfies AiAnswer);

    await openPanel();
    await screen.findByRole('heading', { name: 'Elisabeth Keller' });
    await submitAsk('tell me about the patient elizabeth');

    expect(await screen.findByText(/no authorized evidence about a patient named Elizabeth/i)).toBeInTheDocument();
    expect(screen.getByText('No matching evidence')).toBeInTheDocument();
    expect(screen.queryByText('Carbon dioxide, total')).not.toBeInTheDocument();
    expect(screen.queryByText('Systolic BP')).not.toBeInTheDocument();
    expect(screen.queryByText('Prediabetes (finding)')).not.toBeInTheDocument();
    expect(screen.queryByText('Minted run token')).not.toBeInTheDocument();
  });

  it('renders a cited lab summary without raw markdown or cite ids', async () => {
    askPatient360.mockResolvedValue({
      id: 'a3',
      answer: '**Latest laboratory results** - Creatinine: **1.35 mg/dL** [obs_5996ca9ce86b461e]',
      citations: [{ id: 'obs_5996ca9ce86b461e', label: 'Creatinine', sourceId: 'obs_5996ca9ce86b461e', sourceType: 'lab' }],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false
    } satisfies AiAnswer);

    await openPanel();
    await submitAsk();

    expect(await screen.findByText('Latest laboratory results')).toBeInTheDocument();
    expect(screen.getByText('1.35 mg/dL')).toBeInTheDocument();
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument();
    expect(screen.queryByText(/obs_5996/)).not.toBeInTheDocument();
  });

  it('hides a leaked patient-key cite and one chip per measurement', async () => {
    askPatient360.mockResolvedValue({
      id: 'a4',
      answer:
        'Systolic BP: 130 mmHg [obs_1], 127 mmHg [obs_2]. Historical pneumonia resolved [p_485ba8c8597d4c5cb0fbda55317119a3-historical-pneumonia].',
      citations: [
        { id: 'obs_1', label: 'Systolic BP', sourceId: 'obs_1', sourceType: 'lab' },
        { id: 'obs_2', label: 'Systolic BP', sourceId: 'obs_2', sourceType: 'lab' }
      ],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false
    } satisfies AiAnswer);

    await openPanel();
    await submitAsk();

    expect(await screen.findByText('Sources used')).toBeInTheDocument();
    expect(screen.queryByText(/p_485b/)).not.toBeInTheDocument();
    expect(screen.queryByText(/did not cite a specific lab/)).not.toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Sources used' })).getAllByRole('button', { name: /Systolic BP/ })).toHaveLength(1);
  });

  it('shows an identity answer without clinical source chips', async () => {
    askPatient360.mockResolvedValue({
      id: 'a5',
      answer: 'This open chart is Maria Santos [identity_banner].\n67 years · born 23 Jul 1958 · female · MRN-4471904 [identity_banner].',
      citations: [
        { id: 'identity_banner', label: 'Identity banner', sourceId: 'identity_banner', sourceType: 'identity' },
        { id: 'cond_hl', label: 'Hyperlipidemia', sourceId: 'cond_hl', sourceType: 'condition' },
        { id: 'obs_chol', label: 'Cholesterol', sourceId: 'obs_chol', sourceType: 'lab' }
      ],
      retrievalSteps: ['Read authorized identity banner'],
      refused: false
    } satisfies AiAnswer);

    await openPanel();
    await fireEvent.update(screen.getByLabelText('Question'), 'whos this person');
    await fireEvent.click(screen.getByRole('button', { name: 'Ask with sources' }));

    expect(await screen.findByText(/This open chart is Maria Santos/)).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Sources used' })).getByRole('button', { name: /Identity banner/ })).toBeInTheDocument();
    expect(screen.queryByText('Hyperlipidemia')).not.toBeInTheDocument();
    expect(screen.queryByText('Cholesterol')).not.toBeInTheDocument();
  });

  it('shows condition chips for cite-colon marks', async () => {
    const { router } = await openPanel();
    askPatient360.mockResolvedValue({
      id: 'a-cond',
      answer: 'Prediabetes (code 714628002) [cite:cond_327de270fac646d2].',
      citations: [
        {
          id: 'cond_327de270fac646d2',
          label: 'Prediabetes',
          sourceId: 'cond_327de270fac646d2',
          sourceType: 'condition'
        }
      ],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false
    } satisfies AiAnswer);

    await submitAsk('/conditions');

    expect(await screen.findByText('Sources used')).toBeInTheDocument();
    expect(screen.queryByText(/did not cite a specific lab/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\[cite:cond_/)).not.toBeInTheDocument();
    await fireEvent.click(screen.getByRole('button', { name: 'Open Prediabetes' }));
    expect(router.currentRoute.value.path).toBe('/patients/p_101/overview');
  });

  it('shows only sources the answer cited', async () => {
    askPatient360.mockResolvedValue({
      id: 'a2',
      answer: 'HbA1c is 6.98% [obs_a1].',
      citations: [
        { id: 'obs_a1', label: 'HbA1c', sourceId: 'obs_a1', sourceType: 'lab' },
        ...unusedLabs
      ],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false
    } satisfies AiAnswer);

    await openPanel();
    await submitAsk();

    expect(await screen.findByText('Sources used')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Sources used' })).getByRole('button', { name: /HbA1c/ })).toBeInTheDocument();
    expect(screen.queryByText('Carbon dioxide, total')).not.toBeInTheDocument();
  });

  it('does not call a NemoClaw outage an authorization miss', async () => {
    askPatient360.mockResolvedValue({
      id: 'a6',
      answer: 'NemoClaw was unavailable. No substitute answer was used.',
      citations: unusedLabs,
      retrievalSteps: ['NemoClaw unavailable'],
      policy_reason: 'nemoclaw_unavailable',
      refused: true
    } satisfies AiAnswer);

    await openPanel();
    await submitAsk();

    expect(await screen.findByText('Assistant unavailable')).toBeInTheDocument();
    expect(screen.getByText('The clinical assistant did not complete this turn')).toBeInTheDocument();
    expect(screen.getAllByText('NemoClaw was unavailable. No substitute answer was used.')).toHaveLength(1);
    expect(screen.queryByText('Nothing authorized for that question')).not.toBeInTheDocument();
    expect(screen.queryByText('No matching evidence')).not.toBeInTheDocument();
    expect(screen.getByText(/No substitute answer was used, so there are no source chips/)).toBeInTheDocument();
  });

  it('can retry an unavailable turn and display its cited answer', async () => {
    askPatient360.mockResolvedValueOnce({
      id: 'failed',
      answer: 'NemoClaw was unavailable. No substitute answer was used.',
      citations: [],
      retrievalSteps: ['NemoClaw sandbox setup failed', 'NemoClaw unavailable'],
      policy_reason: 'nemoclaw_unavailable',
      refused: true
    } satisfies AiAnswer).mockResolvedValueOnce({
      id: 'recovered',
      answer: 'The latest note describes resolved pneumonia [note_latest].',
      citations: [{ id: 'note_latest', label: 'Latest note', sourceId: 'note_latest', sourceType: 'note' }],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false
    } satisfies AiAnswer);

    await openPanel();
    await fireEvent.update(screen.getByLabelText('Question'), 'Summarize the latest note');
    await fireEvent.click(screen.getByRole('button', { name: 'Ask with sources' }));
    expect(await screen.findByText('Assistant unavailable')).toBeInTheDocument();
    expect(screen.getByText('Assistant setup failed')).toBeInTheDocument();

    await fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    const sources = await screen.findByRole('region', { name: 'Sources used' });
    expect(within(sources).getByRole('button', { name: /Latest note/ })).toBeInTheDocument();
    expect(screen.getByText(/The latest note describes resolved pneumonia/)).toBeInTheDocument();
    expect(screen.getByText('Assistant unavailable')).toBeInTheDocument();
    expect(askPatient360).toHaveBeenLastCalledWith(expect.objectContaining({
      question: 'Summarize the latest note',
      history: [{ role: 'user', content: 'Summarize the latest note' }]
    }));
    expect(screen.getAllByText('Summarize the latest note')).toHaveLength(2);
  });

  it('retries a request that never returned an answer', async () => {
    askPatient360.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce({
      id: 'recovered',
      answer: 'HbA1c is 6.98% [obs_a1].',
      citations: [{ id: 'obs_a1', label: 'HbA1c', sourceId: 'obs_a1', sourceType: 'lab' }],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false
    } satisfies AiAnswer);

    await openPanel();
    await fireEvent.update(screen.getByLabelText('Question'), 'Summarize the latest labs');
    await fireEvent.click(screen.getByRole('button', { name: 'Ask with sources' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Ask failed');
    expect(screen.getAllByText('Summarize the latest labs')).toHaveLength(1);

    await fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText(/HbA1c is 6.98%/)).toBeInTheDocument();
    expect(screen.getAllByText('Summarize the latest labs')).toHaveLength(1);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(askPatient360).toHaveBeenLastCalledWith(expect.objectContaining({
      question: 'Summarize the latest labs',
      history: []
    }));
  });

  it('keeps a follow-up under the first answer and sends that history', async () => {
    askPatient360.mockResolvedValueOnce({
      id: 'a1',
      answer: 'HbA1c is 6.98% [obs_a1].',
      citations: [{ id: 'obs_a1', label: 'HbA1c', sourceId: 'obs_a1', sourceType: 'lab' }],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false
    } satisfies AiAnswer).mockResolvedValueOnce({
      id: 'a2',
      answer: 'The dose is 5 mg [med_1].',
      citations: [{ id: 'med_1', label: 'Metformin', sourceId: 'med_1', sourceType: 'medication' }],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false
    } satisfies AiAnswer);

    const { ui } = await openPanel();
    await submitAsk();
    expect(await screen.findByText(/HbA1c is 6.98%/)).toBeInTheDocument();

    await fireEvent.update(screen.getByLabelText('Question'), 'What about the dose?');
    await fireEvent.click(screen.getByRole('button', { name: 'Ask with sources' }));
    expect(await screen.findByText(/The dose is 5 mg/)).toBeInTheDocument();
    expect(screen.getByText(/HbA1c is 6.98%/)).toBeInTheDocument();
    expect(askPatient360).toHaveBeenLastCalledWith(expect.objectContaining({
      question: 'What about the dose?',
      patientId: 'p_101',
      history: [
        { role: 'user', content: 'What changed with this patient since the last visit?' },
        { role: 'assistant', content: 'HbA1c is 6.98% [obs_a1].' }
      ]
    }));

    ui.closeAskPanel();
    await waitFor(() => {
      expect(screen.queryByRole('complementary', { name: 'Ask Patient360' })).not.toBeInTheDocument();
    });
    ui.openAskPanel('p_101');
    expect(await screen.findByText(/HbA1c is 6.98%/)).toBeInTheDocument();

    ui.openAskPanel('p_102');
    await waitFor(() => {
      expect(screen.queryByText(/HbA1c is 6.98%/)).not.toBeInTheDocument();
    });
    expect(screen.queryByText(/The dose is 5 mg/)).not.toBeInTheDocument();
  });

  it('starts a new chat for this chart and leaves the next question without history', async () => {
    let releasePending: (answer: AiAnswer) => void = () => {};
    askPatient360
      .mockResolvedValueOnce({
        id: 'a1',
        answer: 'HbA1c is 6.98% [obs_a1].',
        citations: [{ id: 'obs_a1', label: 'HbA1c', sourceId: 'obs_a1', sourceType: 'lab' }],
        retrievalSteps: ['OpenShell sandbox turn'],
        refused: false
      } satisfies AiAnswer)
      .mockImplementationOnce(
        () =>
          new Promise(resolve => {
            releasePending = resolve;
          })
      )
      .mockResolvedValueOnce({
        id: 'a3',
        answer: 'Creatinine is 1.1 mg/dL [obs_cr].',
        citations: [{ id: 'obs_cr', label: 'Creatinine', sourceId: 'obs_cr', sourceType: 'lab' }],
        retrievalSteps: ['OpenShell sandbox turn'],
        refused: false
      } satisfies AiAnswer);

    const { ui } = await openPanel();
    expect(screen.getByRole('button', { name: 'New chat' })).toBeDisabled();
    await submitAsk();
    expect(await screen.findByText(/HbA1c is 6.98%/)).toBeInTheDocument();

    await fireEvent.click(screen.getByRole('button', { name: 'New chat' }));
    expect(screen.queryByText(/HbA1c is 6.98%/)).not.toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Suggested prompts' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'New chat' })).toBeDisabled();

    await fireEvent.update(screen.getByLabelText('Question'), 'What about the dose?');
    await fireEvent.click(screen.getByRole('button', { name: 'Ask with sources' }));
    expect(await screen.findByText('Working on a cited answer…')).toBeInTheDocument();
    await fireEvent.click(screen.getByRole('button', { name: 'New chat' }));
    releasePending({
      id: 'a2',
      answer: 'The dose is 5 mg [med_1].',
      citations: [{ id: 'med_1', label: 'Metformin', sourceId: 'med_1', sourceType: 'medication' }],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false
    });
    await waitFor(() => {
      expect(screen.queryByText('Working on a cited answer…')).not.toBeInTheDocument();
    });
    expect(screen.queryByText(/The dose is 5 mg/)).not.toBeInTheDocument();
    expect(screen.queryByText('What about the dose?')).not.toBeInTheDocument();

    await fireEvent.update(screen.getByLabelText('Question'), 'Summarize the latest labs');
    await fireEvent.click(screen.getByRole('button', { name: 'Ask with sources' }));
    expect(await screen.findByText(/Creatinine is 1.1 mg\/dL/)).toBeInTheDocument();
    expect(askPatient360).toHaveBeenLastCalledWith(expect.objectContaining({
      question: 'Summarize the latest labs',
      patientId: 'p_101',
      history: []
    }));

    ui.openAskPanel('p_102');
    ui.openAskPanel('p_101');
    expect(await screen.findByText(/Creatinine is 1.1 mg\/dL/)).toBeInTheDocument();
  });

  it('hides document upload unless this chart grants notes', async () => {
    await openPanel();
    expect(await screen.findByRole('heading', { name: 'Elisabeth Keller' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Upload document')).not.toBeInTheDocument();
  });

  it('adds an uploaded note to the thread without sending the file to Ask', async () => {
    getPatient.mockResolvedValue({ fullName: 'Elisabeth Keller', avatarInitials: 'EK', canUpload: true });
    uploadDocument.mockResolvedValue({ documentId: 'notes/p_101/note.txt', status: 'processed' });

    await openPanel();
    const input = await screen.findByLabelText('Upload document');
    const file = new File(['Blood pressure log'], 'note.txt', { type: 'text/plain' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    input.dispatchEvent(new Event('change', { bubbles: true }));

    expect(uploadDocument).not.toHaveBeenCalled();
    expect(await screen.findByText('note.txt')).toBeInTheDocument();
    await fireEvent.update(screen.getByLabelText('Question'), '');
    await fireEvent.click(screen.getByRole('button', { name: 'Ask with sources' }));

    expect(await screen.findByText('note.txt is on this chart.')).toBeInTheDocument();
    expect(uploadDocument).toHaveBeenCalledWith('p_101', file);
    expect(askPatient360).not.toHaveBeenCalled();
  });

  it('tells the user a safety block is not allowed', async () => {
    askPatient360.mockResolvedValue({
      id: 'a7',
      answer: 'This is not allowed.',
      citations: unusedLabs,
      retrievalSteps: ['Input rail blocked the question'],
      policy_reason: 'content_safety',
      refused: true
    } satisfies AiAnswer);

    await openPanel();
    await submitAsk();

    expect(await screen.findByText('Not allowed')).toBeInTheDocument();
    expect(screen.getByText('This is not allowed.')).toBeInTheDocument();
    expect(screen.queryByText('Nothing authorized for that question')).not.toBeInTheDocument();
    expect(screen.queryByText('No matching evidence')).not.toBeInTheDocument();
    expect(screen.queryByText('Carbon dioxide, total')).not.toBeInTheDocument();
    expect(screen.queryByText(/Authorized records were searched/)).not.toBeInTheDocument();
  });

  it('says a safety block was not added to the chart', async () => {
    getPatient.mockResolvedValue({ fullName: 'Elisabeth Keller', avatarInitials: 'EK', canUpload: true });
    uploadDocument.mockResolvedValue({
      documentId: 'quarantine/p_101/note.txt',
      status: 'quarantine',
      reason: 'content_safety'
    });

    await openPanel();
    const input = await screen.findByLabelText('Upload document');
    const file = new File(['unsafe'], 'note.txt', { type: 'text/plain' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    input.dispatchEvent(new Event('change', { bubbles: true }));
    await fireEvent.update(screen.getByLabelText('Question'), '');
    await fireEvent.click(screen.getByRole('button', { name: 'Ask with sources' }));

    expect(await screen.findByText('note.txt was blocked and was not added to the chart.')).toBeInTheDocument();
  });

  it('returns to an earlier chat while that sandbox is still active', async () => {
    chatSandbox.mockResolvedValue({ active: true, stamp: 'live' });
    askPatient360.mockResolvedValueOnce({
      id: 'a1',
      answer: 'HbA1c is 6.98% [obs_a1].',
      citations: [{ id: 'obs_a1', label: 'HbA1c', sourceId: 'obs_a1', sourceType: 'lab' }],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false,
      sandboxStamp: 'live'
    } satisfies AiAnswer).mockResolvedValueOnce({
      id: 'a2',
      answer: 'The dose is 5 mg [med_1].',
      citations: [{ id: 'med_1', label: 'Metformin', sourceId: 'med_1', sourceType: 'medication' }],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false,
      sandboxStamp: 'live'
    } satisfies AiAnswer);

    const { ui } = await openPanel();
    await submitAsk();
    expect(await screen.findByText(/HbA1c is 6.98%/)).toBeInTheDocument();

    await fireEvent.click(screen.getByRole('button', { name: 'New chat' }));
    const earlier = await screen.findByRole('button', { name: 'What changed with this patient since the last visit?' });
    expect(screen.queryByText(/HbA1c is 6.98%/)).not.toBeInTheDocument();

    await fireEvent.click(earlier);
    expect(await screen.findByText(/HbA1c is 6.98%/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'What changed with this patient since the last visit?' })).not.toBeInTheDocument();

    await fireEvent.update(screen.getByLabelText('Question'), 'What about the dose?');
    await fireEvent.click(screen.getByRole('button', { name: 'Ask with sources' }));
    expect(await screen.findByText(/The dose is 5 mg/)).toBeInTheDocument();
    expect(askPatient360).toHaveBeenLastCalledWith(expect.objectContaining({
      question: 'What about the dose?',
      history: [
        { role: 'user', content: 'What changed with this patient since the last visit?' },
        { role: 'assistant', content: 'HbA1c is 6.98% [obs_a1].' }
      ]
    }));

    ui.openAskPanel('p_102');
    await waitFor(() => {
      expect(screen.queryByText(/HbA1c is 6.98%/)).not.toBeInTheDocument();
    });
    ui.openAskPanel('p_101');
    expect(await screen.findByText(/HbA1c is 6.98%/)).toBeInTheDocument();
  });

  it('does not offer an earlier chat after its sandbox is gone', async () => {
    chatSandbox.mockResolvedValueOnce({ active: true, stamp: 'live' }).mockResolvedValue({ active: false });
    askPatient360.mockResolvedValue({
      id: 'a1',
      answer: 'HbA1c is 6.98% [obs_a1].',
      citations: [{ id: 'obs_a1', label: 'HbA1c', sourceId: 'obs_a1', sourceType: 'lab' }],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false,
      sandboxStamp: 'live'
    } satisfies AiAnswer);

    await openPanel();
    await submitAsk();
    expect(await screen.findByText(/HbA1c is 6.98%/)).toBeInTheDocument();
    await fireEvent.click(screen.getByRole('button', { name: 'New chat' }));

    await waitFor(() => {
      expect(screen.queryByRole('navigation', { name: 'Earlier chats' })).not.toBeInTheDocument();
    });
    expect(screen.queryByText(/HbA1c is 6.98%/)).not.toBeInTheDocument();
  });

  it('does not continue a chat on a replacement sandbox', async () => {
    chatSandbox
      .mockResolvedValueOnce({ active: true, stamp: 'live' })
      .mockResolvedValueOnce({ active: true, stamp: 'other' });
    askPatient360.mockResolvedValue({
      id: 'a1',
      answer: 'HbA1c is 6.98% [obs_a1].',
      citations: [{ id: 'obs_a1', label: 'HbA1c', sourceId: 'obs_a1', sourceType: 'lab' }],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false,
      sandboxStamp: 'live'
    } satisfies AiAnswer);

    await openPanel();
    await submitAsk();
    expect(await screen.findByText(/HbA1c is 6.98%/)).toBeInTheDocument();
    await fireEvent.update(screen.getByLabelText('Question'), 'What about the dose?');
    await fireEvent.click(screen.getByRole('button', { name: 'Ask with sources' }));

    expect(await screen.findByText('This chat is no longer active. Start a new chat to continue.')).toBeInTheDocument();
    expect(askPatient360).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('What about the dose?')).not.toBeInTheDocument();
  });

  it('renders the thread as opposing chat bubbles', async () => {
    askPatient360.mockResolvedValue({
      id: 'a1',
      answer: 'HbA1c is 6.98% [obs_a1].',
      citations: [{ id: 'obs_a1', label: 'HbA1c', sourceId: 'obs_a1', sourceType: 'lab' }],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false
    } satisfies AiAnswer);

    await openPanel();
    expect(screen.getByLabelText('Question')).toHaveValue('');
    await submitAsk('What is the latest A1c?');
    expect(await screen.findByText(/HbA1c is 6.98%/)).toBeInTheDocument();

    const log = screen.getByRole('log', { name: 'Conversation' });
    expect(log.querySelector('.turn--user .bubble--user')).toBeTruthy();
    expect(log.querySelector('.turn--assistant .bubble--assistant')).toBeTruthy();
    expect(log.querySelector('.answer')).toBeNull();
  });

  it('sends a suggestion chip through Ask immediately', async () => {
    askPatient360.mockResolvedValue({
      id: 'a1',
      answer: 'Creatinine is 1.1 mg/dL [obs_cr].',
      citations: [{ id: 'obs_cr', label: 'Creatinine', sourceId: 'obs_cr', sourceType: 'lab' }],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false
    } satisfies AiAnswer);

    await openPanel();
    await fireEvent.click(await screen.findByRole('button', { name: 'Summarize the latest labs' }));

    expect(await screen.findByText('Summarize the latest labs')).toBeInTheDocument();
    expect(askPatient360).toHaveBeenCalledWith(expect.objectContaining({
      question: 'Summarize the latest labs',
      patientId: 'p_101'
    }));
    expect(await screen.findByText(/Creatinine is 1.1 mg\/dL/)).toBeInTheDocument();
  });

  it('copies the visible user and assistant message text', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    askPatient360.mockResolvedValue({
      id: 'a1',
      answer: 'HbA1c is 6.98% [obs_a1].',
      citations: [{ id: 'obs_a1', label: 'HbA1c', sourceId: 'obs_a1', sourceType: 'lab' }],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false
    } satisfies AiAnswer);

    await openPanel();
    await fireEvent.update(screen.getByLabelText('Question'), 'What is the latest A1c?');
    await fireEvent.click(screen.getByRole('button', { name: 'Ask with sources' }));
    expect(await screen.findByText(/HbA1c is 6.98%/)).toBeInTheDocument();

    const copyButtons = screen.getAllByRole('button', { name: 'Copy message' });
    expect(copyButtons.length).toBeGreaterThanOrEqual(2);
    await fireEvent.click(copyButtons[0]);
    expect(writeText).toHaveBeenCalledWith('What is the latest A1c?');
    expect(await screen.findByText('Copied')).toBeInTheDocument();

    await fireEvent.click(copyButtons[1]);
    expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/HbA1c is 6\.98%/));
  });

  it('opens authorized tools on / and inserts the token instead of sending', async () => {
    await openPanel();
    const input = screen.getByLabelText('Question');
    await fireEvent.update(input, '/lab');

    expect(screen.getByRole('listbox', { name: 'Tools' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Labs' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Notes' })).not.toBeInTheDocument();

    await fireEvent.keyDown(input, { key: 'Enter' });
    expect(input).toHaveValue('/labs ');
    expect(askPatient360).not.toHaveBeenCalled();
  });

  it('hides tools the session cannot use and still sends when the menu is closed', async () => {
    askPatient360.mockResolvedValue({
      id: 'a1',
      answer: 'HbA1c is 6.98% [obs_a1].',
      citations: [{ id: 'obs_a1', label: 'HbA1c', sourceId: 'obs_a1', sourceType: 'lab' }],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false
    } satisfies AiAnswer);

    await openPanel(['labs', 'conditions', 'meds', 'encounters', 'allergies', 'notes', 'imaging', 'ask']);
    const input = screen.getByLabelText('Question');
    await fireEvent.update(input, '/');
    expect(screen.getByRole('option', { name: 'Labs' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Diet' })).not.toBeInTheDocument();

    await fireEvent.keyDown(input, { key: 'Escape' });
    expect(screen.queryByRole('listbox', { name: 'Tools' })).not.toBeInTheDocument();
    expect(input).toHaveValue('/');

    await fireEvent.update(input, 'Summarize /labs');
    await fireEvent.click(screen.getByRole('button', { name: 'Ask with sources' }));
    expect(askPatient360).toHaveBeenLastCalledWith(expect.objectContaining({
      question: 'Summarize /labs',
      patientId: 'p_101'
    }));
  });

  it('does not treat a unit slash as a tool mention and Enter still sends', async () => {
    askPatient360.mockResolvedValue({
      id: 'a1',
      answer: 'Creatinine is 1.1 mg/dL [obs_cr].',
      citations: [{ id: 'obs_cr', label: 'Creatinine', sourceId: 'obs_cr', sourceType: 'lab' }],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false
    } satisfies AiAnswer);

    await openPanel();
    const input = screen.getByLabelText('Question');
    await fireEvent.update(input, 'creatinine is 1.1 mg/dL');
    expect(screen.queryByRole('listbox', { name: 'Tools' })).not.toBeInTheDocument();
    await fireEvent.keyDown(input, { key: 'Enter' });
    expect(askPatient360).toHaveBeenCalledWith(expect.objectContaining({
      question: 'creatinine is 1.1 mg/dL'
    }));
  });

});
