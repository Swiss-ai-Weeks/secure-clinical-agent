import { cleanup, render, screen, waitFor } from '@testing-library/vue';
import { createPinia, setActivePinia } from 'pinia';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ConsentCard from '../../src/features/clinic/ConsentCard.vue';
import { ApiError } from '../../src/services/http';
import { useSessionStore } from '../../src/stores/useSessionStore';

const listConsents = vi.fn();

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    listConsents: (...args: unknown[]) => listConsents(...args),
    grantConsent: vi.fn(),
    revokeConsent: vi.fn()
  }
}));

afterEach(() => {
  cleanup();
  listConsents.mockReset();
});

function renderCard() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const session = useSessionStore();
  session.me = {
    user_id: 'u_diego',
    display: 'Diego Santos',
    role: 'caregiver',
    department: null,
    credential_level: 1,
    self_patient_id: null,
    datasets: [],
    panels: ['consents'],
    policy_version: 'test',
    session: { expires_at: '', absolute_expires_at: '', auth_level: 1, on_duty: true }
  };
  session.personas = [
    { login: 'diego', user_id: 'u_diego', display: 'Diego Santos', role: 'caregiver' },
    { login: 'maria', user_id: 'u_maria', display: 'Maria Santos', role: 'patient' }
  ];
  return render(ConsentCard, {
    props: { patientKey: 'p_103', relations: ['caregiver', 'caregiver_notes', 'blocked'], title: 'Grant access' },
    global: { plugins: [pinia] }
  });
}

describe('ConsentCard', () => {
  it('hides the sharing card when this session cannot list consents', async () => {
    listConsents.mockRejectedValue(new ApiError(404, { resourceType: 'OperationOutcome' }, 'Resource not found'));
    renderCard();
    await waitFor(() => expect(listConsents).toHaveBeenCalledWith('p_103'));
    expect(screen.queryByRole('heading', { name: 'Grant access' })).not.toBeInTheDocument();
    expect(screen.queryByText('Resource not found')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Grant' })).not.toBeInTheDocument();
    expect(screen.queryByText('No consents on this record.')).not.toBeInTheDocument();
  });

  it('shows an empty grant form when the list is authorized and empty', async () => {
    listConsents.mockResolvedValue({ consents: [] });
    renderCard();
    expect(await screen.findByRole('heading', { name: 'Grant access' })).toBeInTheDocument();
    expect(screen.getByText('No one has access yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Grant' })).toBeInTheDocument();
    expect(screen.queryByText('Resource not found')).not.toBeInTheDocument();
  });

  it('renders named people for authorized consents', async () => {
    listConsents.mockResolvedValue({
      consents: [{
        consent_id: 'c1',
        patient_key: 'p_103',
        grantee_user_id: 'u_diego',
        relation: 'caregiver',
        start: '2026-06-01T00:00:00Z',
        expiry: '2026-12-01T00:00:00Z',
        status: 'active',
        granted_by: 'u_maria',
        recorded_at: null,
        justification: null,
        revoked_at: null,
        revoked_by: null,
        enforced: true,
        seeded: true
      }]
    });
    renderCard();
    expect(await screen.findByText('Diego Santos')).toBeInTheDocument();
    expect(screen.getByText(/Family · Caregiver/)).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Who' }).textContent).toMatch(/Maria Santos · Family/);
    expect(screen.queryByText(/u_diego|u_maria/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Revoke' })).toBeInTheDocument();
  });
});
