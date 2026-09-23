import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/vue';
import { createPinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import RedTeamView from '../../src/features/clinic/RedTeamView.vue';

const listRedteam = vi.fn();
const redteam = vi.fn();

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    listRedteam: () => listRedteam(),
    redteam: () => redteam()
  }
}));

afterEach(() => {
  cleanup();
  listRedteam.mockReset();
  redteam.mockReset();
});

const catalog = {
  cases: [
    { id: 'sandbox-two-sessions', layer: 'sandbox', owasp: 'LLM06', expect: 'distinct', result: 'catalogued' },
    { id: 'chen-labs-permit', layer: 'pdp', owasp: 'LLM06', expect: 'permit', result: 'catalogued' },
    { id: 'content-safety', layer: 'safety', owasp: 'LLM01', expect: 'content_safety', result: 'catalogued' }
  ],
  count: 3,
  pass: 0,
  fail: 0,
  partial: 0
};

async function renderBoard() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/redteam', component: RedTeamView }]
  });
  await router.push('/redteam');
  await router.isReady();
  return render(RedTeamView, { global: { plugins: [router, createPinia()] } });
}

describe('RedTeamView', () => {
  it('groups the catalog under the three controls it exercises', async () => {
    listRedteam.mockResolvedValue(catalog);
    await renderBoard();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Session isolation' })).toBeInTheDocument();
    });
    expect(screen.getByRole('heading', { name: 'Access policy' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Safety rails' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Two sessions stay isolated' })).toBeInTheDocument();
    expect(screen.queryByText('sandbox-two-sessions')).not.toBeInTheDocument();
    expect(screen.getAllByText('Not run')).toHaveLength(3);
    expect(screen.getByText(/results appear after you run the suite/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run suite' })).toBeInTheDocument();
    expect(redteam).not.toHaveBeenCalled();
  });

  it('does not POST the suite just because the catalog loaded', async () => {
    listRedteam.mockResolvedValue(catalog);
    await renderBoard();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Run suite' })).toBeInTheDocument());
    expect(listRedteam).toHaveBeenCalled();
    expect(redteam).not.toHaveBeenCalled();
  });

  it('scores each control separately and keeps an unconfigured probe partial', async () => {
    listRedteam.mockResolvedValue(catalog);
    redteam.mockResolvedValue({
      cases: [
        { id: 'sandbox-two-sessions', layer: 'sandbox', result: 'partial', detector: 'not_configured' },
        { id: 'sandbox-gold-turn', layer: 'sandbox', result: 'partial', detector: 'not_configured' },
        { id: 'chen-labs-permit', layer: 'pdp', result: 'pass', detector: 'status_200' },
        { id: 'auditor-labs', layer: 'pdp', result: 'pass', detector: 'status' },
        { id: 'content-safety', layer: 'safety', result: 'fail', detector: 'content_safety' }
      ],
      count: 5,
      pass: 2,
      fail: 1,
      partial: 2
    });
    await renderBoard();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Run suite' })).toBeInTheDocument());

    await fireEvent.click(screen.getByRole('button', { name: 'Run suite' }));

    await waitFor(() => {
      expect(screen.getByText('0 passed · 0 failed · 2 partial')).toBeInTheDocument();
    });
    expect(screen.getByText('2 passed · 0 failed · 0 partial')).toBeInTheDocument();
    expect(screen.getByText('0 passed · 1 failed · 0 partial')).toBeInTheDocument();
    const lastRun = screen.getByLabelText('Last run');
    expect(lastRun).toHaveTextContent('20%');
    expect(lastRun).toHaveTextContent('Failed');
    expect(lastRun).toHaveTextContent('1');
    expect(screen.getAllByText('Failed').length).toBeGreaterThan(0);
    expect(screen.queryByText('Catalogued')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Re-run suite' })).toBeInTheDocument();
  });

  it('shows a loading state while the suite is running', async () => {
    listRedteam.mockResolvedValue(catalog);
    let finish!: (value: unknown) => void;
    redteam.mockImplementation(
      () => new Promise(resolve => {
        finish = resolve;
      })
    );
    await renderBoard();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Run suite' })).toBeInTheDocument());

    await fireEvent.click(screen.getByRole('button', { name: 'Run suite' }));

    expect(screen.getByRole('button', { name: 'Running suite…' })).toBeDisabled();
    expect(screen.getByText('Running the suite…')).toBeInTheDocument();
    finish({
      cases: [{ id: 'chen-labs-permit', layer: 'pdp', result: 'pass' }],
      pass: 1,
      fail: 0,
      partial: 0
    });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Re-run suite' })).toBeInTheDocument());
  });

  it('shows the load error instead of an empty catalog', async () => {
    listRedteam.mockRejectedValue(new Error('Request failed (401)'));
    await renderBoard();

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Request failed (401)');
    });
    expect(screen.queryByText(/no cases are available/i)).not.toBeInTheDocument();
  });

  it('explains a missing catalog without looking broken', async () => {
    listRedteam.mockResolvedValue({ cases: [], count: 0, pass: 0, fail: 0, partial: 0 });
    await renderBoard();

    await waitFor(() => {
      expect(screen.getByText(/no cases are available on this server/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Run suite' })).toBeInTheDocument();
  });

  it('hides a control with no cases instead of showing an empty section', async () => {
    listRedteam.mockResolvedValue({
      cases: [{ id: 'chen-labs-permit', layer: 'pdp', result: 'pass' }],
      count: 1,
      pass: 1,
      fail: 0,
      partial: 0
    });
    await renderBoard();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Access policy' })).toBeInTheDocument();
    });
    expect(screen.queryByRole('heading', { name: 'Session isolation' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Safety rails' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Last run')).toHaveTextContent('Passed');
  });
});
