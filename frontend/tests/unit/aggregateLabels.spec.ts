import { describe, expect, it } from 'vitest';
import { aggregateCellCode, aggregateCellTitle } from '../../src/services/aggregateLabels';

describe('aggregateLabels', () => {
  it('prefers the API display over the raw code', () => {
    const row = { dims: { code: '44054006' }, display: 'Type 2 diabetes mellitus', count: 1 };
    expect(aggregateCellTitle(row)).toBe('Type 2 diabetes mellitus');
    expect(aggregateCellCode(row)).toBe('44054006');
  });

  it('maps seed-demo codes when the cell has no display', () => {
    expect(aggregateCellTitle({ dims: { code: '195967001' }, count: 1 })).toBe('Asthma');
    expect(aggregateCellTitle({ dims: { code: '35489007' }, count: 1 })).toBe('Depressive disorder');
  });

  it('falls back to JSON only when there is no coded dim', () => {
    expect(aggregateCellTitle({ dims: { sex: 'female' }, count: 4 })).toBe('{"sex":"female"}');
  });
});
