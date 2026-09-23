import { describe, expect, it } from 'vitest';
import {
  activityFromAudit,
  attachEncounters,
  deriveAttention,
  deriveBriefing,
  deriveFollowUps,
  filterPatients,
  isAbnormalLab,
  nextEncounter,
  practitionerName
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
      { status: 'booked', started_at: '2026-10-02T09:30:00Z', dept: 'cardiology', type_display: 'Encounter for check up', practitioner_user_id: 'u_okafor' }
    ])).toEqual({
      start: '2026-10-02T09:30:00Z',
      type: 'cardiology',
      reason: 'Encounter for check up',
      practitioner: 'u_okafor',
      status: 'booked'
    });
  });

  it('treats high/low interpretations as abnormal', () => {
    expect(isAbnormalLab({ interpretation: 'H' })).toBe(true);
    expect(isAbnormalLab({ interpretation: 'N' })).toBe(false);
    expect(isAbnormalLab({ interpretation: 'H', redacted: true })).toBe(false);
  });

  it('builds briefing, attention, and follow-ups from live rows', () => {
    const me = { role: 'attending', panels: ['labs', 'appointments'], display: 'Dr. Chen' } as Me;
    const briefing = deriveBriefing(me, [visible, hidden]);
    expect(briefing[0].text).toBe('Good morning, Dr. Chen.');
    expect(briefing[0].text).not.toMatch(/attending|panels|session/i);
    expect(briefing.some(line => line.text.includes('Elisabeth'))).toBe(true);
    expect(briefing.some(line => line.text.includes('(') && line.text.includes('p_'))).toBe(false);
    expect(briefing.some(line => line.text.includes('not visible') || line.text.includes('p_205'))).toBe(false);
    expect(briefing.some(line => line.text.includes('/me'))).toBe(false);

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
    expect(tasks.some(task => task.description.includes('p_101'))).toBe(false);
    expect(tasks.some(task => task.description.includes('Elisabeth'))).toBe(true);
  });

  it('maps audit rows and encounter times onto the home list', () => {
    const activity = activityFromAudit([
      {
        id: '1',
        recorded_at: '2026-09-18T10:15:00Z',
        event_type: 'login',
        agent_user: 'u_chen',
        purpose_of_event: 'TREAT',
        entity_patient: 'p_101',
        entity_resource: null,
        outcome: '0',
        reason_code: null
      },
      {
        id: '2',
        recorded_at: '2026-09-21T09:00:00Z',
        event_type: 'tool_call',
        agent_user: 'u_chen',
        purpose_of_event: 'TREAT',
        entity_patient: 'p_101',
        entity_resource: 'clinical_rows/labs',
        outcome: '0',
        reason_code: 'relationship'
      },
      {
        id: '3',
        recorded_at: '2026-09-21T09:01:00Z',
        event_type: 'tool_call',
        agent_user: 'u_chen',
        purpose_of_event: 'TREAT',
        entity_patient: 'p_101',
        entity_resource: 'clinical_rows/labs',
        outcome: '0',
        reason_code: 'relationship'
      },
      {
        id: '4',
        recorded_at: '2026-09-21T09:02:00Z',
        event_type: 'decision',
        agent_user: 'u_chen',
        purpose_of_event: 'TREAT',
        entity_patient: 'p_101',
        entity_resource: 'clinical_rows/labs',
        outcome: '0',
        reason_code: 'relationship'
      }
    ] as AuditRow[], [visible], [{ user_id: 'u_chen', display: 'Dr. Sarah Chen', role: 'attending', credential_level: 3 }]);
    expect(activity).toHaveLength(2);
    expect(activity[0].actor).toBe('Dr. Sarah Chen · Privileged · Attending');
    expect(activity[1].actor).toBe('Dr. Sarah Chen · Privileged · Attending');
    expect(JSON.stringify(activity)).not.toMatch(/u_chen|p_101/);
    expect(activity[0].title).toBe('Opened labs for Elisabeth Keller');
    expect(activity[0].summary).toBe('2 times');
    expect(activity[0].date).toMatch(/21 Sept? 2026 · 09:01|21 Sep 2026 · 09:01/);
    expect(activity[1].title).toBe('Signed in');
    expect(activity[1].summary).toBe('');
    expect(activity[1].summary).not.toMatch(/p_101|u_chen/);
    expect(activity[1].date).toMatch(/18 Sept? 2026 · 10:15|18 Sep 2026 · 10:15/);
    expect(activity.some(item => /tool call|decision|relationship|Clinical record|Allowed because/i.test(item.title))).toBe(false);
    expect(activity.some(item => /tool call|decision|relationship/i.test(item.summary))).toBe(false);
    const attached = attachEncounters(
      [
        { ...visible, id: 'p_late', fullName: 'Late' },
        { ...visible, id: 'p_none', fullName: 'No slot' },
        visible
      ],
      {
        p_101: { ...labs, dataset: 'encounters', rows: [{ status: 'booked', started_at: '2026-09-22T08:30:00Z', dept: 'internal medicine', type_display: 'Pneumonia follow-up', practitioner_user_id: 'u_chen' }] },
        p_late: { ...labs, dataset: 'encounters', rows: [{ status: 'booked', started_at: '2026-09-22T10:00:00Z', dept: 'cardiology', type_display: 'Hypertension follow-up' }] }
      }
    );
    expect(attached.map(patient => patient.id)).toEqual(['p_101', 'p_late', 'p_none']);
    expect(attached[0].appointmentTime).toBe('08:30');
    expect(attached[0].appointmentType).toBe('internal medicine');
    expect(attached[0].appointmentClinician).toBe('u_chen');
    expect(attached[0].reasonForVisit).toBe('Pneumonia follow-up');
    expect(practitionerName('u_chen', [{ user_id: 'u_chen', display: 'Dr. Sarah Chen' }])).toBe('Dr. Sarah Chen');
    expect(practitionerName('u_chen', [{ user_id: 'u_chen', display: 'Dr. Sarah Chen', role: 'attending', credential_level: 3 }])).toBe('Dr. Sarah Chen · Privileged · Attending');
    expect(practitionerName('u_okafor', [{ user_id: 'u_chen', display: 'Dr. Sarah Chen' }])).toBe('Clinician');
  });
});
