import { fireEvent, render, screen, within } from '@testing-library/vue';
import { createPinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';
import LabsView from '../../src/features/patient360/LabsView.vue';
import { patients } from '../../src/data/mockPatient360';
import type { Patient } from '../../src/types/patient360';

let resolvePatient!: (patient: Patient) => void;

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    getPatient: () => new Promise(resolve => { resolvePatient = resolve; })
  }
}));

async function renderLabs(path = '/patients/p_101/labs') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/patients/:patientId/labs', component: LabsView }]
  });
  await router.push(path);
  await router.isReady();
  return render(LabsView, { global: { plugins: [router, createPinia()] } });
}

function patientWithLongPriors(): Patient {
  const base = patients[0];
  return {
    ...base,
    labs: [
      {
        id: 'obs_a1',
        label: 'HbA1c',
        value: '6.98',
        unit: '%',
        referenceRange: '4–5.6',
        trend: 'stable',
        flag: 'high',
        abnormal: true,
        date: '2025-12-05',
        sourceId: 'obs_a1'
      },
      {
        id: 'obs_a1b',
        label: 'HbA1c',
        value: '6.98',
        unit: '%',
        referenceRange: '4–5.6',
        trend: 'stable',
        flag: 'high',
        abnormal: true,
        date: '2024-11-29',
        sourceId: 'obs_a1b'
      },
      {
        id: 'obs_a1c',
        label: 'HbA1c',
        value: '6.98',
        unit: '%',
        referenceRange: '4–5.6',
        trend: 'stable',
        flag: 'high',
        abnormal: true,
        date: '2023-11-24',
        sourceId: 'obs_a1c'
      },
      {
        id: 'obs_a1d',
        label: 'HbA1c',
        value: '6.98',
        unit: '%',
        referenceRange: '4–5.6',
        trend: 'stable',
        flag: 'high',
        abnormal: true,
        date: '2022-11-18',
        sourceId: 'obs_a1d'
      },
      {
        id: 'obs_a1e',
        label: 'HbA1c',
        value: '6.98',
        unit: '%',
        referenceRange: '4–5.6',
        trend: 'stable',
        flag: 'high',
        abnormal: true,
        date: '2021-11-12',
        sourceId: 'obs_a1e'
      },
      {
        id: 'obs_k1',
        label: 'Potassium',
        value: '5.2',
        unit: 'mmol/L',
        referenceRange: '3.5–5.0',
        trend: 'up',
        flag: 'high',
        abnormal: true,
        date: '2025-12-05',
        sourceId: 'obs_k1'
      },
      {
        id: 'obs_k2',
        label: 'Potassium',
        value: '4.9',
        unit: 'mmol/L',
        referenceRange: '3.5–5.0',
        trend: 'stable',
        flag: 'normal',
        abnormal: false,
        date: '2024-11-29',
        sourceId: 'obs_k2'
      }
    ]
  };
}

describe('LabsView', () => {
  it('does not treat an in-flight fetch as an empty lab list', async () => {
    await renderLabs();

    expect(screen.queryByText('No visible laboratory rows.')).not.toBeInTheDocument();
    expect(screen.queryByText('HbA1c')).not.toBeInTheDocument();

    resolvePatient(patients[0]);
    expect(await screen.findByText('HbA1c')).toBeInTheDocument();
    expect(screen.queryByText('No visible laboratory rows.')).not.toBeInTheDocument();
    expect(screen.getByText('2 results')).toBeInTheDocument();
  });

  it('leads with the latest value and keeps prior history out of a run-on Prior line', async () => {
    await renderLabs();
    resolvePatient(patientWithLongPriors());

    const article = (await screen.findByText('HbA1c')).closest('article');
    expect(article).toBeTruthy();
    const row = within(article as HTMLElement);

    expect(row.getByText('High')).toBeInTheDocument();
    expect(row.getByText(/Reference 4–5.6/)).toBeInTheDocument();
    expect(row.getByText('Earlier results')).toBeInTheDocument();
    expect(article!.querySelector('.primary > .num')?.textContent).toBe('6.98');

    expect(row.queryByText(/Prior\s+6\.98/)).not.toBeInTheDocument();
    expect(article!.textContent).not.toMatch(/Prior[\s\S]*·/);

    const historyItems = row.getAllByRole('listitem');
    expect(historyItems).toHaveLength(3);
    expect(historyItems[0]).toHaveTextContent('6.98');
    expect(historyItems[0]).toHaveTextContent('29 Nov 2024');
    expect(row.queryByText('12 Nov 2021')).not.toBeInTheDocument();

    const more = row.getByRole('button', { name: 'Show earlier results (1)' });
    await fireEvent.click(more);
    expect(row.getAllByRole('listitem')).toHaveLength(4);
    expect(row.getByText('12 Nov 2021')).toBeInTheDocument();
    expect(row.getByRole('button', { name: 'Show fewer results' })).toBeInTheDocument();
  });

  it('counts analytes and filters the list as the clinician types', async () => {
    await renderLabs();
    resolvePatient(patientWithLongPriors());

    expect(await screen.findByText('HbA1c')).toBeInTheDocument();
    expect(screen.getByText('Potassium')).toBeInTheDocument();
    expect(screen.getByText('2 results')).toBeInTheDocument();
    expect(screen.queryByText(/p_101/)).not.toBeInTheDocument();

    await fireEvent.update(screen.getByLabelText('Search results'), 'pot');
    expect(screen.getByText('Potassium')).toBeInTheDocument();
    expect(screen.queryByText('HbA1c')).not.toBeInTheDocument();
    expect(screen.getByText('1 of 2 results')).toBeInTheDocument();
    expect(screen.queryByText(/Prior\s+/)).not.toBeInTheDocument();

    await fireEvent.update(screen.getByLabelText('Search results'), 'mmol');
    expect(screen.getByText('Potassium')).toBeInTheDocument();
    expect(screen.queryByText('HbA1c')).not.toBeInTheDocument();

    await fireEvent.update(screen.getByLabelText('Search results'), 'zzz');
    expect(screen.getByText('No laboratory results match this filter.')).toBeInTheDocument();
    expect(screen.getByText('0 of 2 results')).toBeInTheDocument();
    expect(screen.queryByText('HbA1c')).not.toBeInTheDocument();
    expect(screen.queryByText('Potassium')).not.toBeInTheDocument();

    await fireEvent.update(screen.getByLabelText('Search results'), '');
    expect(screen.getByText('HbA1c')).toBeInTheDocument();
    expect(screen.getByText('Potassium')).toBeInTheDocument();
    expect(screen.getByText('2 results')).toBeInTheDocument();
  });

  it('narrows analytes by flag and combines that filter with search', async () => {
    await renderLabs();
    resolvePatient({
      ...patients[0],
      labs: [
        ...patients[0].labs,
        {
          id: 'obs_na1',
          label: 'Sodium',
          value: '132',
          unit: 'mmol/L',
          referenceRange: '136–145',
          trend: 'down',
          flag: 'low',
          abnormal: true,
          date: '2026-09-10',
          sourceId: 'obs_na1'
        },
        {
          id: 'obs_note1',
          label: 'Comment',
          value: 'See note',
          unit: '',
          referenceRange: '',
          trend: 'stable',
          flag: 'unknown',
          abnormal: false,
          date: '2026-09-10',
          sourceId: 'obs_note1'
        }
      ]
    });

    expect(await screen.findByText('4 results')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'All' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Recorded' })).toBeInTheDocument();

    await fireEvent.click(screen.getByRole('tab', { name: 'High' }));
    expect(screen.getByText('HbA1c')).toBeInTheDocument();
    expect(screen.queryByText('Creatinine')).not.toBeInTheDocument();
    expect(screen.queryByText('Sodium')).not.toBeInTheDocument();
    expect(screen.getByText('1 of 4 results')).toBeInTheDocument();

    await fireEvent.click(screen.getByRole('tab', { name: 'Low' }));
    expect(screen.getByText('Sodium')).toBeInTheDocument();
    expect(screen.queryByText('HbA1c')).not.toBeInTheDocument();
    expect(screen.getByText('1 of 4 results')).toBeInTheDocument();

    await fireEvent.click(screen.getByRole('tab', { name: 'In range' }));
    expect(screen.getByText('Creatinine')).toBeInTheDocument();
    expect(screen.queryByText('HbA1c')).not.toBeInTheDocument();

    await fireEvent.click(screen.getByRole('tab', { name: 'Recorded' }));
    expect(screen.getByText('Comment')).toBeInTheDocument();
    expect(screen.queryByText('Creatinine')).not.toBeInTheDocument();

    await fireEvent.click(screen.getByRole('tab', { name: 'High' }));
    await fireEvent.update(screen.getByLabelText('Search results'), 'pot');
    expect(screen.getByText('No laboratory results match this filter.')).toBeInTheDocument();
    expect(screen.getByText('0 of 4 results')).toBeInTheDocument();

    await fireEvent.update(screen.getByLabelText('Search results'), '');
    await fireEvent.click(screen.getByRole('tab', { name: 'All' }));
    expect(screen.getByText('HbA1c')).toBeInTheDocument();
    expect(screen.getByText('Creatinine')).toBeInTheDocument();
    expect(screen.getByText('Sodium')).toBeInTheDocument();
    expect(screen.getByText('Comment')).toBeInTheDocument();
    expect(screen.getByText('4 results')).toBeInTheDocument();
  });
});
