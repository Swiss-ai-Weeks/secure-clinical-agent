import { describe, expect, it } from 'vitest';
import {
  chartSection,
  describeAuditEvent,
  groupConsecutiveAuditEvents,
  humanizeAgent
} from '../../src/services/auditLabels';
import type { AuditRow } from '../../src/types/api';

function row(partial: Partial<AuditRow> & Pick<AuditRow, 'id' | 'event_type'>): AuditRow {
  return {
    recorded_at: '2026-09-21T12:00:00Z',
    agent_user: 'u_chen',
    purpose_of_event: 'TREAT',
    entity_patient: 'p_101',
    entity_resource: null,
    outcome: '0',
    reason_code: null,
    ...partial
  };
}

describe('auditLabels', () => {
  it('humanizes agent ids without showing raw keys', () => {
    expect(humanizeAgent('u_chen')).toBe('Chen');
    expect(humanizeAgent(null)).toBe('System');
  });

  it('maps resource tokens to chart sections', () => {
    expect(chartSection('clinical_rows/labs')).toBe('labs');
    expect(chartSection('clinical_rows/meds')).toBe('medications');
    expect(chartSection('notes')).toBe('notes');
    expect(chartSection('imaging_report')).toBe('imaging');
    expect(chartSection('identity/banner')).toBe('patient identity');
    expect(chartSection('/tools/query')).toBeNull();
  });

  it('describes tool calls and decisions in plain language', () => {
    expect(describeAuditEvent(row({ id: 't1', event_type: 'tool_call', entity_resource: 'clinical_rows/labs' })).title).toBe(
      'Opened labs'
    );
    expect(describeAuditEvent(row({ id: 't2', event_type: 'tool_call', entity_resource: 'notes' })).title).toBe(
      'Opened notes'
    );
    expect(describeAuditEvent(row({ id: 't3', event_type: 'tool_call', entity_resource: null })).title).toBe(
      'Viewed the chart'
    );
    expect(
      describeAuditEvent(
        row({ id: 'd1', event_type: 'decision', reason_code: 'relationship', outcome: '0', entity_resource: 'notes' }),
        { p_101: 'Norman Hettinger' }
      ).title
    ).toBe('Care team access to notes for Norman Hettinger');
    expect(
      describeAuditEvent(
        row({
          id: 'd2',
          event_type: 'decision',
          reason_code: 'relationship_missing_or_expired',
          outcome: '8',
          entity_resource: 'clinical_rows/labs'
        }),
        { p_101: 'Norman Hettinger' }
      )
    ).toEqual({
      title: 'Not allowed to open labs for Norman Hettinger',
      summary: 'Not on the care team',
      date: expect.stringMatching(/21 Sept? 2026 · 12:00|21 Sep 2026 · 12:00/)
    });
  });

  it('never surfaces implementation vocabulary as the primary line', () => {
    const titles = [
      describeAuditEvent(row({ id: 'a', event_type: 'tool_call', entity_resource: 'clinical_rows/labs' })).title,
      describeAuditEvent(row({ id: 'b', event_type: 'decision', reason_code: 'relationship' })).title,
      describeAuditEvent(row({ id: 'c', event_type: 'login' })).title
    ].join(' ');
    expect(titles).not.toMatch(/tool call|decision|relationship|PDP|sandbox|Clinical record/i);
  });

  it('names the patient and drops the matching care-team check', () => {
    const names = { p_101: 'Norman Hettinger', p_102: 'Shenna McLaughlin' };
    const grouped = groupConsecutiveAuditEvents([
      row({ id: '1', event_type: 'tool_call', entity_resource: 'notes', recorded_at: '2026-09-21T10:00:00Z' }),
      row({ id: '2', event_type: 'tool_call', entity_resource: 'notes', recorded_at: '2026-09-21T10:01:00Z' }),
      row({ id: '3', event_type: 'tool_call', entity_resource: 'notes', recorded_at: '2026-09-21T10:02:00Z' }),
      row({ id: '4', event_type: 'decision', entity_resource: 'notes', reason_code: 'relationship', recorded_at: '2026-09-21T10:03:00Z' }),
      row({ id: '5', event_type: 'tool_call', entity_patient: 'p_102', entity_resource: 'notes', recorded_at: '2026-09-21T10:04:00Z' })
    ], 12, names);
    expect(grouped).toHaveLength(2);
    expect(grouped[0].title).toBe('Opened notes for Shenna McLaughlin');
    expect(grouped[1].title).toBe('Opened notes for Norman Hettinger');
    expect(grouped[1].summary).toBe('3 times');
    expect(grouped[1].date).toMatch(/21 Sept? 2026 · 10:02|21 Sep 2026 · 10:02/);
    expect(grouped.map(item => item.title).join(' ')).not.toMatch(/p_101|p_102|care team access/i);
  });

  it('collapses one chart open into the patient and the sections', () => {
    const grouped = groupConsecutiveAuditEvents([
      row({ id: '1', event_type: 'tool_call', entity_resource: 'notes', recorded_at: '2026-09-21T14:02:00Z' }),
      row({ id: '2', event_type: 'decision', entity_resource: 'notes', reason_code: 'relationship', recorded_at: '2026-09-21T14:02:01Z' }),
      row({ id: '3', event_type: 'tool_call', entity_resource: 'clinical_rows/labs', recorded_at: '2026-09-21T14:02:02Z' }),
      row({ id: '4', event_type: 'decision', entity_resource: 'clinical_rows/labs', reason_code: 'relationship', recorded_at: '2026-09-21T14:02:03Z' }),
      row({ id: '5', event_type: 'identity_resolve', entity_resource: 'identity/banner', recorded_at: '2026-09-21T14:02:04Z' })
    ], 12, { p_101: 'Norman Hettinger' });
    expect(grouped).toHaveLength(1);
    expect(grouped[0].title).toBe("Opened Norman Hettinger's chart");
    expect(grouped[0].summary).toBe('Notes, labs, and identity');
    expect(grouped[0].date).toMatch(/14:02/);
  });
});
