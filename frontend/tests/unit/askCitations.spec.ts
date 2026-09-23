import { describe, expect, it } from 'vitest';
import {
  answerBlocks,
  citationsUsedInAnswer,
  displayAnswerText,
  friendlyRetrievalSteps,
  isNoEvidenceAnswer,
  policyReasonLabel
} from '../../src/services/askCitations';
import type { AiAnswer, AiCitation } from '../../src/types/patient360';

function answer(partial: Partial<AiAnswer> & Pick<AiAnswer, 'answer'>): AiAnswer {
  return {
    id: 'a1',
    citations: [],
    retrievalSteps: [],
    ...partial
  };
}

const labs: AiCitation[] = [
  { id: 'obs_a1', label: 'HbA1c', sourceId: 'obs_a1', sourceType: 'lab' },
  { id: 'obs_co2', label: 'Carbon dioxide, total', sourceId: 'obs_co2', sourceType: 'lab' },
  { id: 'cond_1', label: 'Prediabetes (finding)', sourceId: 'cond_1', sourceType: 'condition' }
];

describe('askCitations', () => {
  it('hides retrieved labs when the model says there is no authorized evidence', () => {
    const result = citationsUsedInAnswer(answer({
      answer: 'There is no authorized evidence about a patient named Elizabeth.',
      citations: labs
    }));
    expect(result).toEqual([]);
    expect(isNoEvidenceAnswer({ answer: 'There is no authorized evidence about a patient named Elizabeth.' })).toBe(true);
  });

  it('hides citations on an explicit refusal', () => {
    expect(citationsUsedInAnswer(answer({
      answer: 'No authorized evidence for that question.',
      refused: true,
      citations: labs
    }))).toEqual([]);
  });

  it('keeps only citations the answer used', () => {
    const result = citationsUsedInAnswer(answer({
      answer: 'HbA1c is 6.98% [obs_a1].',
      citations: labs
    }));
    expect(result.map(item => item.label)).toEqual(['HbA1c']);
  });

  it('shows a historical note source when the answer uses the note without a cite id', () => {
    const result = citationsUsedInAnswer(answer({
      answer: 'Active conditions: pneumonia, hypoxemia, respiratory distress. Latest measurement: respiratory distress noted in historical note.',
      citations: [
        { id: 'note_pna', label: 'Historical Pneumonia', sourceId: 'note_p101_pna', sourceType: 'note' },
        { id: 'obs_a1', label: 'HbA1c', sourceId: 'obs_a1', sourceType: 'lab' }
      ]
    }));
    expect(result.map(item => item.label)).toEqual(['Historical Pneumonia']);
  });

  it('renders a cite-colon condition mark as a condition chip', () => {
    const blocks = answerBlocks('Prediabetes (code 714628002) [cite:cond_327de270fac646d2].', [
      {
        id: 'cond_327de270fac646d2',
        label: 'Prediabetes',
        sourceId: 'cond_327de270fac646d2',
        sourceType: 'condition'
      }
    ]);
    expect(blocks[0]).toEqual({
      type: 'p',
      parts: [
        { text: 'Prediabetes (code 714628002) ' },
        { text: 'Prediabetes', citeId: 'cond_327de270fac646d2' },
        { text: '.' }
      ]
    });
    expect(displayAnswerText('Prediabetes (code 714628002) [cite:cond_327de270fac646d2].')).toBe(
      'Prediabetes (code 714628002).'
    );
    const used = citationsUsedInAnswer(answer({
      answer: 'Prediabetes (code 714628002) [cite:cond_327de270fac646d2].',
      citations: [
        {
          id: 'cond_327de270fac646d2',
          label: 'Prediabetes',
          sourceId: 'cond_327de270fac646d2',
          sourceType: 'condition'
        },
        { id: 'obs_a1', label: 'HbA1c', sourceId: 'obs_a1', sourceType: 'lab' }
      ]
    }));
    expect(used.map(item => item.label)).toEqual(['Prediabetes']);
  });

  it('formats a NemoClaw paragraph with clickable citations', () => {
    const blocks = answerBlocks('Creatinine is 1.35 mg/dL [obs_a2]. HbA1c is 6.35% [obs_a1].');
    expect(blocks[0]).toEqual({
      type: 'p',
      parts: [
        { text: 'Creatinine is 1.35 mg/dL ' },
        { text: 'Lab', citeId: 'obs_a2' },
        { text: '. HbA1c is 6.35% ' },
        { text: 'Lab', citeId: 'obs_a1' },
        { text: '.' }
      ]
    });
  });

  it('keeps the admission note id as a citation token', () => {
    const blocks = answerBlocks('Metformin continued [p101-admission-2026-09-10].');
    expect(blocks[0]).toEqual({
      type: 'p',
      parts: [
        { text: 'Metformin continued ' },
        { text: 'Admission note, 10 Sep 2026', citeId: 'p101-admission-2026-09-10' },
        { text: '.' }
      ]
    });
  });

  it('turns a uuid citation into a note chip instead of the raw id', () => {
    const id = '6aa46f8e-ac36-5e28-a116-900a0699b0f6';
    const blocks = answerBlocks(`Pneumonia with a history of acute bronchitis [${id}].`, [
      { id, label: 'Historical pneumonia', sourceId: id, sourceType: 'note' }
    ]);
    const visible = blocks.flatMap(block => (block.type === 'p' ? block.parts : block.items.flat())).map(part => part.text).join('');
    expect(visible).not.toContain(id);
    expect(blocks[0]).toEqual({
      type: 'p',
      parts: [
        { text: 'Pneumonia with a history of acute bronchitis ' },
        { text: 'Historical pneumonia', citeId: id },
        { text: '.' }
      ]
    });
  });

  it('rewrites a json-entry lead-in as the note itself', () => {
    const raw =
      'The JSON entry is a clinical note for patient titled “historical pneumonia,” documenting a 21-year-old male with acute bronchitis and a chest x-ray.';
    const blocks = answerBlocks(raw);
    const rendered = JSON.stringify(blocks);
    expect(rendered).not.toMatch(/json entry/i);
    expect(rendered).toMatch(/Historical pneumonia, a past encounter, documents/);
    expect(rendered).toMatch(/chest x-ray/);
  });

  it('keeps blood pressure values when a social-history line shares the answer', () => {
    const raw =
      'The patient has never smoked and currently has Humana insurance - Systolic BP: **130 mmHg** [obs_sbp] - Diastolic BP: **80 mmHg** [obs_dbp]';
    const blocks = answerBlocks(raw, [
      { id: 'obs_sbp', label: 'Systolic BP', sourceId: 'obs_sbp', sourceType: 'lab' },
      { id: 'obs_dbp', label: 'Diastolic BP', sourceId: 'obs_dbp', sourceType: 'lab' }
    ]);
    const rendered = JSON.stringify(blocks);
    expect(rendered).not.toMatch(/never smoked|Humana|insurance/i);
    expect(rendered).toMatch(/130 mmHg/);
    expect(rendered).toMatch(/80 mmHg/);
    expect(rendered).toMatch(/Systolic BP/);
  });

  it('drops synthea social-history sentences from the displayed answer', () => {
    const raw = [
      'Since the last visit the historical pneumonia note records pneumonia [6aa46f8e-ac36-5e28-a116-900a0699b0f6].',
      'The note records that the patient has never smoked, identifies as heterosexual, and currently has Humana insurance [2393d095-2762-5768-a7b1-df0b57d2c07e].',
      'No known allergies are documented [81bc54d4-37f7-5eba-b269-745694cbc41b].'
    ].join(' ');
    const blocks = answerBlocks(raw, [
      { id: '6aa46f8e-ac36-5e28-a116-900a0699b0f6', label: 'Historical pneumonia', sourceId: '6aa46f8e-ac36-5e28-a116-900a0699b0f6', sourceType: 'note' },
      { id: '81bc54d4-37f7-5eba-b269-745694cbc41b', label: 'Allergies', sourceId: '81bc54d4-37f7-5eba-b269-745694cbc41b', sourceType: 'note' }
    ]);
    const rendered = JSON.stringify(blocks);
    expect(rendered).not.toMatch(/never smoked|heterosexual|Humana|2393d095/i);
    expect(rendered).toMatch(/historical pneumonia note/i);
    expect(rendered).toMatch(/No known allergies/);
    expect(rendered).toMatch(/Historical pneumonia/);
  });

  it('hides patient-key note filenames in the displayed answer', () => {
    const leaked = 'Historical pneumonia resolved [p_485ba8c8597d4c5cb0fbda55317119a3-historical-pneumonia].';
    expect(displayAnswerText(leaked)).toBe('Historical pneumonia resolved.');
    expect(displayAnswerText(leaked)).not.toMatch(/p_485b/);
    expect(displayAnswerText('HbA1c: 6.35% [cite_id: obs_b22fc44a0faf4ef0]')).toBe('HbA1c: 6.35%');
  });

  it('dedupes same-label lab chips when the answer only names the measurement', () => {
    const systolic: AiCitation[] = [
      { id: 'obs_1', label: 'Systolic BP', sourceId: 'obs_1', sourceType: 'lab' },
      { id: 'obs_2', label: 'Systolic BP', sourceId: 'obs_2', sourceType: 'lab' },
      { id: 'obs_3', label: 'Systolic BP', sourceId: 'obs_3', sourceType: 'lab' }
    ];
    const result = citationsUsedInAnswer(answer({
      answer: 'Systolic BP: 130 mmHg, 127 mmHg, 121 mmHg',
      citations: systolic
    }));
    expect(result).toHaveLength(1);
    expect(result[0].label).toBe('Systolic BP');
  });

  it('formats a markdown lab dump into a title and list without cite ids', () => {
    const raw = '**Latest laboratory results** - Carbon dioxide, total: **22.45 mmol/L** [obs_16348755b41e419d] - Creatinine: **1.35 mg/dL** [obs_5996ca9ce86b461e]';
    expect(displayAnswerText(raw)).not.toMatch(/obs_/);
    expect(displayAnswerText('Chloride: 101.86 mmol/L [obs_7e412390e')).toBe('Chloride: 101.86 mmol/L');
    const blocks = answerBlocks(raw);
    expect(blocks[0]).toEqual({ type: 'p', parts: [{ text: 'Latest laboratory results', bold: true }] });
    expect(blocks[1]?.type).toBe('list');
    if (blocks[1]?.type !== 'list') throw new Error('expected list');
    expect(blocks[1].items).toHaveLength(2);
    expect(blocks[1].items[1]).toEqual([
      { text: 'Creatinine: ' },
      { text: '1.35 mg/dL', bold: true },
      { text: ' ' },
      { text: 'Lab', citeId: 'obs_5996ca9ce86b461e' }
    ]);
  });

  it('maps policy reasons and retrieval steps for the panel', () => {
    expect(policyReasonLabel('no_authorized_evidence')).toBe('No authorized records matched this question.');
    expect(policyReasonLabel('nemoclaw_unavailable')).toBe(
      'NemoClaw was unavailable. No substitute answer was used.'
    );
    expect(policyReasonLabel('named_patient_mismatch')).toBe(
      'That question names someone other than the open chart, so it was blocked.'
    );
    expect(policyReasonLabel('other_patients')).toBe(
      "Ask answers only this open chart. Other patients on today's schedule are not in these records."
    );
    expect(policyReasonLabel('mystery')).toBe('');
    expect(friendlyRetrievalSteps(['Minted run token', 'Searched authorized structured rows'])).toEqual([
      'Started a scoped search',
      'Searched authorized labs, conditions, and medications'
    ]);
    expect(friendlyRetrievalSteps(['Read authorized identity banner'])).toEqual([
      'Read the identity banner for this open chart'
    ]);
    expect(friendlyRetrievalSteps(['Searched authorized appointments'])).toEqual([
      'Searched booked appointments on this chart'
    ]);
    expect(friendlyRetrievalSteps(['Reading visible /tools/query rows'])).toEqual([
      'Completed an authorized retrieval step'
    ]);
  });
});
