import { cleanup, fireEvent, render, screen } from '@testing-library/vue';
import { createPinia, setActivePinia } from 'pinia';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ClinicalBrief from '../../src/features/patient360/ClinicalBrief.vue';
import { patients } from '../../src/data/mockPatient360';
import { useSessionStore } from '../../src/stores/useSessionStore';
import type { AiAnswer } from '../../src/types/patient360';
import type { Me } from '../../src/types/api';

const askPatient360 = vi.fn();

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    askPatient360: (...args: unknown[]) => askPatient360(...args)
  }
}));

afterEach(() => {
  cleanup();
  askPatient360.mockReset();
});

function attendingSession(): Me {
  return {
    user_id: 'u_chen',
    display: 'Dr. Sarah Chen',
    role: 'attending',
    department: null,
    credential_level: 2,
    self_patient_id: null,
    datasets: [],
    panels: ['labs', 'ask', 'notes'],
    policy_version: 'test',
    session: { expires_at: '', absolute_expires_at: '', auth_level: 2, on_duty: true }
  };
}

describe('ClinicalBrief', () => {
  it('renders a regenerated summary as structured text instead of a raw dump', async () => {
    askPatient360.mockResolvedValue({
      id: 'brief-1',
      answer: '**Latest labs** - HbA1c: **6.35 %** [obs_a1c] - Creatinine: **1.35 mg/dL** [obs_cr]',
      citations: [],
      retrievalSteps: ['OpenShell sandbox turn'],
      refused: false
    } satisfies AiAnswer);

    const pinia = createPinia();
    setActivePinia(pinia);
    useSessionStore().me = attendingSession();
    render(ClinicalBrief, {
      props: { patient: patients[0] },
      global: { plugins: [pinia] }
    });

    await fireEvent.click(screen.getByRole('button', { name: 'Regenerate summary' }));

    expect(askPatient360).toHaveBeenCalledWith({
      scope: 'patient',
      patientId: 'p_101',
      question: 'Summarize the visible record since the last visit.'
    });
    expect(await screen.findByText('Latest labs')).toBeInTheDocument();
    expect(screen.getByText('6.35 %')).toBeInTheDocument();
    expect(screen.queryByText(/obs_a1c/)).not.toBeInTheDocument();
  });

  it('hides Ask actions when the session cannot launch Ask', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    useSessionStore().me = {
      ...attendingSession(),
      panels: ['labs', 'notes']
    };
    render(ClinicalBrief, {
      props: { patient: patients[0] },
      global: { plugins: [pinia] }
    });
    expect(screen.queryByRole('button', { name: 'Open Ask' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Ask follow-up' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Regenerate summary' })).not.toBeInTheDocument();
  });
});
