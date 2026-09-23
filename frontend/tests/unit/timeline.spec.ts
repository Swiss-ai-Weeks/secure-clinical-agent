import { fireEvent, render, screen } from '@testing-library/vue';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import { describe, expect, it, vi } from 'vitest';
import TimelineEventCard from '../../src/features/patient360/TimelineEventCard.vue';
import TimelineView from '../../src/features/patient360/TimelineView.vue';
import { patients, timelineEvents } from '../../src/data/mockPatient360';
import { composeTimeline, filterTimeline } from '../../src/services/patientRecord';
import { useUiStore } from '../../src/stores/useUiStore';
import type { TimelineEvent } from '../../src/types/patient360';

const chartEvents: TimelineEvent[] = [
  { id: 'obs_a1', kind: 'lab', date: '2026-09-10', title: 'HbA1c', summary: '7.9 %', tags: ['Laboratory'], provenance: 'clinical' },
  { id: 'med_a1', kind: 'medication', date: '2025-01-01', title: 'Metformin', summary: 'Active', tags: ['Medication'], provenance: 'clinical' },
  { id: 'note_1', kind: 'note', date: '2026-09-12', title: 'Admission', summary: 'Historical pneumonia.', tags: ['Note'], provenance: 'clinical' }
];

vi.mock('../../src/services/apiClient', () => ({
  apiClient: {
    getTimeline: async () => chartEvents
  }
}));

async function renderTimeline() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/patients/:patientId/timeline', component: TimelineView }]
  });
  await router.push('/patients/p_101/timeline');
  await router.isReady();
  render(TimelineView, { global: { plugins: [router, pinia] } });
  await screen.findByText('HbA1c');
}

describe('TimelineEventCard', () => {
  it('renders a note whose date is missing', () => {
    render(TimelineEventCard, {
      props: {
        highlighted: false,
        event: {
          id: 'p_485ba8c8597d4c5cb0fbda55317119a3-historical-pneumonia',
          kind: 'note',
          date: '',
          title: 'Historical Pneumonia',
          summary: 'Prior pneumonia with hypoxemia.',
          tags: ['Note'],
          provenance: 'clinical'
        }
      }
    });

    expect(screen.getByText('Historical Pneumonia')).toBeInTheDocument();
    expect(screen.getByText('Date not recorded')).toBeInTheDocument();
  });
});

describe('timeline filtering', () => {
  it('keeps all events visible by default', () => {
    expect(filterTimeline(timelineEvents, { kind: 'all', query: '' })).toHaveLength(timelineEvents.length);
  });

  it('filters labs without losing the HbA1c event', () => {
    const labs = filterTimeline(timelineEvents, { kind: 'lab', query: '' });

    expect(labs).toHaveLength(1);
    expect(labs[0].id).toBe('obs_a1');
  });

  it('matches a query against title, summary, tags, and date', () => {
    expect(filterTimeline(timelineEvents, { kind: 'all', query: 'HbA1c' }).map(event => event.id)).toEqual(['obs_a1']);
    expect(filterTimeline(timelineEvents, { kind: 'all', query: 'medication' }).map(event => event.id)).toEqual(['med_a1']);
    expect(filterTimeline(timelineEvents, { kind: 'all', query: '2025-01-01' }).map(event => event.id)).toEqual(['med_a1']);
  });

  it('applies kind and query together', () => {
    expect(filterTimeline(timelineEvents, { kind: 'lab', query: 'metformin' })).toEqual([]);
    expect(filterTimeline(timelineEvents, { kind: 'medication', query: 'metformin' }).map(event => event.id)).toEqual(['med_a1']);
  });

  it('returns nothing when nothing matches', () => {
    expect(filterTimeline(timelineEvents, { kind: 'all', query: 'zzz' })).toEqual([]);
  });
});

describe('composeTimeline', () => {
  it('includes notes and documents newest first', () => {
    const events = composeTimeline({
      ...patients[0],
      notes: [{ id: 'note_1', title: 'Admission', author: 'clinical', date: '2026-09-12', text: 'Historical pneumonia.' }],
      documents: [{
        id: 'doc_1',
        title: 'Chest report',
        type: 'Radiology',
        date: '2026-09-11',
        source: 'Imaging',
        processingState: 'processed',
        uploadedBy: 'clinical',
        summary: 'No acute findings'
      }, {
        id: 'doc_2',
        title: 'Upload',
        type: 'patient-reported',
        date: '2026-08-01',
        source: 'upload',
        processingState: 'processed',
        uploadedBy: 'patient'
      }]
    });

    expect(events.map(event => event.id).slice(0, 2)).toEqual(['note_1', 'doc_1']);
    expect(events.find(event => event.id === 'note_1')).toMatchObject({ kind: 'note', tags: ['Note'], summary: 'Historical pneumonia.' });
    expect(events.find(event => event.id === 'doc_1')).toMatchObject({ kind: 'document', tags: ['Document'], summary: 'No acute findings' });
    expect(events.find(event => event.id === 'doc_2')).toMatchObject({ kind: 'document', summary: 'patient-reported', provenance: 'patient-reported' });
  });
});

describe('TimelineView search and filters', () => {
  it('narrows events by search text and kind together', async () => {
    await renderTimeline();
    expect(screen.getByText('3 visible clinical events')).toBeInTheDocument();

    await fireEvent.update(screen.getByLabelText('Search timeline'), 'HbA1c');
    expect(screen.getByText('HbA1c')).toBeInTheDocument();
    expect(screen.queryByText('Metformin')).not.toBeInTheDocument();
    expect(screen.getByText('1 visible clinical events')).toBeInTheDocument();

    await fireEvent.click(screen.getByRole('tab', { name: 'Labs' }));
    await fireEvent.update(screen.getByLabelText('Search timeline'), 'metformin');
    expect(screen.getByText('No timeline events match this filter.')).toBeInTheDocument();
    expect(screen.getByText('0 visible clinical events')).toBeInTheDocument();
  });

  it('shows notes for the Notes pill and keeps a highlighted event visible', async () => {
    await renderTimeline();
    await fireEvent.click(screen.getByRole('tab', { name: 'Notes' }));
    expect(screen.getByText('Admission')).toBeInTheDocument();
    expect(screen.queryByText('HbA1c')).not.toBeInTheDocument();

    await fireEvent.click(screen.getByRole('tab', { name: 'Labs' }));
    useUiStore().highlightSource('note_1');
    expect(await screen.findByText('Admission')).toBeInTheDocument();
    expect(screen.getByText('HbA1c')).toBeInTheDocument();
  });
});
