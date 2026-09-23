import { describe, expect, it } from 'vitest';
import {
  activeToolMention,
  askToolMentionsFor,
  filterToolMentions,
  insertToolMention,
  parseAskToolMentions
} from '../../src/services/askToolMentions';

describe('askToolMentionsFor', () => {
  it('follows chart datasets plus notes and imaging panels', () => {
    expect(
      askToolMentionsFor(['labs', 'meds', 'conditions', 'notes', 'imaging', 'ask']).map(item => item.token)
    ).toEqual(['labs', 'conditions', 'meds', 'notes', 'imaging']);
  });

  it('omits diet for a consultant and treats food-allergy as allergies', () => {
    expect(
      askToolMentionsFor(['labs', 'conditions', 'meds', 'encounters', 'allergies', 'notes', 'imaging']).map(
        item => item.token
      )
    ).not.toContain('diet');
    expect(askToolMentionsFor(['allergies_food', 'diet']).map(item => item.token)).toEqual([
      'allergies',
      'diet'
    ]);
  });

  it('uses imaging_metadata for imaging and never lists availability', () => {
    expect(askToolMentionsFor(['imaging_metadata']).map(item => item)).toEqual([
      { token: 'imaging', label: 'Imaging' }
    ]);
    expect(askToolMentionsFor(['appointments', 'ask']).map(item => item.token)).toEqual([]);
  });
});

describe('activeToolMention', () => {
  it('opens after a boundary and ignores units like mg/dL', () => {
    expect(activeToolMention('/lab', 4)).toEqual({ start: 0, query: 'lab' });
    expect(activeToolMention('check /', 7)).toEqual({ start: 6, query: '' });
    expect(activeToolMention('mg/dL', 5)).toBeNull();
    expect(activeToolMention('mg/', 3)).toBeNull();
    expect(activeToolMention('hello/', 6)).toBeNull();
  });
});

describe('filterToolMentions', () => {
  const catalog = askToolMentionsFor(['labs', 'meds', 'notes', 'imaging']);

  it('matches a prefix on the token or chart label', () => {
    expect(filterToolMentions(catalog, 'lab').map(item => item.token)).toEqual(['labs']);
    expect(filterToolMentions(catalog, 'med').map(item => item.token)).toEqual(['meds']);
    expect(filterToolMentions(catalog, 'Imag').map(item => item.token)).toEqual(['imaging']);
    expect(filterToolMentions(catalog, '').map(item => item.token)).toEqual(['labs', 'meds', 'notes', 'imaging']);
  });
});

describe('insertToolMention', () => {
  it('replaces the active /query with /labs and leaves the caret after it', () => {
    expect(insertToolMention('Summarize /lab', 10, 14, 'labs')).toEqual({
      text: 'Summarize /labs ',
      caret: 16
    });
    expect(insertToolMention('See /lab here', 4, 8, 'labs')).toEqual({
      text: 'See /labs here',
      caret: 9
    });
  });
});

describe('parseAskToolMentions', () => {
  it('collects known tokens and ignores unknown or mid-word slashes', () => {
    expect(parseAskToolMentions('Use /labs and /notes, skip /foo and mg/dL')).toEqual(['labs', 'notes']);
    expect(parseAskToolMentions('no mentions')).toEqual([]);
  });
});
