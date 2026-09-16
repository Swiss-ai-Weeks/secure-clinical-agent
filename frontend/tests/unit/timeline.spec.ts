import { describe, expect, it } from 'vitest';
import { timelineEvents } from '../../src/data/mockPatient360';

function filterEvents(kind: string) {
  return kind === 'all' ? timelineEvents : timelineEvents.filter(event => event.kind === kind);
}

describe('timeline filtering', () => {
  it('keeps all events visible by default', () => {
    expect(filterEvents('all')).toHaveLength(timelineEvents.length);
  });

  it('filters labs without losing the abnormal LDL event', () => {
    const labs = filterEvents('lab');

    expect(labs).toHaveLength(1);
    expect(labs[0].id).toBe('event-lab-aug-18');
  });
});
