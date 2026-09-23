import type { IdentityBanner, ImagingResponse, NotesResponse, QueryResponse } from '../types/api';
import type { ClinicalNote, LabFlag, LabResult, MedicalDocument, Medication, Patient, PatientSummary, TimelineEvent } from '../types/patient360';

export function ageFromIso(dateOfBirth: string): number {
  const born = new Date(dateOfBirth);
  if (Number.isNaN(born.getTime())) return 0;
  const now = new Date();
  let age = now.getUTCFullYear() - born.getUTCFullYear();
  const month = now.getUTCMonth() - born.getUTCMonth();
  if (month < 0 || (month === 0 && now.getUTCDate() < born.getUTCDate())) age -= 1;
  return age;
}

function initials(given: string, family: string, fallback: string): string {
  const letters = `${given.charAt(0)}${family.charAt(0)}`.toUpperCase();
  return letters.trim() || fallback.slice(0, 2).toUpperCase();
}

/** Synthea appends digits to given/family names so they cannot be mistaken for real people. */
export function cleanSyntheaName(value: string): string {
  return value.replace(/\d+/g, ' ').replace(/\s+/g, ' ').trim();
}

function text(value: unknown): string {
  if (value == null) return '';
  return String(value);
}

/** Raw patient keys, sandbox ids, and UUID-like MRNs must not appear as display labels. */
function looksLikeInternalId(value: string): boolean {
  const raw = value.trim();
  if (!raw) return false;
  if (/^p_[0-9a-f]/i.test(raw) || /^p\d{2,}$/i.test(raw)) return true;
  if (/^p360-s-/i.test(raw)) return true;
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(raw)) return true;
  return false;
}

const LAB_LABELS: Array<[RegExp, string]> = [
  [/hemoglobin a1c/i, 'HbA1c'],
  [/^creatinine\b/i, 'Creatinine'],
  [/^potassium\b/i, 'Potassium'],
  [/glomerular filtration/i, 'eGFR'],
  [/^systolic blood pressure/i, 'Systolic BP'],
  [/^diastolic blood pressure/i, 'Diastolic BP'],
  [/blood pressure panel/i, ''],
  [/^cholesterol\b/i, 'Cholesterol'],
  [/leukocytes|^wbc\b/i, 'WBC'],
  [/^hemoglobin \[mass/i, 'Hemoglobin'],
  [/^eosinophils\b/i, 'Eosinophils'],
  [/oxygen saturation/i, 'Oxygen saturation'],
  [/respiratory rate/i, 'Respiratory rate'],
  [/^heart rate\b/i, 'Heart rate'],
  [/body temperature/i, 'Temperature'],
  [/c reactive protein|^crp\b/i, 'CRP']
];

const SURVEY_OR_SDOH = /^(are you|do you|have you|has |how |what was|within the last|housing status|employment status|highest level|primary insurance|tobacco smoking|stress level|discharged from|total score)/i;
const CLINICAL_CONDITION = /diabetes|prediabetes|hypertension|pneumonia|hypoxemia|thrombosis|coronavirus|covid|respiratory distress|kidney|asthma|depressive|depression|hyperlipidemia|pregnancy prevention/i;
const SNAPSHOT_LAB_LABELS = new Set([
  'Blood pressure',
  'Heart rate',
  'Respiratory rate',
  'Oxygen saturation',
  'Temperature',
  'HbA1c',
  'Glucose',
  'Creatinine',
  'eGFR',
  'Potassium',
  'Sodium',
  'Hemoglobin',
  'WBC',
  'CRP'
]);
const BRIEF_LAB_ORDER = [
  'Oxygen saturation',
  'Respiratory rate',
  'Blood pressure',
  'HbA1c',
  'eGFR',
  'Creatinine',
  'Heart rate'
];

function prettyLabLabel(display: string, code: string): string {
  const raw = display || code;
  for (const [pattern, label] of LAB_LABELS) {
    if (pattern.test(raw)) return label;
  }
  return raw.replace(/\s*\[[^\]]+\]/g, '').split(' in ')[0].trim() || raw;
}

function prettyUnit(unit: string): string {
  return unit
    .replaceAll('mm[Hg]', 'mmHg')
    .replaceAll('mL/min/{1.73_m2}', 'mL/min/1.73m²')
    .replaceAll('10*3/uL', '×10³/µL');
}

function asNumber(value: unknown): number | null {
  if (value == null || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

const CLINICAL_RANGES: Array<[RegExp, number | null, number | null]> = [
  [/hemoglobin a1c|^hba1c$/i, 4, 5.6],
  [/^glucose\b/i, 70, 199],
  [/^creatinine\b/i, 0.6, 1.3],
  [/glomerular filtration|^egfr$/i, 60, null],
  [/systolic blood pressure|^systolic bp$/i, 90, 140],
  [/diastolic blood pressure|^diastolic bp$/i, 60, 90],
  [/oxygen saturation/i, 95, 100],
  [/respiratory rate/i, 12, 20],
  [/^heart rate\b/i, 60, 100],
  [/body temperature|^temperature$/i, 36, 38],
  [/^potassium\b/i, 3.5, 5],
  [/^sodium\b/i, 135, 145],
  [/leukocytes|^wbc$/i, 4, 11],
  [/^hemoglobin \[mass|^hemoglobin$/i, 12, 16],
  [/c reactive protein|^crp$/i, null, 10]
];

function clinicalRange(label: string, display: string): { low: number | null; high: number | null } | null {
  const hay = `${label} ${display}`;
  for (const [pattern, low, high] of CLINICAL_RANGES) {
    if (pattern.test(hay) || pattern.test(label)) return { low, high };
  }
  return null;
}

function formatRange(low: number | null, high: number | null): string {
  if (low != null && high != null) return `${low}–${high}`;
  if (low != null) return `≥${low}`;
  if (high != null) return `≤${high}`;
  return '';
}

function labFlag(interp: string, value: string, low: number | null, high: number | null): LabFlag {
  const code = interp.toUpperCase();
  if (code === 'H' || code === 'HH') return 'high';
  if (code === 'L' || code === 'LL') return 'low';
  const n = asNumber(value);
  if (n != null && high != null && n > high) return 'high';
  if (n != null && low != null && n < low) return 'low';
  if (code === 'N' || code === 'NML') return 'normal';
  if (n != null && (low != null || high != null)) return 'normal';
  return 'unknown';
}

function isClinicalObservation(row: Record<string, unknown>): boolean {
  const category = text(row.category).toLowerCase();
  if (category === 'survey' || category === 'social-history' || category === 'sdoh') return false;
  if (category && category !== 'laboratory' && category !== 'vital-signs') return false;
  return !SURVEY_OR_SDOH.test(text(row.display));
}

function conditionLabel(row: Record<string, unknown>): string | null {
  if (row.redacted) return 'Redacted condition';
  const display = text(row.display);
  if (!display || !CLINICAL_CONDITION.test(display)) return null;
  const status = text(row.clinical_status).toLowerCase();
  const resolved = ['resolved', 'inactive', 'remission'].includes(status);
  const name = display.replace(/\s*\((?:disorder|finding|situation)\)\s*$/i, '');
  return resolved ? `${name} (resolved)` : name;
}

function pairBloodPressure(labs: LabResult[]): LabResult[] {
  const systolic = labs.filter(lab => lab.label === 'Systolic BP');
  const diastolic = labs.filter(lab => lab.label === 'Diastolic BP');
  const rest = labs.filter(lab => lab.label !== 'Systolic BP' && lab.label !== 'Diastolic BP');
  const used = new Set<string>();
  const combined: LabResult[] = [];
  for (const sys of systolic) {
    const dia = diastolic.find(item => item.date === sys.date && !used.has(item.id));
    if (!dia) {
      combined.push(sys);
      continue;
    }
    used.add(dia.id);
    const flag: LabFlag = sys.flag === 'high' || dia.flag === 'high'
      ? 'high'
      : sys.flag === 'low' || dia.flag === 'low'
        ? 'low'
        : sys.flag === 'normal' && dia.flag === 'normal'
          ? 'normal'
          : 'unknown';
    combined.push({
      id: sys.id,
      label: 'Blood pressure',
      value: `${sys.value}/${dia.value}`,
      unit: prettyUnit(sys.unit || dia.unit || 'mmHg'),
      referenceRange: [sys.referenceRange && `sys ${sys.referenceRange}`, dia.referenceRange && `dia ${dia.referenceRange}`]
        .filter(Boolean)
        .join(' · '),
      trend: sys.trend,
      flag,
      abnormal: flag === 'high' || flag === 'low',
      date: sys.date,
      sourceId: sys.sourceId
    });
  }
  return [...rest, ...combined, ...diastolic.filter(item => !used.has(item.id))];
}

function labsFrom(query: QueryResponse | null): LabResult[] {
  const mapped = (query?.rows ?? []).flatMap(row => {
    if (!row.redacted && !isClinicalObservation(row)) return [];
    const redacted = Boolean(row.redacted);
    const rawLabel = text(row.display) || text(row.code);
    const label = redacted ? 'Redacted' : prettyLabLabel(rawLabel, text(row.code));
    const value = redacted ? '—' : text(row.value_num ?? row.value_text ?? row.value_display);
    if (!label || (!redacted && !value)) return [];
    const storedLow = asNumber(row.ref_low);
    const storedHigh = asNumber(row.ref_high);
    const fallback = redacted ? null : clinicalRange(label, rawLabel);
    const low = storedLow ?? fallback?.low ?? null;
    const high = storedHigh ?? fallback?.high ?? null;
    const flag = redacted ? 'unknown' : labFlag(text(row.interpretation), value, low, high);
    return [{
      id: text(row.cite_id) || crypto.randomUUID(),
      label,
      value,
      unit: redacted ? '' : prettyUnit(text(row.unit)),
      referenceRange: redacted ? '' : [row.ref_low, row.ref_high].filter(v => v != null).join('–') || text(row.ref_text) || formatRange(low, high),
      trend: 'stable' as const,
      flag,
      abnormal: flag === 'high' || flag === 'low',
      date: text(row.effective_at).slice(0, 10),
      sourceId: text(row.cite_id)
    }];
  });
  return pairBloodPressure(mapped).sort((a, b) => b.date.localeCompare(a.date) || a.label.localeCompare(b.label));
}

export function groupLabs(labs: LabResult[]): Array<{ label: string; latest: LabResult; prior: LabResult[] }> {
  const groups = new Map<string, LabResult[]>();
  for (const lab of labs) {
    const list = groups.get(lab.label) ?? [];
    list.push(lab);
    groups.set(lab.label, list);
  }
  return [...groups.entries()].map(([label, rows]) => {
    const ordered = [...rows].sort((a, b) => b.date.localeCompare(a.date));
    return { label, latest: ordered[0], prior: ordered.slice(1) };
  }).sort((a, b) => Number(b.latest.abnormal) - Number(a.latest.abnormal) || a.label.localeCompare(b.label));
}

export function snapshotLabGroups(labs: LabResult[]): Array<{ label: string; latest: LabResult; prior: LabResult[] }> {
  return groupLabs(labs).filter(group => SNAPSHOT_LAB_LABELS.has(group.label) || group.latest.abnormal);
}

export function preferredChartLab(labs: LabResult[]): LabResult | undefined {
  const groups = groupLabs(labs);
  for (const label of BRIEF_LAB_ORDER) {
    const group = groups.find(item => item.label === label);
    if (group) return group.latest;
  }
  return groups[0]?.latest;
}

export function briefStatements(patient: Patient): string[] {
  const statements = [`Chart for ${patient.fullName}.`];
  const active = patient.majorDiagnoses.filter(item => !item.includes('(resolved)'));
  const resolved = patient.majorDiagnoses.filter(item => item.includes('(resolved)'));
  if (active.length) statements.push(`Active conditions: ${active.join(', ')}.`);
  if (resolved.length) statements.push(`Resolved history: ${resolved.join(', ')}.`);
  if (patient.placement) statements.push(`Current location: ${patient.placement}.`);
  const lab = preferredChartLab(patient.labs);
  if (lab) statements.push(`Latest ${lab.label}: ${lab.value} ${lab.unit}`.trim() + '.');
  if (patient.majorAllergies.length) statements.push(`Allergies: ${patient.majorAllergies.join(', ')}.`);
  if (patient.riskIndicators.length) statements.push(`Risks: ${patient.riskIndicators.join('; ')}.`);
  if (patient.notes[0]) statements.push(`Latest note: ${patient.notes[0].title}.`);
  return statements;
}

export function mergeQueryResponses(...parts: Array<QueryResponse | null>): QueryResponse | null {
  const present = parts.filter((part): part is QueryResponse => part != null);
  if (!present.length) return null;
  const rows = present.flatMap(part => part.rows);
  return {
    ...present[0],
    rows,
    row_count: rows.length,
    redacted_count: present.reduce((sum, part) => sum + part.redacted_count, 0)
  };
}

export function formatLabDate(iso: string): string {
  if (!iso) return '';
  const date = new Date(iso.includes('T') ? iso : `${iso}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return iso.slice(0, 10);
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(date);
}

export function identityLine(patient: { age: number; dateOfBirth: string; sex: string; patientId?: string }): string {
  const dob = patient.dateOfBirth ? `born ${formatLabDate(patient.dateOfBirth)}` : null;
  return [patient.age ? `${patient.age} years` : null, dob, patient.sex].filter(Boolean).join(' · ');
}

export function labFlagLabel(flag: LabFlag): string {
  if (flag === 'high') return 'High';
  if (flag === 'low') return 'Low';
  if (flag === 'normal') return 'In range';
  return 'Recorded';
}

function medsFrom(query: QueryResponse | null): Medication[] {
  return (query?.rows ?? []).map(row => {
    const redacted = Boolean(row.redacted);
    return {
      id: text(row.cite_id) || crypto.randomUUID(),
      name: redacted ? 'Redacted' : text(row.display) || text(row.code),
      dosage: redacted ? '—' : [row.dose_value, row.dose_unit, row.dosage_text].filter(Boolean).map(text).join(' '),
      frequency: redacted ? '' : text(row.timing_frequency),
      route: '',
      startDate: text(row.authored_at).slice(0, 10),
      stopDate: text(row.status) === 'stopped' ? text(row.authored_at).slice(0, 10) : undefined,
      prescriber: '',
      reason: text(row.reason_condition),
      current: text(row.status) === 'active'
    };
  });
}

const SDOH_ITEM = /employment|labor force|medication review|social isolation|stress \(finding\)|limited social|reports of violence|housing status|unemployed|received higher education|high school|socioeconomic/i;
const SOCIAL_NOTE = /the following procedures were conducted|the following lab reports were completed|socioeconomic background|identifies as heterosexual|has never smoked|the patient was prescribed the following medications/i;
const SOCIAL_SENTENCE = /never smoked|identifies as|socioeconomic|college courses|high school education|comes from a |patient is single|no complaints|\binsurance\b|humana|medicaid|medicare/i;

function withoutSocialSentences(value: string): string {
  return value
    .split(/\n+/)
    .map(paragraph =>
      paragraph
        .split(/(?<=[.!?])\s+/)
        .filter(sentence => sentence.trim() && !SOCIAL_SENTENCE.test(sentence))
        .join(' ')
    )
    .filter(paragraph => paragraph.trim())
    .join('\n')
    .trim();
}
const NOTE_ALIASES: Array<[RegExp, string]> = [
  [/plain x-ray of chest/i, 'chest x-ray'],
  [/oxygen administration by mask/i, 'oxygen by mask'],
  [/placing subject in prone position/i, 'prone positioning'],
  [/^cbc panel\b/i, 'CBC'],
  [/auto differential panel/i, 'CBC differential'],
  [/comprehensive metabolic 2000 panel/i, 'CMP'],
  [/^iron panel\b/i, 'iron panel'],
  [/troponin i\.cardiac/i, 'high-sensitivity troponin I'],
  [/^pt panel\b/i, 'PT'],
  [/0\.4 ml enoxaparin sodium 100 mg\/ml prefilled syringe/i, 'enoxaparin 40 mg'],
  [/acetaminophen 500 mg oral tablet/i, 'acetaminophen 500 mg'],
  [/suspected disease caused by severe acute respiratory coronavirus 2/i, 'suspected COVID-19'],
  [/disease caused by severe acute respiratory syndrome coronavirus 2/i, 'COVID-19'],
  [/severe anxiety \(panic\)/i, 'panic disorder'],
  [/disorder of teeth and\/or supporting structures/i, 'dental disease']
];

function noteSlice(source: string, start: RegExp, stops: RegExp[]): string {
  const match = start.exec(source);
  if (!match) return '';
  const rest = source.slice(match.index + match[0].length);
  const ends = stops.map(stop => rest.search(stop)).filter(index => index >= 0);
  return ends.length ? rest.slice(0, Math.min(...ends)) : rest;
}

function prettyNoteItem(raw: string): string {
  let item = raw.split(/\s+patient is presenting\b/i)[0];
  item = item.replace(/\s*\((?:disorder|finding|situation|procedure)\)\s*$/i, '').replace(/^[\s.-]+|[\s.]+$/g, '');
  item = item.replace(/\s*-\s*(blood by automated count|serum or plasma.*|platelet poor plasma.*)$/i, '');
  for (const [pattern, label] of NOTE_ALIASES) {
    if (pattern.test(item)) return label;
  }
  return item.replace(/\s+/g, ' ').trim();
}

const SPECIMEN_ONLY = /^(blood|blood by automated count|serum or plasma.*|platelet poor plasma.*)$/i;
const NOTE_LEFTOVER = /^(the patient was|the patient)$/i;
const HISTORY_NOISE = /^(cbc|cbc differential|cmp|iron panel|pt|high-sensitivity troponin i|chest x-ray|oxygen by mask|prone positioning)$/i;

function uniqueNoteItems(blob: string, dropHistoryNoise = false): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const part of blob.split(/\s+-\s+|,\s+/)) {
    const item = prettyNoteItem(part);
    if (!item || SDOH_ITEM.test(item) || SPECIMEN_ONLY.test(item) || NOTE_LEFTOVER.test(item)) continue;
    if (dropHistoryNoise && HISTORY_NOISE.test(item)) continue;
    const key = item.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

export function cleanSyntheaNote(value: string): string {
  const stripped = value.replace(/<\/?[A-Z]+>/g, ' ').replace(/^#+\s+/gm, '');
  const text = stripped.replace(/\s+/g, ' ').trim();
  if (!text || !SOCIAL_NOTE.test(text)) return withoutSocialSentences(value.trim());
  const lines: string[] = [];
  const who = /(\d+)\s*year-old\b.*?\b(male|female|other)\b/i.exec(text);
  if (who) lines.push(`${who[1]}-year-old ${who[2].toLowerCase()}.`);
  const presenting = uniqueNoteItems(noteSlice(text, /presenting with/i, [/the following/i, /no known allerg/i, /has never smoked/i, /identifies as/i, /social history/i, /patient is single/i]));
  const history = uniqueNoteItems(noteSlice(text, /has a history of/i, [/presenting with/i, /the following/i, /social history/i, /lab reports were completed/i, /procedures were conducted/i]), true);
  const procedures = uniqueNoteItems(noteSlice(text, /procedures were conducted:/i, [/lab reports were completed/i, /prescribed the following/i, /no known allerg/i]));
  const labs = uniqueNoteItems(noteSlice(text, /lab reports were completed:/i, [/the patient was/i, /prescribed the following/i, /no known allerg/i]));
  const meds = uniqueNoteItems(noteSlice(text, /prescribed the following medications:/i, [/no known allerg/i, /allergies/i, /patient is presenting/i, /procedures were conducted/i, /lab reports were completed/i]));
  if (presenting.length) lines.push(`Presenting: ${presenting.join(', ')}.`);
  if (history.length) lines.push(`History: ${history.join(', ')}.`);
  if (procedures.length) lines.push(`Procedures: ${procedures.join(', ')}.`);
  if (labs.length) lines.push(`Labs: ${labs.join(', ')}.`);
  if (meds.length) lines.push(`Medications: ${meds.join(', ')}.`);
  if (/no known allerg/i.test(text)) lines.push('Allergies: none known.');
  return lines.join('\n') || withoutSocialSentences(text);
}

function noteTitle(row: Record<string, unknown>): string {
  const typed = text(row.type_display);
  if (typed) return typed;
  const path = text(row.sanitized_ref || row.note_id);
  const name = path.split('/').pop() || '';
  const file = name.endsWith('.txt') ? name.slice(0, -4) : name;
  if (file && (file.includes('.') || path.startsWith('notes/'))) return file;
  const noteId = text(row.note_id);
  const key = text(row.patient_key);
  const alias = key && noteId.startsWith(`${key}-`) ? noteId.slice(key.length + 1) : '';
  return alias ? alias.replace(/-/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase()) : 'Clinical note';
}

function rowKeys(row: Record<string, unknown>): string[] {
  return [text(row.cite_id), text(row.note_id), text(row.sanitized_ref)].filter(Boolean);
}

function documentObjectKey(row: Record<string, unknown>): string | undefined {
  const ref = text(row.sanitized_ref);
  if (ref.startsWith('notes/')) return ref;
  const noteId = text(row.note_id);
  return noteId.startsWith('notes/') ? noteId : undefined;
}

function chartUploadKey(row: Record<string, unknown>): string | undefined {
  const noteId = text(row.note_id);
  if (noteId.startsWith('notes/')) return noteId;
  const ref = text(row.sanitized_ref);
  if (text(row.source) === 'upload' && ref.startsWith('notes/')) return ref;
  return undefined;
}

function authorLabel(row: Record<string, unknown>): string {
  if (text(row.uploader_role) === 'patient') return 'Patient reported';
  if (chartUploadKey(row)) return 'Clinical';
  if (text(row.provenance) === 'patient-reported') return 'Patient reported';
  return text(row.provenance) === 'clinical' || !text(row.provenance) ? 'Clinical' : text(row.provenance);
}

function noteCard(row: Record<string, unknown>): ClinicalNote | null {
  const id = text(row.cite_id || row.note_id);
  if (!id) return null;
  const storageKey = chartUploadKey(row);
  return {
    id,
    title: noteTitle(row),
    author: authorLabel(row),
    date: text(row.authored_at).slice(0, 10),
    text: row.redacted ? 'Redacted' : cleanSyntheaNote(text(row.text)),
    ...(storageKey ? { storageKey } : {})
  };
}

function reportedChunkNotes(payload: NotesResponse, known: Set<string>): ClinicalNote[] {
  const grouped = new Map<string, ClinicalNote>();
  for (const row of payload.chunks ?? []) {
    if (text(row.provenance) !== 'patient-reported' && !chartUploadKey(row)) continue;
    const keys = rowKeys(row);
    if (keys.some(key => known.has(key))) continue;
    const id = text(row.note_id || row.cite_id);
    if (!id) continue;
    const piece = text(row.text);
    const current = grouped.get(id);
    if (!current) {
      const card = noteCard(row);
      if (card) grouped.set(id, { ...card, id, text: piece });
      continue;
    }
    if (piece && !current.text.includes(piece)) current.text = current.text ? `${current.text}\n\n${piece}` : piece;
  }
  return [...grouped.values()].map(note => ({ ...note, text: cleanSyntheaNote(note.text) }));
}

function notesFrom(payload: NotesResponse | null): ClinicalNote[] {
  const listed = (payload?.notes ?? []).map(noteCard).filter((note): note is ClinicalNote => note !== null);
  const known = new Set((payload?.notes ?? []).flatMap(rowKeys));
  const uploaded = payload ? reportedChunkNotes(payload, known) : [];
  if (listed.length || uploaded.length) return [...uploaded, ...listed];
  const grouped = new Map<string, ClinicalNote>();
  for (const row of payload?.chunks ?? []) {
    const id = text(row.note_id || row.cite_id);
    if (!id || row.redacted) continue;
    const piece = text(row.text);
    const current = grouped.get(id);
    if (!current) {
      grouped.set(id, {
        id,
        title: noteTitle(row),
        author: authorLabel(row),
        date: text(row.authored_at).slice(0, 10),
        text: piece
      });
      continue;
    }
    if (piece && !current.text.includes(piece)) current.text = current.text ? `${current.text}\n\n${piece}` : piece;
  }
  return [...grouped.values()].map(note => ({ ...note, text: cleanSyntheaNote(note.text) }));
}

const DIET_LABELS: Record<string, string> = {
  '160670007': 'diabetic diet',
  '386619000': 'low sodium diet'
};

export function dietLabel(code: unknown): string {
  const key = text(code);
  if (!key) return '';
  if (DIET_LABELS[key]) return DIET_LABELS[key];
  // Numeric clinical codes stay off the tray card; human slugs stay readable.
  if (/^\d{5,}$/.test(key)) return 'Diet order';
  return key.replace(/[_-]+/g, ' ').trim();
}

export function formatDietOrder(row: Record<string, unknown>): string {
  const ward = text(row.ward);
  const codes = Array.isArray(row.diet_codes)
    ? row.diet_codes.map(dietLabel).filter(Boolean)
    : dietLabel(row.diet_codes) ? [dietLabel(row.diet_codes)] : [];
  return [ward ? `Ward ${ward}` : '', ...codes].filter(Boolean).join(' · ');
}

const ENCOUNTER_CLASS: Record<string, string> = {
  AMB: 'Ambulatory',
  IMP: 'Inpatient',
  EMER: 'Emergency',
  VR: 'Virtual',
  HH: 'Home'
};

function encounterType(row: Record<string, unknown>): string {
  return text(row.type_display).replace(/\s*\((?:procedure|disorder|finding)\)\s*$/i, '');
}

function placementFrom(diet: QueryResponse | null, encounters: QueryResponse | null): string {
  const dietRow = diet?.rows?.find(item => !item.redacted && item.ward);
  if (dietRow) return formatDietOrder(dietRow);
  const rows = (encounters?.rows ?? []).filter(item => !item.redacted);
  const current = rows.find(item => ['in-progress', 'arrived', 'triaged', 'onleave'].includes(text(item.status).toLowerCase()));
  const row = current ?? rows[0];
  if (!row) return '';
  const cls = ENCOUNTER_CLASS[text(row.class)] || text(row.class);
  const type = encounterType(row);
  const dept = text(row.dept);
  const when = formatLabDate(text(row.started_at));
  if (current) return [cls, dept && `Ward ${dept}`, type].filter(Boolean).join(' · ');
  return ['Last visit', cls, type, when].filter(Boolean).join(' · ');
}

function latestAbnormalRisks(labs: LabResult[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const lab of labs) {
    if (!lab.abnormal || seen.has(lab.label)) continue;
    seen.add(lab.label);
    out.push(`${lab.label} ${lab.value} ${lab.unit}`.trim());
  }
  return out;
}

function storedObjectKey(ref: unknown): string | undefined {
  const key = text(ref);
  return key.startsWith('notes/') ? key : undefined;
}

function pdfObjectKey(ref: unknown): string | undefined {
  const key = text(ref);
  return key.endsWith('.pdf') ? key : undefined;
}

export function sessionCanOpenSignedFiles(
  me: { role: string; panels: readonly string[] } | null
): boolean {
  if (!me) return false;
  return me.role === 'patient' || me.panels.includes('imaging');
}

function documentsFrom(
  payload: NotesResponse | null,
  imaging: ImagingResponse | null,
  canOpenSignedFiles = true
): MedicalDocument[] {
  const reported = canOpenSignedFiles
    ? [...(payload?.notes ?? []), ...(payload?.chunks ?? [])].filter(
      row => text(row.provenance) === 'patient-reported' || Boolean(chartUploadKey(row))
    )
    : [];
  const seen = new Set<string>();
  const uploads = reported.flatMap(row => {
    const keys = rowKeys(row);
    if (!keys.length || keys.some(key => seen.has(key))) return [];
    keys.forEach(key => seen.add(key));
    return [{
      id: text(row.cite_id || row.note_id),
      title: noteTitle(row),
      type: authorLabel(row),
      date: text(row.authored_at).slice(0, 10),
      source: 'upload',
      processingState: row.published === false ? 'pending-review' as const : 'processed' as const,
      uploadedBy: 'patient',
      summary: noteSummary(text(row.text)) || undefined,
      objectKey: documentObjectKey(row)
    }];
  });
  const pdfNotes = canOpenSignedFiles
    ? (payload?.notes ?? [])
    .filter(row => text(row.provenance) !== 'patient-reported')
    .flatMap(row => {
      const objectKey = pdfObjectKey(row.sanitized_ref);
      if (!objectKey) return [];
      return [{
        id: text(row.cite_id || row.note_id),
        title: text(row.type_display) || 'Clinical note',
        type: 'clinical',
        date: text(row.authored_at).slice(0, 10),
        source: 'clinical',
        processingState: 'processed' as const,
        uploadedBy: 'clinical',
        objectKey
      }];
    })
    : [];
  const reports = (imaging?.reports ?? []).map(row => ({
    id: text(row.cite_id),
    title: text(row.display) || 'Imaging report',
    type: text(row.category) === 'RAD' ? 'Radiology' : text(row.category) || 'Imaging',
    date: text(row.issued_at || row.effective_at).slice(0, 10),
    source: 'Imaging',
    processingState: 'processed' as const,
    uploadedBy: 'clinical',
    summary: text(row.conclusion_text) || undefined,
    studyId: canOpenSignedFiles ? text(row.orthanc_id) || undefined : undefined,
    objectKey: canOpenSignedFiles ? storedObjectKey(row.report_ref) : undefined
  }));
  return [...uploads, ...pdfNotes, ...reports];
}

export function composePatient(
  patientKey: string,
  identity: IdentityBanner | null,
  queries: Record<string, QueryResponse | null>,
  extras: {
    notes?: NotesResponse | null;
    imaging?: ImagingResponse | null;
    canOpenSignedFiles?: boolean;
  } = {}
): Patient {
  const given = cleanSyntheaName(identity?.given_name ?? '');
  const family = cleanSyntheaName(identity?.family_name ?? '');
  const fullName = `${given} ${family}`.trim() || 'Patient';
  const labs = labsFrom(queries.labs);
  const medications = medsFrom(queries.meds);
  const diagnoses = (() => {
    const seen = new Set<string>();
    const active: string[] = [];
    const resolved: string[] = [];
    for (const row of queries.conditions?.rows ?? []) {
      const label = conditionLabel(row);
      if (!label) continue;
      const key = label.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      if (label.endsWith('(resolved)')) resolved.push(label);
      else active.push(label);
    }
    return [...active, ...resolved];
  })();
  const allergies = (queries.allergies?.rows ?? [])
    .map(row => (row.redacted ? 'Redacted allergy' : text(row.display)))
    .filter(Boolean);
  return {
    id: patientKey,
    fullName,
    age: identity ? ageFromIso(identity.birth_date) : 0,
    dateOfBirth: identity?.birth_date ?? '',
    phone: '',
    email: '',
    status: identity ? 'Visible' : 'Record without identity banner',
    warning: identity?.compliance_flag ? 'Break-glass active' : undefined,
    avatarInitials: initials(given, family, 'PT'),
    assignedClinician: '',
    sex: identity?.sex ?? '',
    patientId: identity?.mrn && !looksLikeInternalId(identity.mrn) ? identity.mrn : '',
    bloodType: '',
    majorAllergies: allergies,
    majorDiagnoses: diagnoses,
    placement: placementFrom(queries.diet, queries.encounters),
    riskIndicators: [
      ...latestAbnormalRisks(labs),
      ...(queries.labs?.redacted_count ? [`${queries.labs.redacted_count} lab row(s) redacted`] : []),
      ...(queries.conditions?.redacted_count ? [`${queries.conditions.redacted_count} condition row(s) redacted`] : [])
    ],
    measurements: [],
    labs,
    medications,
    documents: documentsFrom(
      extras.notes ?? null,
      extras.imaging ?? null,
      extras.canOpenSignedFiles !== false
    ),
    notes: notesFrom(extras.notes ?? null)
  };
}

function noteSummary(text: string): string {
  const compact = text.replace(/\s+/g, ' ').trim();
  if (compact.length <= 180) return compact;
  return `${compact.slice(0, 177).trimEnd()}...`;
}

export function composeTimeline(patient: Patient): TimelineEvent[] {
  const labs: TimelineEvent[] = patient.labs.map(lab => ({
    id: lab.id,
    kind: 'lab',
    date: lab.date,
    title: lab.label,
    summary: `${lab.value} ${lab.unit}`.trim(),
    tags: ['Laboratory'],
    provenance: 'clinical',
    linkedRecordId: lab.sourceId
  }));
  const meds: TimelineEvent[] = patient.medications.map(med => ({
    id: med.id,
    kind: 'medication',
    date: med.startDate,
    title: med.name,
    summary: [med.dosage, med.frequency].filter(Boolean).join(' · '),
    tags: ['Medication'],
    provenance: 'clinical'
  }));
  const notes: TimelineEvent[] = patient.notes.map(note => ({
    id: note.id,
    kind: 'note',
    date: note.date,
    title: note.title,
    summary: noteSummary(note.text),
    tags: ['Note'],
    provenance: note.author === 'patient-reported' || note.author === 'ai-generated' ? note.author : 'clinical'
  }));
  const documents: TimelineEvent[] = patient.documents.map(document => ({
    id: document.id,
    kind: 'document',
    date: document.date,
    title: document.title,
    summary: document.summary || document.type,
    tags: ['Document'],
    provenance: document.type === 'patient-reported' ? 'patient-reported' : 'clinical'
  }));
  return [...labs, ...meds, ...notes, ...documents].sort((a, b) => b.date.localeCompare(a.date));
}

export function filterTimeline(events: TimelineEvent[], options: { kind: string; query: string }): TimelineEvent[] {
  const kind = options.kind;
  const query = options.query.trim().toLowerCase();
  return events.filter(event => {
    if (kind !== 'all' && event.kind !== kind) return false;
    if (!query) return true;
    const haystack = [event.title, event.summary, event.date, ...event.tags].join(' ').toLowerCase();
    return haystack.includes(query);
  });
}

export function summariesFromKeys(keys: readonly string[], banners: Array<IdentityBanner | null>): PatientSummary[] {
  return keys.flatMap((key, index) => {
    const identity = banners[index];
    if (!identity) return [];
    const given = cleanSyntheaName(identity.given_name);
    const family = cleanSyntheaName(identity.family_name);
    const fullName = `${given} ${family}`.trim() || 'Patient';
    return [{
      id: key,
      fullName,
      age: ageFromIso(identity.birth_date),
      dateOfBirth: identity.birth_date,
      phone: '',
      email: '',
      status: 'Visible',
      avatarInitials: initials(given, family, 'PT'),
      assignedClinician: '',
      warning: identity.compliance_flag ? 'Break-glass active' : undefined
    }];
  });
}

export function kitchenCardFromDiet(patientKey: string, diet: QueryResponse): PatientSummary {
  const row = diet.rows[0] ?? {};
  const codes = Array.isArray(row.diet_codes)
    ? row.diet_codes.map(dietLabel).filter(Boolean).join(', ')
    : dietLabel(row.diet_codes);
  const ward = text(row.ward);
  const title = ward ? `Ward ${ward}` : 'Tray';
  return {
    id: patientKey,
    fullName: title,
    age: 0,
    dateOfBirth: '',
    phone: '',
    email: '',
    status: 'Visible',
    avatarInitials: ward ? ward.replace(/\W/g, '').slice(-2).toUpperCase() || 'WD' : 'TR',
    assignedClinician: '',
    reason: codes || 'Diet order on this ward',
    reasonForVisit: codes || undefined
  };
}
