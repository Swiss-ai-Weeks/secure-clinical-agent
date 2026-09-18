import { describe, expect, it } from 'vitest';
import {
  activityFromAudit,
  attachEncounters,
  deriveAttention,
  deriveBriefing,
  deriveFollowUps,
  filterPatients,
  isAbnormalLab,
  nextEncounter
} from '../../src/services/dashboard';
import type { AuditRow, Me, QueryResponse } from '../../src/types/api';
import type { PatientSummary } from '../../src/types/patient360';

const visible: PatientSummary = {
  id: 'p_101',
  fullName: 'Elisabeth Keller',
  age: 65,
  dateOfBirth: '1961-04-17',
  phone: '',
  email: '',
  status: 'Visible',
  avatarInitials: 'EK',
  assignedClinician: ''
};

const hidden: PatientSummary = {
  ...visible,
  id: 'p_205',
  fullName: 'Not visible (p_205)',
  status: 'Hidden',
  avatarInitials: '05'
};

const labs: QueryResponse = {
  patient_key: 'p_101',
  dataset: 'labs',
  rows: [
    { cite_id: 'obs_a1', display: 'HbA1c', value_num: 7.9, unit: '%', interpretation: 'H', effective_at: '2026-09-10' }
  ],
  row_count: 1,
  redacted_count: 1,
  suppressed_cells: 0,
  obligations: {},
  decision: {
    effect: 'permit',
    reason_code: 'ok',
    policy_id: 'pdp',
    policy_version: 'test',
    relation: 'can_read_clinical',
    purpose_of_event: 'TREAT',
    compliance_flag: false
  },
  audit_id: 'a1'
};

describe('dashboard derivation', () => {
  it('filters patients on visible identity fields only', () => {
    const results = filterPatients([visible, hidden], 'elisabeth');
    expect(results).toHaveLength(1);
    expect(results[0].resultMode).toBe('standard');
    expect(results[0].reason).toContain('Matched structured');
  });

  it('picks the next booked encounter', () => {
    expect(nextEncounter([
      { status: 'finished', started_at: '2026-01-01T09:00:00Z' },
      { status: 'booked', started_at: '2026-10-02T09:30:00Z', dept: 'cardiology' }
    ])).toEqual({ start: '2026-10-02T09:30:00Z', type: 'cardiology', status: 'booked' });
  });

  it('treats high/low interpretations as abnormal', () => {
    expect(isAbnormalLab({ interpretation: 'H' })).toBe(true);
    expect(isAbnormalLab({ interpretation: 'N' })).toBe(false);
    expect(isAbnormalLab({ interpretation: 'H', redacted: true })).toBe(false);
  });

  it('builds briefing, attention, and follow-ups from live rows', () => {
    const me = { role: 'attending', panels: ['labs', 'appointments'], display: 'Dr. Chen' } as Me;
    const briefing = deriveBriefing(me, [visible, hidden]);
    expect(briefing[0].text).toContain('attending');
    expect(briefing.some(line => line.text.includes('not visible'))).toBe(true);

    const flagged = { ...visible, warning: 'Break-glass active' };
    const attention = deriveAttention([flagged], { p_101: labs });
    expect(attention.some(item => item.severity === 'urgent')).toBe(true);
    expect(attention.some(item => item.title.includes('HbA1c'))).toBe(true);

    const tasks = deriveFollowUps({
      patients: [visible],
      labsByKey: { p_101: labs },
      encountersByKey: {
        p_101: { ...labs, dataset: 'encounters', rows: [{ cite_id: 'enc1', status: 'pending', dept: 'cardiology', started_at: '2026-10-02' }] }
      },
      documentsByKey: {
        p_101: [{ id: 'doc1', title: 'Upload', type: 'note', date: '2026-09-18', source: 'upload', processingState: 'pending-review', uploadedBy: 'patient' }]
      }
    });
    expect(tasks.map(task => task.source)).toEqual(expect.arrayContaining(['Laboratory', 'Appointments', 'Upload']));
  });

  it('maps audit rows and encounter times onto the home list', () => {
    const activity = activityFromAudit([
      { id: '1', recorded_at: '2026-09-18T10:15:00Z', event_type: 'login', agent_user: 'u_chen', purpose_of_event: 'TREAT', entity_patient: 'p_101', entity_resource: null, outcome: '0', reason_code: null }
    ] as AuditRow[]);
    expect(activity[0].title).toBe('login');
    expect(attachEncounters([visible], {
      p_101: { ...labs, dataset: 'encounters', rows: [{ status: 'booked', started_at: '2026-10-02T09:30:00Z', dept: 'cardiology' }] }
    })[0].appointmentType).toBe('cardiology');
  });
});
