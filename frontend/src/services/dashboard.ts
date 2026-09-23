import type { AuditRow, Me, Persona, QueryResponse } from '../types/api';
import type { AttentionItem, FollowUp, MedicalDocument, PatientSummary, TimelineEvent } from '../types/patient360';
import { actorAccessLabel, personAccessLabel } from './accessLevel';
import { groupConsecutiveAuditEvents } from './auditLabels';

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

export function nextEncounter(rows: Record<string, unknown>[]): { start: string; type: string; reason: string; practitioner: string; status: string } | null {
  const pending = rows
    .filter(row => ['booked', 'pending'].includes(String(row.status ?? '')))
    .map(row => ({
      start: String(row.started_at ?? row.start ?? ''),
      type: String(row.dept ?? row.service_type ?? row.type_code ?? 'Appointment'),
      reason: String(row.type_display ?? row.reason_display ?? ''),
      practitioner: String(row.practitioner_user_id ?? ''),
      status: String(row.status ?? '')
    }))
    .sort((a, b) => a.start.localeCompare(b.start));
  return pending[0] ?? null;
}

export function practitionerName(userId: string | undefined, personas: Array<Pick<Persona, 'user_id' | 'display' | 'role' | 'panels'>>): string {
  if (!userId) return '';
  const persona = personas.find(entry => entry.user_id === userId);
  if (!persona) return 'Clinician';
  return personAccessLabel(persona);
}

export function isAbnormalLab(row: Record<string, unknown>): boolean {
  return !row.redacted && ['H', 'L', 'HH', 'LL', 'A'].includes(String(row.interpretation ?? ''));
}

export function deriveBriefing(me: Me | null, patients: PatientSummary[]): Array<{ id: string; text: string; patientId?: string }> {
  const name = me?.display?.trim();
  const lines: Array<{ id: string; text: string; patientId?: string }> = [
    {
      id: 'brief-greeting',
      text: name ? `Good morning, ${name}.` : me ? 'Good morning.' : "Sign in to see today's summary."
    }
  ];
  for (const patient of patients.filter(item => item.status === 'Visible')) {
    lines.push({
      id: `brief-${patient.id}`,
      text: `${patient.fullName} is on your roster.`,
      patientId: patient.id
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
        description: `Review ${String(row.display ?? row.code ?? 'lab')} for ${patient.fullName}`,
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
        priority: String(row.status) === 'pending' ? 'High' : 'Normal',
        clinicianId: String(row.practitioner_user_id ?? '') || undefined
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

export function activityFromAudit(
  rows: AuditRow[],
  patients: Array<{ id: string; fullName: string }> = [],
  personas: Array<Pick<Persona, 'user_id' | 'display' | 'role' | 'panels'>> = []
): TimelineEvent[] {
  const patientNames: Record<string, string> = {};
  for (const patient of patients) {
    const name = patient.fullName?.trim();
    if (!name || name === 'Patient' || /p_[0-9a-f]/i.test(name)) continue;
    patientNames[patient.id] = name;
  }
  const byId = new Map(rows.map(row => [row.id, row]));
  return groupConsecutiveAuditEvents(rows, 12, patientNames).map(item => {
    const source = byId.get(item.id);
    const actor = actorAccessLabel(source?.agent_user, personas);
    return {
      id: item.id,
      kind: 'note',
      date: item.date,
      title: item.title,
      summary: item.summary,
      actor: actor && actor !== 'System' ? actor : undefined,
      tags: ['activity'],
      provenance: 'clinical'
    };
  });
}

export function attachEncounters(patients: PatientSummary[], encountersByKey: Record<string, QueryResponse | null>): PatientSummary[] {
  return patients.map(patient => {
    const next = nextEncounter(encountersByKey[patient.id]?.rows ?? []);
    return {
      ...patient,
      appointmentTime: next?.start ? next.start.slice(11, 16) || next.start.slice(0, 10) : patient.appointmentTime,
      appointmentType: next?.type ?? patient.appointmentType,
      appointmentClinician: next?.practitioner || patient.appointmentClinician,
      reasonForVisit: next?.reason || patient.reasonForVisit
    };
  }).sort((a, b) => {
    const at = a.appointmentTime || '\uffff';
    const bt = b.appointmentTime || '\uffff';
    return at.localeCompare(bt);
  });
}
