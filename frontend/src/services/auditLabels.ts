import type { AuditRow } from '../types/api';
import { formatLabDate } from './patientRecord';

/** Sections clinicians recognize; never surface tool paths or raw codes. */
const SECTION_BY_TOKEN: Record<string, string> = {
  labs: 'labs',
  meds: 'medications',
  medications: 'medications',
  conditions: 'conditions',
  encounters: 'appointments',
  allergies: 'allergies',
  diet: 'diet orders',
  notes: 'notes',
  imaging: 'imaging',
  imaging_report: 'imaging',
  imaging_metadata: 'imaging',
  chat: 'Ask',
  documents: 'documents',
  upload: 'documents',
  appointment: 'appointments',
  appointments: 'appointments',
  consent: 'sharing',
  consents: 'sharing',
  identity: 'patient identity',
  banner: 'patient identity',
  vault: 'patient identity',
  clinical_rows: 'chart',
  aggregate: 'group results'
};

const ALLOW_REASON: Record<string, string> = {
  relationship: 'Care team access',
  self_match: 'Their own record',
  break_glass: 'Emergency access',
  guardian: 'Guardian access',
  delegate: 'Shared access'
};

const ROUTINE_ALLOW = new Set(['relationship', 'self_match']);

const DENY_REASONS = new Set([
  'relationship_missing_or_expired',
  'self_mismatch',
  'break_glass_role_not_allowed',
  'delegate_authority_missing',
  'aggregate_only',
  'aggregate_project_missing',
  'aggregate_role_not_allowed',
  'overlap_blocked'
]);

export function humanizeAgent(agent: string | null | undefined): string {
  if (!agent) return 'System';
  if (/^u_/.test(agent)) {
    return agent.replace(/^u_/, '').replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase());
  }
  return agent;
}

export function formatAuditDate(value: string | null | undefined): string {
  if (!value) return '—';
  const label = formatLabDate(value);
  return label || value.slice(0, 10) || '—';
}

export function formatAuditTime(value: string | null | undefined): string {
  if (!value || !value.includes('T')) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    timeZone: 'UTC'
  }).format(date);
}

function formatAuditStamp(value: string | null | undefined): string {
  const day = formatAuditDate(value);
  const time = formatAuditTime(value);
  return time ? `${day} · ${time}` : day;
}

function looksLikeOpaqueId(token: string): boolean {
  return (
    /^p_[0-9a-f]+$/i.test(token) ||
    /^u_/.test(token) ||
    /^[0-9a-f]{8}-[0-9a-f-]{20,}$/i.test(token) ||
    /^1\.\d+(\.\d+)+$/.test(token) ||
    token.includes('/')
  );
}

/** Chart section from entity_resource, or null when unknown. */
export function chartSection(resource: string | null | undefined): string | null {
  if (!resource) return null;
  const cleaned = resource.replace(/^\/+/, '').replace(/^tools\//, '');
  const parts = cleaned.split(/[/:]+/).filter(Boolean);
  const generic = new Set(['clinical_rows', 'aggregate', 'tuple']);
  for (const part of [...parts].reverse()) {
    const key = part.toLowerCase();
    if (generic.has(key) || looksLikeOpaqueId(part)) continue;
    if (SECTION_BY_TOKEN[key]) return SECTION_BY_TOKEN[key];
  }
  for (const part of parts) {
    const key = part.toLowerCase();
    if (SECTION_BY_TOKEN[key]) return SECTION_BY_TOKEN[key];
  }
  if (parts.some(part => looksLikeOpaqueId(part))) {
    if (/study|instance|series|orthanc|dicom/i.test(cleaned)) return 'imaging';
    return null;
  }
  return null;
}

function isDenied(row: AuditRow): boolean {
  const outcome = String(row.outcome ?? '');
  if (['4', '8', '12'].includes(outcome)) return true;
  const reason = String(row.reason_code ?? '');
  if (DENY_REASONS.has(reason)) return true;
  if (/_missing|_denied|_not_allowed|_blocked|_mismatch$/i.test(reason)) return true;
  return false;
}

function denyDetail(reason: string): string {
  switch (reason) {
    case 'relationship_missing_or_expired':
      return 'Not on the care team';
    case 'self_mismatch':
      return 'Not their record';
    case 'break_glass_role_not_allowed':
      return 'This role cannot use emergency access';
    case 'delegate_authority_missing':
      return 'Sharing was not authorized';
    case 'aggregate_only':
    case 'aggregate_project_missing':
    case 'aggregate_role_not_allowed':
      return 'Group results only';
    case 'overlap_blocked':
      return 'This would identify someone in the group';
    default:
      return '';
  }
}

function displayPatient(row: AuditRow, patientNames?: Record<string, string>): string | null {
  const key = row.entity_patient;
  if (!key || !patientNames) return null;
  const name = patientNames[key]?.trim();
  if (!name || name === 'Patient' || looksLikeOpaqueId(name) || /p_[0-9a-f]/i.test(name)) return null;
  return name;
}

function withPatient(action: string, patient: string | null, about = false): string {
  if (!patient) return action;
  return about ? `${action} about ${patient}` : `${action} for ${patient}`;
}

function decisionTitle(row: AuditRow, patient: string | null): string {
  const reason = String(row.reason_code ?? '');
  const section = chartSection(row.entity_resource);
  if (isDenied(row)) {
    if (section === 'Ask') return withPatient('Ask was not allowed', patient, true);
    if (section) return withPatient(`Not allowed to open ${section}`, patient);
    return 'Not allowed';
  }
  const phrase = ALLOW_REASON[reason] ?? 'Access checked';
  const action = section ? `${phrase} to ${section}` : phrase;
  return withPatient(action, patient);
}

function toolCallTitle(row: AuditRow, patient: string | null): string {
  const section = chartSection(row.entity_resource);
  if (isDenied(row)) {
    if (section === 'Ask') return withPatient('Ask was not allowed', patient, true);
    if (section) return withPatient(`Could not open ${section}`, patient);
    return 'Not allowed';
  }
  if (section === 'Ask') return withPatient('Asked a question', patient, true);
  if (section === 'chart' || !section) return withPatient('Viewed the chart', patient);
  if (section === 'group results') return 'Viewed group results';
  if (section === 'patient identity') return withPatient('Viewed patient identity', patient);
  if (section === 'sharing') return withPatient('Updated sharing', patient);
  if (section === 'documents') return withPatient('Opened documents', patient);
  return withPatient(`Opened ${section}`, patient);
}

function eventTitle(row: AuditRow, patient: string | null): string {
  switch (row.event_type) {
    case 'tool_call':
      return toolCallTitle(row, patient);
    case 'decision':
      return decisionTitle(row, patient);
    case 'login':
      return 'Signed in';
    case 'logout':
      return 'Signed out';
    case 'consent_granted':
      return isDenied(row) ? withPatient('Sharing not granted', patient) : withPatient('Shared access', patient);
    case 'consent_revoked':
      return withPatient('Revoked shared access', patient);
    case 'break_glass':
      return isDenied(row) ? withPatient('Emergency access not allowed', patient) : withPatient('Opened emergency access', patient);
    case 'step_up':
      return 'Confirmed identity';
    case 'media_sign':
    case 'media_fetch':
      return isDenied(row) ? withPatient('Imaging not allowed', patient) : withPatient('Opened imaging', patient);
    case 'ingest':
      return 'Imported records';
    case 'upload':
      return isDenied(row) ? withPatient('Upload not allowed', patient) : withPatient('Uploaded a document', patient);
    case 'identity_resolve':
      return isDenied(row) ? withPatient('Patient identity not available', patient) : withPatient('Viewed patient identity', patient);
    case 'appointment_booked':
      return isDenied(row) ? withPatient('Appointment not booked', patient) : withPatient('Booked an appointment', patient);
    case 'appointment_cancelled':
      return withPatient('Cancelled an appointment', patient);
    default: {
      const section = chartSection(row.entity_resource);
      if (section) return withPatient(`Chart activity · ${section}`, patient);
      return withPatient('Chart activity', patient);
    }
  }
}

function actionKey(row: AuditRow): string {
  return `${row.entity_patient ?? ''}|${chartSection(row.entity_resource) ?? ''}|${formatAuditDate(row.recorded_at)}`;
}

function isCoveredRoutineDecision(row: AuditRow, covered: Set<string>): boolean {
  if (row.event_type !== 'decision' || isDenied(row)) return false;
  if (!ROUTINE_ALLOW.has(String(row.reason_code ?? ''))) return false;
  return covered.has(actionKey(row));
}

export interface AuditDisplay {
  title: string;
  summary: string;
  date: string;
}

/** Plain-language title for one audit row. Patient names come from the roster, never raw keys. */
export function describeAuditEvent(row: AuditRow, patientNames?: Record<string, string>): AuditDisplay {
  const patient = displayPatient(row, patientNames);
  const reason = String(row.reason_code ?? '');
  const detail = isDenied(row) ? denyDetail(reason) : '';
  return {
    title: eventTitle(row, patient),
    summary: detail,
    date: formatAuditStamp(row.recorded_at)
  };
}

export interface GroupedAuditDisplay extends AuditDisplay {
  id: string;
  count: number;
}

const CHART_READS = new Set(['tool_call', 'identity_resolve', 'media_sign', 'media_fetch']);
const BURST_MS = 3 * 60 * 1000;

function rowTime(row: AuditRow): number {
  const time = row.recorded_at ? Date.parse(row.recorded_at) : Number.NaN;
  return Number.isNaN(time) ? 0 : time;
}

function isChartRead(row: AuditRow): boolean {
  if (isDenied(row) || !row.entity_patient || !chartSection(row.entity_resource)) return false;
  if (CHART_READS.has(row.event_type)) return true;
  return row.event_type === 'decision' && ROUTINE_ALLOW.has(String(row.reason_code ?? ''));
}

function sectionPhrase(sections: string[]): string {
  const labels = sections.map(section => (section === 'patient identity' ? 'identity' : section));
  const phrase = labels.length <= 1
    ? labels[0] ?? ''
    : labels.length === 2
      ? `${labels[0]} and ${labels[1]}`
      : `${labels.slice(0, -1).join(', ')}, and ${labels[labels.length - 1]}`;
  return phrase ? phrase.charAt(0).toUpperCase() + phrase.slice(1) : '';
}

function burstFrom(rows: AuditRow[], patientNames?: Record<string, string>): GroupedAuditDisplay & { time: number } {
  const newest = [...rows].sort((a, b) => rowTime(b) - rowTime(a))[0];
  const patient = displayPatient(newest, patientNames);
  const counts = new Map<string, number>();
  const order: string[] = [];
  let emergency = false;
  for (const row of [...rows].sort((a, b) => rowTime(a) - rowTime(b))) {
    if (row.reason_code === 'break_glass' || row.event_type === 'break_glass') emergency = true;
    const section = chartSection(row.entity_resource);
    if (!section) continue;
    if (!order.includes(section)) order.push(section);
    if (row.event_type !== 'decision') counts.set(section, (counts.get(section) ?? 0) + 1);
  }
  const stamp = formatAuditStamp(newest.recorded_at);
  const clinical = order.filter(section => section !== 'sharing');
  const shown = clinical.length ? clinical : order;
  if (shown.length === 1 && shown[0] === 'sharing') {
    return {
      time: rowTime(newest),
      id: newest.id,
      title: patient ? `Reviewed sharing for ${patient}` : 'Reviewed sharing',
      summary: emergency ? 'Emergency access' : '',
      date: stamp,
      count: 1
    };
  }
  if (shown.length === 1) {
    const sample = rows.find(row => row.event_type !== 'decision') ?? newest;
    const display = describeAuditEvent(sample, patientNames);
    const times = counts.get(shown[0]) ?? 0;
    return {
      time: rowTime(newest),
      id: newest.id,
      title: display.title,
      summary: [emergency ? 'Emergency access' : '', times > 1 ? `${times} times` : display.summary].filter(Boolean).join(' · '),
      date: stamp,
      count: Math.max(times, 1)
    };
  }
  const title = patient ? `Opened ${patient}'s chart` : 'Opened a chart';
  return {
    time: rowTime(newest),
    id: newest.id,
    title,
    summary: [emergency ? 'Emergency access' : '', sectionPhrase(shown)].filter(Boolean).join(' · '),
    date: stamp,
    count: rows.length
  };
}

/**
 * One line per chart visit. Section fetches and their care-team checks from the
 * same patient, within a few minutes, become a single line naming that patient.
 * A repeat of one section stays "Opened notes for … / 3 times".
 */
export function groupConsecutiveAuditEvents(
  rows: AuditRow[],
  limit = 12,
  patientNames?: Record<string, string>
): GroupedAuditDisplay[] {
  const covered = new Set(rows.filter(row => row.event_type !== 'decision').map(actionKey));
  const visible = rows.filter(row => !isCoveredRoutineDecision(row, covered));
  const byPatient = new Map<string, AuditRow[]>();
  const singles: AuditRow[] = [];
  for (const row of visible) {
    if (!isChartRead(row) || !row.entity_patient) {
      singles.push(row);
      continue;
    }
    const list = byPatient.get(row.entity_patient) ?? [];
    list.push(row);
    byPatient.set(row.entity_patient, list);
  }

  const items: Array<GroupedAuditDisplay & { time: number }> = [];
  for (const list of byPatient.values()) {
    const ordered = [...list].sort((a, b) => rowTime(b) - rowTime(a));
    let current: AuditRow[] = [];
    const flush = () => {
      if (!current.length) return;
      items.push(burstFrom(current, patientNames));
      current = [];
    };
    for (const row of ordered) {
      if (current.length && rowTime(current[current.length - 1]) - rowTime(row) > BURST_MS) flush();
      current.push(row);
    }
    flush();
  }
  for (const row of singles) {
    const display = describeAuditEvent(row, patientNames);
    items.push({ time: rowTime(row), id: row.id, ...display, count: 1 });
  }
  return items
    .sort((a, b) => b.time - a.time)
    .slice(0, limit)
    .map(({ time: _time, ...item }) => item);
}
