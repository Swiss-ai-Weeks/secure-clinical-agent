import type { AuditRow, Me, QueryResponse } from '../types/api';
import type { AttentionItem, FollowUp, MedicalDocument, PatientSummary, TimelineEvent } from '../types/patient360';

export function filterPatients(patients: PatientSummary[], query: string): PatientSummary[] {
  const normalized = query.trim().toLowerCase();
  return patients
    .filter(patient => {
      const haystack = [patient.fullName, patient.id, patient.dateOfBirth].join(' ').toLowerCase();
      return !normalized || haystack.includes(normalized);
    })
    .map(patient => ({
      ...patient,
      resultMode: 'standard' as const,
      reason: 'Matched structured patient fields.'
    }));
}

export function nextEncounter(rows: Record<string, unknown>[]): { start: string; type: string; status: string } | null {
  const pending = rows
    .filter(row => ['booked', 'pending'].includes(String(row.status ?? '')))
    .map(row => ({
      start: String(row.started_at ?? row.start ?? ''),
      type: String(row.dept ?? row.service_type ?? row.type_code ?? 'Appointment'),
      status: String(row.status ?? '')
    }))
    .sort((a, b) => a.start.localeCompare(b.start));
  return pending[0] ?? null;
}

export function isAbnormalLab(row: Record<string, unknown>): boolean {
  return !row.redacted && ['H', 'L', 'HH', 'LL', 'A'].includes(String(row.interpretation ?? ''));
}

export function deriveBriefing(me: Me | null, patients: PatientSummary[]): Array<{ id: string; text: string; patientId?: string }> {
  const lines: Array<{ id: string; text: string; patientId?: string }> = [
    { id: 'brief-role', text: me ? `${me.role} · ${me.panels.length} panels gated by /me` : 'No session' }
  ];
  for (const patient of patients) {
    lines.push({
      id: `brief-${patient.id}`,
      text: patient.status === 'Visible' ? `${patient.fullName} (${patient.id}) is visible.` : `${patient.id} is not visible.`,
      patientId: patient.status === 'Visible' ? patient.id : undefined
    });
  }
  return lines;
}

export function deriveAttention(
  patients: PatientSummary[],
  labsByKey: Record<string, QueryResponse | null>
): AttentionItem[] {
  const items: AttentionItem[] = [];
  for (const patient of patients) {
    if (patient.warning) {
      items.push({
        id: `btg-${patient.id}`,
        patientId: patient.id,
        severity: 'urgent',
        title: `${patient.fullName}: break-glass`,
        detail: patient.warning,
        provenance: 'clinical'
      });
    }
    const labs = labsByKey[patient.id];
    if (labs?.redacted_count) {
      items.push({
        id: `redact-${patient.id}`,
        patientId: patient.id,
        severity: 'review',
        title: `${patient.fullName}: redacted labs`,
        detail: `${labs.redacted_count} laboratory row(s) redacted.`,
        provenance: 'clinical'
      });
    }
    for (const row of labs?.rows ?? []) {
      if (!isAbnormalLab(row)) continue;
      items.push({
        id: `lab-${patient.id}-${String(row.cite_id ?? row.display ?? items.length)}`,
        patientId: patient.id,
        severity: 'warning',
        title: `${patient.fullName}: ${String(row.display ?? row.code ?? 'Lab')} out of range`,
        detail: `${row.value_num ?? row.value_text ?? row.value_display ?? ''} ${row.unit ?? ''}`.trim(),
        provenance: 'clinical'
      });
    }
  }
  return items;
}

export function deriveFollowUps(input: {
  patients: PatientSummary[];
  labsByKey: Record<string, QueryResponse | null>;
  encountersByKey: Record<string, QueryResponse | null>;
  documentsByKey: Record<string, MedicalDocument[]>;
}): FollowUp[] {
  const tasks: FollowUp[] = [];
  for (const patient of input.patients.filter(item => item.status === 'Visible')) {
    for (const row of input.labsByKey[patient.id]?.rows ?? []) {
      if (!isAbnormalLab(row)) continue;
      tasks.push({
        id: `lab-${patient.id}-${String(row.cite_id ?? tasks.length)}`,
        patientId: patient.id,
        patient: patient.fullName,
        description: `Review ${String(row.display ?? row.code ?? 'lab')} for ${patient.id}`,
        dueDate: String(row.effective_at ?? '').slice(0, 10) || '—',
        source: 'Laboratory',
        priority: 'High'
      });
    }
    for (const row of input.encountersByKey[patient.id]?.rows ?? []) {
      if (!['booked', 'pending'].includes(String(row.status ?? ''))) continue;
      tasks.push({
        id: `enc-${patient.id}-${String(row.cite_id ?? tasks.length)}`,
        patientId: patient.id,
        patient: patient.fullName,
        description: `Confirm ${String(row.dept ?? 'clinic')} appointment (${row.status})`,
        dueDate: String(row.started_at ?? row.start ?? '').slice(0, 10) || '—',
        source: 'Appointments',
        priority: String(row.status) === 'pending' ? 'High' : 'Normal'
      });
    }
    for (const document of input.documentsByKey[patient.id] ?? []) {
      if (document.processingState !== 'pending-review') continue;
      tasks.push({
        id: `doc-${document.id}`,
        patientId: patient.id,
        patient: patient.fullName,
        description: `Review uploaded document ${document.title}`,
        dueDate: document.date || '—',
        source: 'Upload',
        priority: 'Normal'
      });
    }
  }
  return tasks;
}

export function activityFromAudit(rows: AuditRow[]): TimelineEvent[] {
  return rows.slice(0, 12).map(row => ({
    id: row.id,
    kind: 'note',
    date: (row.recorded_at || '').slice(0, 10) || '—',
    title: row.event_type,
    summary: [row.agent_user, row.entity_patient, row.reason_code].filter(Boolean).join(' · '),
    tags: [row.purpose_of_event || 'audit'],
    provenance: 'clinical'
  }));
}

export function attachEncounters(patients: PatientSummary[], encountersByKey: Record<string, QueryResponse | null>): PatientSummary[] {
  return patients.map(patient => {
    const next = nextEncounter(encountersByKey[patient.id]?.rows ?? []);
    return {
      ...patient,
      appointmentTime: next?.start ? next.start.slice(11, 16) || next.start.slice(0, 10) : patient.appointmentTime,
      appointmentType: next?.type ?? patient.appointmentType
    };
  });
}
