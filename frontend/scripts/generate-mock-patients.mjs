#!/usr/bin/env node
/**
 * Regenerates frontend/src/data/mockPatient360.ts from the single JSON
 * source of truth at .scratch/patient-scenarios/patients.json.
 *
 * Patient edits happen ONLY in that JSON file from now on — the `patients`
 * array in mockPatient360.ts is generated output, not hand-maintained.
 * `timelineEvents`, `attentionItems`, and `homeDashboard`'s narrative copy
 * (greeting/briefing) stay as a static template in THIS script: they're
 * hand-written editorial content about Emma Laurent's specific story, not
 * structured per-patient data, so there's nothing in patients.json to
 * derive them from. `homeDashboard.todaysPatients` still points at the
 * freshly generated `patients` array either way.
 *
 * Usage: node scripts/generate-mock-patients.mjs   (from frontend/)
 *    or: npm run generate:mock
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(FRONTEND_ROOT, '..');
const SOURCE_JSON = path.join(REPO_ROOT, '.scratch', 'patient-scenarios', 'patients.json');
const OUTPUT_TS = path.join(FRONTEND_ROOT, 'src', 'data', 'mockPatient360.ts');

// --- Minimal, deterministic JS-value -> TypeScript-literal serializer ------
// Strings use double quotes (JSON.stringify's native form) rather than the
// single quotes the original hand-written file used — simpler and safer
// given apostrophes already appear in real content (e.g. "Huntington's
// disease"), and this is generated output now, not hand-styled code.
function serialize(value, indent) {
  const pad = '  '.repeat(indent);
  const padIn = '  '.repeat(indent + 1);

  if (value === null || value === undefined) return 'undefined';
  if (typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);

  if (Array.isArray(value)) {
    if (value.length === 0) return '[]';
    // Arrays of plain strings (majorAllergies, majorDiagnoses, riskIndicators)
    // stay on one line; arrays of objects (measurements, labs, medications,
    // documents, notes) get one entry per line for readability.
    if (value.every(v => typeof v === 'string')) {
      return `[${value.map(v => JSON.stringify(v)).join(', ')}]`;
    }
    const items = value.map(v => `${padIn}${serialize(v, indent + 1)}`).join(',\n');
    return `[\n${items}\n${pad}]`;
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value).filter(([, v]) => v !== undefined);
    if (entries.length === 0) return '{}';
    const body = entries.map(([k, v]) => `${padIn}${k}: ${serialize(v, indent + 1)}`).join(',\n');
    return `{\n${body}\n${pad}}`;
  }

  throw new Error(`generate-mock-patients: don't know how to serialize ${JSON.stringify(value)}`);
}

function serializePatient(patient) {
  return '  ' + serialize(patient, 1);
}

// --- Static narrative content — hand-authored, not derived from patients.json ---
const STATIC_TAIL = `
export const timelineEvents: TimelineEvent[] = [
  { id: 'event-consult-sept-12', kind: 'visit', date: '2026-09-12', title: 'Consultation', summary: 'Migraine frequency increased to approximately three episodes per month. No neurological red flags documented.', tags: ['Dr. Müller', 'Consultation'], provenance: 'clinical', linkedRecordId: 'note-consult-sept' },
  { id: 'event-patient-update-sept-02', kind: 'patient-update', date: '2026-09-02', title: 'Patient update', summary: 'Reported headaches on four of the previous seven days and starting magnesium 300 mg daily.', tags: ['Patient reported'], provenance: 'patient-reported' },
  { id: 'event-lab-aug-18', kind: 'lab', date: '2026-08-18', title: 'Laboratory result', summary: 'LDL cholesterol measured at 4.2 mmol/L, up from 3.7 mmol/L.', tags: ['Laboratory', 'Abnormal LDL'], provenance: 'clinical', linkedRecordId: 'lab-ldl-sept' },
  { id: 'event-doc-july-21', kind: 'document', date: '2026-07-21', title: 'External neurology letter', summary: 'Previous neurologist documented migraine without aura and recommended continued symptom diary.', tags: ['Document', 'AI processed'], provenance: 'ai-generated' }
];

export const attentionItems: AttentionItem[] = [
  { id: 'att-ldl', patientId: 'emma-laurent', severity: 'warning', title: 'New abnormal lab result', detail: 'LDL cholesterol increased 12% since the previous result.', provenance: 'clinical' },
  { id: 'att-migraine', patientId: 'emma-laurent', severity: 'review', title: 'Worsening symptoms reported', detail: 'Emma reported headaches on four of the previous seven days.', provenance: 'patient-reported' },
  { id: 'att-doc', patientId: 'emma-laurent', severity: 'review', title: 'Uploaded report waiting for review', detail: 'Neurology report has extracted information pending clinician approval.', provenance: 'ai-generated' }
];

export const homeDashboard: HomeDashboard = {
  greeting: 'Good morning, Dr. Müller',
  todaysPatients: patients,
  briefing: [
    { id: 'brief-1', text: 'You have 8 patients today.' },
    { id: 'brief-2', text: '2 have new lab results.', patientId: 'emma-laurent' },
    { id: 'brief-3', text: '1 patient reported worsening symptoms overnight.', patientId: 'emma-laurent' },
    { id: 'brief-4', text: '3 follow-ups are overdue.' }
  ],
  attention: attentionItems,
  recentActivity: timelineEvents
};
`;

function main() {
  const raw = readFileSync(SOURCE_JSON, 'utf8');
  const { patients } = JSON.parse(raw);
  if (!Array.isArray(patients) || patients.length === 0) {
    throw new Error(`generate-mock-patients: no patients found in ${SOURCE_JSON}`);
  }

  const patientsBlock = patients.map(serializePatient).join(',\n');

  const header = `/**
 * GENERATED FILE — do not edit by hand.
 *
 * Source of truth: .scratch/patient-scenarios/patients.json
 * Generator:       frontend/scripts/generate-mock-patients.mjs
 * Regenerate with: npm run generate:mock
 *
 * Edit patient data in patients.json, then re-run the generator. Changes
 * made directly to the \`patients\` array below will be overwritten.
 */
import type { AttentionItem, HomeDashboard, Patient, TimelineEvent } from '../types/patient360';

export const patients: Patient[] = [
${patientsBlock}
];
`;

  const output = header + STATIC_TAIL;
  writeFileSync(OUTPUT_TS, output, 'utf8');
  console.log(`Generated ${OUTPUT_TS} from ${patients.length} patients in ${SOURCE_JSON}`);
}

main();
