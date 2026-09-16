# Patient360 Vue Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a polished Vue.js frontend demo of Patient360 focused on the Patient 360 clinical workspace, clinic home dashboard, AI-assisted interactions, and convincing supporting screens using mock data only.

**Architecture:** Create a Vue 3 + Vite + TypeScript single-page app with Vue Router, Pinia, and focused feature modules. All backend-facing behavior goes through typed mock service functions in `src/services/mockApi.ts`, so later backend integration can replace those functions without changing page components.

**Tech Stack:** Vue 3, Vite, TypeScript, Vue Router, Pinia, Vitest, Testing Library, Playwright, lucide-vue-next, Chart.js via vue-chartjs, CSS variables, local JSON-like fixtures.

**Spec:** `spec.md`

## Global Constraints

- No backend is required for this phase; all API behavior must use deterministic mock data and mock async service functions.
- The initial role is a generic **Clinical Staff** view.
- The app must make Patient 360 understandable within approximately five seconds of opening a patient profile.
- AI-generated content must always use the `✦` symbol and must not visually resemble raw clinical facts.
- Patient-reported information must be visibly marked as patient-reported.
- Color must never be the sole carrier of clinical information.
- Body text should be approximately 16-18 px minimum, with secondary text no smaller than approximately 14 px unless unavoidable.
- Clickable controls should have generous targets of approximately 44-48 px minimum height.
- Layouts should tolerate approximately 125-150% browser zoom without breaking.
- Demo priority order: Patient 360, Clinic Home, AI interactions, supporting screens.

---

## File Structure

Create a fresh Vue app in the repository root. Keep feature code grouped by domain and keep shared UI primitives small.

- `package.json`: npm scripts and dependencies for the Vue app.
- `vite.config.ts`: Vite config with Vue plugin and Vitest test environment.
- `tsconfig.json`, `tsconfig.node.json`: TypeScript config.
- `index.html`: App mount shell.
- `src/main.ts`: Create Vue app, install router and Pinia.
- `src/App.vue`: Persistent dashboard frame plus router outlet.
- `src/router/index.ts`: Route definitions for clinical and patient portal screens.
- `src/stores/useUiStore.ts`: AI panel state, selected patient id, highlighted citation id, navigation state.
- `src/types/patient360.ts`: Shared domain types for patients, labs, documents, notes, tasks, timeline events, AI answers, provenance, permissions.
- `src/data/mockPatient360.ts`: Deterministic demo dataset centered on Emma Laurent.
- `src/services/mockApi.ts`: Async mock service facade for patients, AI answers, uploads, extracted facts, tasks, search, and audit events.
- `src/styles/tokens.css`: Color, radius, spacing, typography, shadows, and focus variables.
- `src/styles/base.css`: Global reset, accessibility defaults, layout helpers, body styles.
- `src/components/layout/AppShell.vue`: Persistent navigation, patient tabs, header controls.
- `src/components/layout/AskPatient360Panel.vue`: Persistent AI side panel with citations and mock loading states.
- `src/components/ui/*.vue`: Reusable primitives: `ProvenanceBadge`, `ClinicalCard`, `MetricTile`, `StatusPill`, `LargeTabs`, `EmptyState`, `ConfirmDialog`, `SourceCitation`, `AvatarBadge`.
- `src/features/home/*.vue`: Clinic home sections.
- `src/features/patients/*.vue`: Patient search and result components.
- `src/features/patient360/*.vue`: Patient header, clinical brief, since-last-visit, snapshot, timeline, labs, medications, documents, notes.
- `src/features/clinic/*.vue`: Cohort insights, tasks, audit/privacy supporting views.
- `src/features/portal/*.vue`: Patient portal supporting view.
- `tests/unit/*.spec.ts`: Unit tests for mock service behavior, timeline filtering, AI citation highlighting, and permission filtering.
- `tests/e2e/patient360.spec.ts`: Demo-flow Playwright test.

---

### Task 1: Scaffold Vue App And Tooling

**Files:**
- Create: `package.json`
- Create: `vite.config.ts`
- Create: `tsconfig.json`
- Create: `tsconfig.node.json`
- Create: `index.html`
- Create: `src/main.ts`
- Create: `src/App.vue`
- Create: `src/router/index.ts`
- Create: `src/styles/tokens.css`
- Create: `src/styles/base.css`

**Interfaces:**
- Consumes: none.
- Produces: A runnable Vue 3 app with route names `home`, `patients`, `patient-overview`, `patient-timeline`, `patient-labs`, `patient-medications`, `patient-documents`, `patient-notes`, `tasks`, `cohort`, `audit`, and `portal`.

- [ ] **Step 1: Create `package.json`**

```json
{
  "name": "patient360-vue-frontend",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0",
    "build": "vue-tsc -b && vite build",
    "preview": "vite preview --host 0.0.0.0",
    "test:unit": "vitest run",
    "test:e2e": "playwright test",
    "test": "npm run test:unit && npm run build"
  },
  "dependencies": {
    "@vitejs/plugin-vue": "^5.2.0",
    "chart.js": "^4.4.7",
    "lucide-vue-next": "^0.468.0",
    "pinia": "^2.3.0",
    "vue": "^3.5.13",
    "vue-chartjs": "^5.3.2",
    "vue-router": "^4.5.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.49.1",
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/vue": "^8.1.0",
    "@types/node": "^22.10.2",
    "@vitejs/plugin-vue": "^5.2.0",
    "@vue/test-utils": "^2.4.6",
    "jsdom": "^25.0.1",
    "typescript": "^5.7.2",
    "vite": "^6.0.3",
    "vitest": "^2.1.8",
    "vue-tsc": "^2.1.10"
  }
}
```

- [ ] **Step 2: Create TypeScript and Vite config**

`vite.config.ts`

```ts
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts']
  }
});
```

`tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "jsx": "preserve",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src/**/*.ts", "src/**/*.vue", "tests/**/*.ts"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`tsconfig.node.json`

```json
{
  "compilerOptions": {
    "composite": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts", "playwright.config.ts"]
}
```

- [ ] **Step 3: Create the app entry files**

`index.html`

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Patient360</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

`src/main.ts`

```ts
import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import { router } from './router';
import './styles/tokens.css';
import './styles/base.css';

createApp(App).use(createPinia()).use(router).mount('#app');
```

`src/App.vue`

```vue
<template>
  <AppShell>
    <RouterView />
  </AppShell>
</template>

<script setup lang="ts">
import AppShell from './components/layout/AppShell.vue';
</script>
```

- [ ] **Step 4: Create routes**

`src/router/index.ts`

```ts
import { createRouter, createWebHistory } from 'vue-router';

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('../features/home/HomeView.vue') },
    { path: '/patients', name: 'patients', component: () => import('../features/patients/PatientsView.vue') },
    { path: '/patients/:patientId', redirect: to => `/patients/${to.params.patientId}/overview` },
    { path: '/patients/:patientId/overview', name: 'patient-overview', component: () => import('../features/patient360/PatientOverviewView.vue') },
    { path: '/patients/:patientId/timeline', name: 'patient-timeline', component: () => import('../features/patient360/TimelineView.vue') },
    { path: '/patients/:patientId/labs', name: 'patient-labs', component: () => import('../features/patient360/LabsView.vue') },
    { path: '/patients/:patientId/medications', name: 'patient-medications', component: () => import('../features/patient360/MedicationsView.vue') },
    { path: '/patients/:patientId/documents', name: 'patient-documents', component: () => import('../features/patient360/DocumentsView.vue') },
    { path: '/patients/:patientId/notes', name: 'patient-notes', component: () => import('../features/patient360/NotesView.vue') },
    { path: '/tasks', name: 'tasks', component: () => import('../features/clinic/TasksView.vue') },
    { path: '/cohort', name: 'cohort', component: () => import('../features/clinic/CohortInsightsView.vue') },
    { path: '/audit', name: 'audit', component: () => import('../features/clinic/AuditPrivacyView.vue') },
    { path: '/portal', name: 'portal', component: () => import('../features/portal/PatientPortalView.vue') }
  ],
  scrollBehavior: () => ({ top: 0 })
});
```

- [ ] **Step 5: Create design tokens**

`src/styles/tokens.css`

```css
:root {
  --color-bg: #fffdf4;
  --color-surface: #ffffff;
  --color-yellow: #ffefa8;
  --color-yellow-soft: #fff8cf;
  --color-pink: #f6b8c8;
  --color-pink-soft: #fde8ee;
  --color-plum: #28232a;
  --color-muted: #675f68;
  --color-line: #e8dcc7;
  --color-danger: #b42318;
  --color-warning: #a15c00;
  --color-success: #287347;
  --shadow-soft: 0 14px 38px rgb(52 35 13 / 10%);
  --radius-control: 12px;
  --radius-card: 20px;
  --radius-panel: 28px;
  --focus-ring: 0 0 0 4px rgb(246 184 200 / 55%);
  --font-body: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
```

`src/styles/base.css`

```css
* {
  box-sizing: border-box;
}

html {
  min-width: 320px;
  background: var(--color-bg);
  color: var(--color-plum);
  font-family: var(--font-body);
}

body {
  margin: 0;
  font-size: 17px;
  line-height: 1.45;
}

button,
input,
textarea,
select {
  font: inherit;
}

button,
a {
  min-height: 44px;
}

:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
```

- [ ] **Step 6: Run install and first build**

Run: `npm install`

Run: `npm run build`

Expected: build fails only because route component files have not been created yet.

- [ ] **Step 7: Commit**

```bash
git add package.json package-lock.json vite.config.ts tsconfig.json tsconfig.node.json index.html src
git commit -m "chore: scaffold vue patient360 app"
```

---

### Task 2: Domain Types, Mock Data, And Mock Services

**Files:**
- Create: `src/types/patient360.ts`
- Create: `src/data/mockPatient360.ts`
- Create: `src/services/mockApi.ts`
- Create: `tests/setup.ts`
- Create: `tests/unit/mockApi.spec.ts`

**Interfaces:**
- Consumes: route ids from Task 1.
- Produces: `mockApi` with methods `getHomeDashboard()`, `getPatients()`, `searchPatients(query, mode)`, `getPatient(patientId)`, `getTimeline(patientId)`, `askPatient360(request)`, `uploadDocument(patientId, fileName)`, and `applyExtractedFact(patientId, factId, decision)`.

- [ ] **Step 1: Write mock service tests**

`tests/setup.ts`

```ts
import '@testing-library/jest-dom/vitest';
```

`tests/unit/mockApi.spec.ts`

```ts
import { describe, expect, it } from 'vitest';
import { mockApi } from '../../src/services/mockApi';

describe('mockApi', () => {
  it('returns Emma Laurent as the demo anchor patient', async () => {
    const patient = await mockApi.getPatient('emma-laurent');
    expect(patient.fullName).toBe('Emma Laurent');
    expect(patient.majorAllergies).toContain('Penicillin');
  });

  it('labels natural-language search results as AI generated', async () => {
    const results = await mockApi.searchPatients('diabetes dizziness', 'ai');
    expect(results[0].resultMode).toBe('ai');
    expect(results[0].reason).toContain('AI matched');
  });

  it('returns cited AI answers for patient-specific questions', async () => {
    const answer = await mockApi.askPatient360({
      scope: 'patient',
      patientId: 'emma-laurent',
      question: "What changed with Emma's migraines over the last six months?"
    });
    expect(answer.citations.map(citation => citation.sourceId)).toEqual(
      expect.arrayContaining(['event-consult-sept-12', 'event-patient-update-sept-02'])
    );
  });

  it('returns extracted facts after a document upload', async () => {
    const result = await mockApi.uploadDocument('emma-laurent', 'neurology-report.pdf');
    expect(result.extractedFacts).toHaveLength(3);
    expect(result.extractedFacts[0].status).toBe('pending');
  });
});
```

- [ ] **Step 2: Create shared domain types**

`src/types/patient360.ts`

```ts
export type Provenance = 'clinical' | 'patient-reported' | 'ai-generated';
export type TimelineKind = 'visit' | 'lab' | 'medication' | 'patient-update' | 'document' | 'note';
export type ResultMode = 'standard' | 'ai';
export type TaskStatus = 'pending' | 'confirmed' | 'done';
export type ExtractedFactStatus = 'pending' | 'accepted' | 'edited' | 'rejected';

export interface PermissionGate {
  canView: boolean;
  canAct: boolean;
  redactedFields: string[];
}

export interface PatientSummary {
  id: string;
  fullName: string;
  age: number;
  dateOfBirth: string;
  phone: string;
  email: string;
  status: string;
  appointmentTime?: string;
  appointmentType?: string;
  reasonForVisit?: string;
  warning?: string;
  avatarInitials: string;
  assignedClinician: string;
  resultMode?: ResultMode;
  reason?: string;
}

export interface Patient extends PatientSummary {
  sex: string;
  patientId: string;
  bloodType: string;
  majorAllergies: string[];
  majorDiagnoses: string[];
  riskIndicators: string[];
  measurements: Measurement[];
  labs: LabResult[];
  medications: Medication[];
  documents: MedicalDocument[];
  notes: ClinicalNote[];
}

export interface Measurement {
  id: string;
  label: string;
  value: string;
  date: string;
  provenance: Provenance;
}

export interface LabResult {
  id: string;
  label: string;
  value: string;
  unit: string;
  referenceRange: string;
  previousValue?: string;
  trend: 'up' | 'down' | 'stable';
  abnormal: boolean;
  date: string;
  sourceId: string;
}

export interface Medication {
  id: string;
  name: string;
  dosage: string;
  frequency: string;
  route: string;
  startDate: string;
  stopDate?: string;
  prescriber: string;
  reason: string;
  current: boolean;
}

export interface MedicalDocument {
  id: string;
  title: string;
  type: string;
  date: string;
  source: string;
  processingState: 'processed' | 'pending-review' | 'extracting';
  uploadedBy: string;
  extractedFacts?: ExtractedFact[];
}

export interface ExtractedFact {
  id: string;
  label: string;
  value: string;
  sourceDocumentId: string;
  status: ExtractedFactStatus;
}

export interface ClinicalNote {
  id: string;
  title: string;
  author: string;
  date: string;
  text: string;
}

export interface TimelineEvent {
  id: string;
  kind: TimelineKind;
  date: string;
  title: string;
  summary: string;
  tags: string[];
  provenance: Provenance;
  linkedRecordId?: string;
}

export interface AiCitation {
  id: string;
  label: string;
  sourceId: string;
  sourceType: TimelineKind | 'lab' | 'document' | 'note';
}

export interface AiAnswer {
  id: string;
  answer: string;
  citations: AiCitation[];
  retrievalSteps: string[];
}

export interface AskPatient360Request {
  scope: 'patient' | 'clinic';
  patientId?: string;
  question: string;
}

export interface AttentionItem {
  id: string;
  patientId: string;
  severity: 'review' | 'warning' | 'urgent';
  title: string;
  detail: string;
  provenance: Provenance;
}

export interface HomeDashboard {
  greeting: string;
  todaysPatients: PatientSummary[];
  briefing: Array<{ id: string; text: string; patientId?: string }>;
  attention: AttentionItem[];
  recentActivity: TimelineEvent[];
}
```

- [ ] **Step 3: Create deterministic mock data**

`src/data/mockPatient360.ts`

```ts
import type { AttentionItem, HomeDashboard, Patient, TimelineEvent } from '../types/patient360';

export const patients: Patient[] = [
  {
    id: 'emma-laurent',
    fullName: 'Emma Laurent',
    age: 34,
    dateOfBirth: '1992-04-18',
    phone: '+41 79 555 0134',
    email: 'emma.laurent@example.ch',
    status: 'Active',
    appointmentTime: '09:30',
    appointmentType: 'Follow-up consultation',
    reasonForVisit: 'Migraine review and new LDL result',
    warning: 'Penicillin allergy; LDL increased 12%',
    avatarInitials: 'EL',
    assignedClinician: 'Dr. Müller',
    sex: 'Female',
    patientId: 'P360-1042',
    bloodType: 'O+',
    majorAllergies: ['Penicillin'],
    majorDiagnoses: ['Migraine without aura', 'Hyperlipidemia'],
    riskIndicators: ['Elevated LDL', 'Worsening headache frequency'],
    measurements: [
      { id: 'm-bp', label: 'Blood pressure', value: '128/82 mmHg', date: '2026-09-12', provenance: 'clinical' },
      { id: 'm-hr', label: 'Heart rate', value: '74 bpm', date: '2026-09-12', provenance: 'clinical' },
      { id: 'm-weight', label: 'Weight', value: '68 kg', date: '2026-09-02', provenance: 'patient-reported' }
    ],
    labs: [
      { id: 'lab-ldl-sept', label: 'LDL cholesterol', value: '4.2', unit: 'mmol/L', referenceRange: '< 3.0', previousValue: '3.7', trend: 'up', abnormal: true, date: '2026-08-18', sourceId: 'event-lab-aug-18' },
      { id: 'lab-hba1c-sept', label: 'HbA1c', value: '5.4', unit: '%', referenceRange: '4.0-5.6', previousValue: '5.3', trend: 'stable', abnormal: false, date: '2026-08-18', sourceId: 'event-lab-aug-18' }
    ],
    medications: [
      { id: 'med-sumatriptan', name: 'Sumatriptan', dosage: '50 mg', frequency: 'As needed', route: 'Oral', startDate: '2026-03-11', prescriber: 'Dr. Müller', reason: 'Migraine attacks', current: true },
      { id: 'med-magnesium', name: 'Magnesium', dosage: '300 mg', frequency: 'Daily', route: 'Oral', startDate: '2026-09-02', prescriber: 'Patient-reported', reason: 'Migraine prevention', current: true }
    ],
    documents: [
      { id: 'doc-lab-aug', title: 'August lipid panel', type: 'Laboratory report', date: '2026-08-18', source: 'Limmat Lab', processingState: 'processed', uploadedBy: 'Clinic inbox' },
      { id: 'doc-neuro-sept', title: 'Neurology report', type: 'External medical report', date: '2026-09-14', source: 'Neurology Zentrum Zürich', processingState: 'pending-review', uploadedBy: 'Emma Laurent' }
    ],
    notes: [
      { id: 'note-consult-sept', title: 'Migraine follow-up', author: 'Dr. Müller', date: '2026-09-12', text: 'Migraine frequency increased to three episodes per month. No neurological red flags documented.' }
    ]
  },
  {
    id: 'jonas-meier',
    fullName: 'Jonas Meier',
    age: 58,
    dateOfBirth: '1968-01-09',
    phone: '+41 79 555 0199',
    email: 'jonas.meier@example.ch',
    status: 'Active',
    appointmentTime: '11:00',
    appointmentType: 'Diabetes check',
    reasonForVisit: 'Dizziness reported after medication change',
    warning: 'New dizziness questionnaire',
    avatarInitials: 'JM',
    assignedClinician: 'Dr. Müller',
    sex: 'Male',
    patientId: 'P360-1068',
    bloodType: 'A+',
    majorAllergies: [],
    majorDiagnoses: ['Type 2 diabetes', 'Hypertension'],
    riskIndicators: ['Reported dizziness'],
    measurements: [],
    labs: [],
    medications: [],
    documents: [],
    notes: []
  }
];

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
```

- [ ] **Step 4: Create the mock service facade**

`src/services/mockApi.ts`

```ts
import { homeDashboard, patients, timelineEvents } from '../data/mockPatient360';
import type { AiAnswer, AskPatient360Request, ExtractedFact, HomeDashboard, Patient, PatientSummary, TimelineEvent } from '../types/patient360';

const delay = async (ms = 220) => new Promise(resolve => window.setTimeout(resolve, ms));

export const mockApi = {
  async getHomeDashboard(): Promise<HomeDashboard> {
    await delay();
    return homeDashboard;
  },

  async getPatients(): Promise<PatientSummary[]> {
    await delay();
    return patients;
  },

  async searchPatients(query: string, mode: 'standard' | 'ai'): Promise<PatientSummary[]> {
    await delay(280);
    const normalized = query.trim().toLowerCase();
    const matches = patients.filter(patient => {
      const haystack = [
        patient.fullName,
        patient.patientId,
        patient.dateOfBirth,
        patient.phone,
        patient.email,
        patient.assignedClinician,
        patient.majorDiagnoses.join(' '),
        patient.medications.map(medication => medication.name).join(' ')
      ].join(' ').toLowerCase();
      return normalized.length === 0 || haystack.includes(normalized) || mode === 'ai';
    });

    return matches.map(patient => ({
      ...patient,
      resultMode: mode,
      reason: mode === 'ai' ? `AI matched "${query}" against conditions, medications, recent activity, and notes.` : 'Matched structured patient fields.'
    }));
  },

  async getPatient(patientId: string): Promise<Patient> {
    await delay();
    const patient = patients.find(candidate => candidate.id === patientId);
    if (!patient) throw new Error(`Patient ${patientId} was not found`);
    return patient;
  },

  async getTimeline(patientId: string): Promise<TimelineEvent[]> {
    await delay();
    if (patientId !== 'emma-laurent') return [];
    return timelineEvents;
  },

  async askPatient360(request: AskPatient360Request): Promise<AiAnswer> {
    await delay(700);
    if (request.scope === 'clinic') {
      return {
        id: 'answer-clinic-1',
        answer: 'Three patients have outstanding blood tests, with Emma Laurent the highest-priority follow-up because her LDL increased and a neurology report is pending review.',
        retrievalSteps: ['Searching clinic tasks', 'Checking recent laboratory results', 'Applying Clinical Staff permissions'],
        citations: [
          { id: 'citation-att-ldl', label: 'Emma LDL result', sourceId: 'event-lab-aug-18', sourceType: 'lab' }
        ]
      };
    }

    return {
      id: 'answer-emma-migraine',
      answer: "Emma's migraine pattern changed from about once per month to about three episodes per month. The increase is supported by her September consultation and the patient update reporting headaches on four of the previous seven days. No neurological red flags have been documented.",
      retrievalSteps: ['Searching Emma Laurent timeline', 'Comparing symptom entries since last visit', 'Reading relevant consultation note', 'Preparing cited summary'],
      citations: [
        { id: 'citation-consult', label: '12 Sep consultation', sourceId: 'event-consult-sept-12', sourceType: 'visit' },
        { id: 'citation-update', label: '2 Sep patient update', sourceId: 'event-patient-update-sept-02', sourceType: 'patient-update' }
      ]
    };
  },

  async uploadDocument(patientId: string, fileName: string): Promise<{ documentId: string; extractedFacts: ExtractedFact[] }> {
    await delay(900);
    return {
      documentId: `${patientId}-${fileName}`,
      extractedFacts: [
        { id: 'fact-diagnosis', label: 'Diagnosis', value: 'Migraine without aura', sourceDocumentId: `${patientId}-${fileName}`, status: 'pending' },
        { id: 'fact-medication', label: 'Medication', value: 'Magnesium 300 mg daily', sourceDocumentId: `${patientId}-${fileName}`, status: 'pending' },
        { id: 'fact-followup', label: 'Follow-up', value: 'Review headache diary in 8 weeks', sourceDocumentId: `${patientId}-${fileName}`, status: 'pending' }
      ]
    };
  },

  async applyExtractedFact(patientId: string, factId: string, decision: 'accepted' | 'edited' | 'rejected'): Promise<{ patientId: string; factId: string; decision: string }> {
    await delay(260);
    return { patientId, factId, decision };
  }
};
```

- [ ] **Step 5: Run tests**

Run: `npm run test:unit -- tests/unit/mockApi.spec.ts`

Expected: all mock service tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/types src/data src/services tests/setup.ts tests/unit/mockApi.spec.ts
git commit -m "feat: add patient360 mock domain data"
```

---

### Task 3: Shared Layout, Navigation, And UI Primitives

**Files:**
- Create: `src/stores/useUiStore.ts`
- Create: `src/components/layout/AppShell.vue`
- Create: `src/components/layout/AskPatient360Panel.vue`
- Create: `src/components/ui/ProvenanceBadge.vue`
- Create: `src/components/ui/ClinicalCard.vue`
- Create: `src/components/ui/MetricTile.vue`
- Create: `src/components/ui/StatusPill.vue`
- Create: `src/components/ui/LargeTabs.vue`
- Create: `src/components/ui/EmptyState.vue`
- Create: `src/components/ui/SourceCitation.vue`
- Create: `tests/unit/provenance.spec.ts`

**Interfaces:**
- Consumes: route names from Task 1 and `mockApi.askPatient360()` from Task 2.
- Produces: `useUiStore()` with `askPanelOpen`, `selectedPatientId`, `highlightedSourceId`, `openAskPanel(patientId?: string)`, and `highlightSource(sourceId: string)`.

- [ ] **Step 1: Write provenance rendering tests**

`tests/unit/provenance.spec.ts`

```ts
import { render, screen } from '@testing-library/vue';
import ProvenanceBadge from '../../src/components/ui/ProvenanceBadge.vue';

describe('ProvenanceBadge', () => {
  it('marks AI content with the required symbol', () => {
    render(ProvenanceBadge, { props: { provenance: 'ai-generated' } });
    expect(screen.getByText('✦ AI generated')).toBeInTheDocument();
  });

  it('marks patient-reported content with explicit text', () => {
    render(ProvenanceBadge, { props: { provenance: 'patient-reported' } });
    expect(screen.getByText('Patient reported')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Create UI state store**

`src/stores/useUiStore.ts`

```ts
import { defineStore } from 'pinia';

export const useUiStore = defineStore('ui', {
  state: () => ({
    askPanelOpen: false,
    selectedPatientId: 'emma-laurent',
    highlightedSourceId: ''
  }),
  actions: {
    openAskPanel(patientId?: string) {
      if (patientId) this.selectedPatientId = patientId;
      this.askPanelOpen = true;
    },
    closeAskPanel() {
      this.askPanelOpen = false;
    },
    highlightSource(sourceId: string) {
      this.highlightedSourceId = sourceId;
    }
  }
});
```

- [ ] **Step 3: Create provenance and card primitives**

`src/components/ui/ProvenanceBadge.vue`

```vue
<template>
  <span class="badge" :class="provenance">
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { Provenance } from '../../types/patient360';

const props = defineProps<{ provenance: Provenance }>();

const label = computed(() => {
  if (props.provenance === 'ai-generated') return '✦ AI generated';
  if (props.provenance === 'patient-reported') return 'Patient reported';
  return 'Clinical record';
});
</script>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  border-radius: 999px;
  padding: 0 12px;
  font-size: 14px;
  font-weight: 700;
}

.clinical {
  background: #f4efe5;
}

.patient-reported {
  background: var(--color-pink-soft);
}

.ai-generated {
  background: var(--color-yellow);
}
</style>
```

`src/components/ui/ClinicalCard.vue`

```vue
<template>
  <section class="card" :class="{ ai }" :aria-labelledby="titleId">
    <div class="card__header">
      <p v-if="eyebrow" class="card__eyebrow">{{ eyebrow }}</p>
      <h2 :id="titleId">{{ title }}</h2>
    </div>
    <slot />
  </section>
</template>

<script setup lang="ts">
const props = defineProps<{ title: string; eyebrow?: string; ai?: boolean }>();
const titleId = `card-${props.title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
</script>

<style scoped>
.card {
  background: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-card);
  padding: 22px;
  box-shadow: var(--shadow-soft);
}

.card.ai {
  background: var(--color-yellow-soft);
}

.card__header {
  margin-bottom: 16px;
}

.card__eyebrow {
  margin: 0 0 4px;
  color: var(--color-muted);
  font-size: 14px;
  font-weight: 800;
  text-transform: uppercase;
}

h2 {
  margin: 0;
  font-size: clamp(1.35rem, 2vw, 1.8rem);
}
</style>
```

- [ ] **Step 4: Create layout shell**

`src/components/layout/AppShell.vue`

```vue
<template>
  <div class="shell">
    <aside class="nav" aria-label="Primary">
      <RouterLink class="brand" to="/">Patient360</RouterLink>
      <RouterLink v-for="item in navItems" :key="item.to" class="nav__item" :to="item.to">
        <component :is="item.icon" aria-hidden="true" />
        <span>{{ item.label }}</span>
      </RouterLink>
    </aside>

    <div class="workspace">
      <header class="topbar">
        <div>
          <p class="topbar__eyebrow">Clinical Staff</p>
          <strong>Warm, clear patient intelligence</strong>
        </div>
        <button class="ask-button" type="button" @click="ui.openAskPanel(route.params.patientId as string | undefined)">
          ✦ Ask Patient360
        </button>
      </header>

      <nav v-if="route.params.patientId" class="patient-tabs" aria-label="Patient sections">
        <RouterLink v-for="tab in patientTabs" :key="tab.to" :to="tab.to">{{ tab.label }}</RouterLink>
      </nav>

      <main class="content">
        <slot />
      </main>
    </div>

    <AskPatient360Panel />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink, useRoute } from 'vue-router';
import { ClipboardList, FileText, Home, LockKeyhole, Search, Sparkles, Users } from 'lucide-vue-next';
import { useUiStore } from '../../stores/useUiStore';
import AskPatient360Panel from './AskPatient360Panel.vue';

const route = useRoute();
const ui = useUiStore();

const navItems = [
  { label: 'Home', to: '/', icon: Home },
  { label: 'Patients', to: '/patients', icon: Search },
  { label: 'Tasks / Follow-ups', to: '/tasks', icon: ClipboardList },
  { label: 'Documents / Inbox', to: '/patients/emma-laurent/documents', icon: FileText },
  { label: 'Cohort Insights', to: '/cohort', icon: Users },
  { label: 'Audit & Privacy', to: '/audit', icon: LockKeyhole }
];

const patientTabs = computed(() => {
  const id = route.params.patientId;
  return [
    { label: 'Overview', to: `/patients/${id}/overview` },
    { label: 'Timeline', to: `/patients/${id}/timeline` },
    { label: 'Labs', to: `/patients/${id}/labs` },
    { label: 'Medications', to: `/patients/${id}/medications` },
    { label: 'Documents', to: `/patients/${id}/documents` },
    { label: 'Notes', to: `/patients/${id}/notes` }
  ];
});
</script>
```

- [ ] **Step 5: Implement the AI side panel**

`src/components/layout/AskPatient360Panel.vue`

```vue
<template>
  <aside v-if="ui.askPanelOpen" class="panel" aria-label="Ask Patient360">
    <header class="panel__header">
      <div>
        <p>✦ Ask Patient360</p>
        <h2>{{ ui.selectedPatientId ? 'Patient context active' : 'Clinic context' }}</h2>
      </div>
      <button type="button" @click="ui.closeAskPanel">Close</button>
    </header>

    <form class="question" @submit.prevent="ask">
      <label for="ask-input">Question</label>
      <textarea id="ask-input" v-model="question" rows="3" />
      <button type="submit">Ask with sources</button>
    </form>

    <ol v-if="loading" class="steps">
      <li v-for="step in loadingSteps" :key="step">{{ step }}</li>
    </ol>

    <article v-if="answer" class="answer">
      <h3>✦ Answer</h3>
      <p>{{ answer.answer }}</p>
      <div class="citations">
        <button v-for="citation in answer.citations" :key="citation.id" type="button" @click="ui.highlightSource(citation.sourceId)">
          {{ citation.label }}
        </button>
      </div>
    </article>
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { mockApi } from '../../services/mockApi';
import type { AiAnswer } from '../../types/patient360';
import { useUiStore } from '../../stores/useUiStore';

const ui = useUiStore();
const question = ref("What changed with Emma's migraines over the last six months?");
const loading = ref(false);
const answer = ref<AiAnswer | null>(null);
const loadingSteps = ['Searching clinical history...', 'Reading relevant documents...', 'Preparing cited summary...'];

async function ask() {
  loading.value = true;
  answer.value = null;
  answer.value = await mockApi.askPatient360({
    scope: ui.selectedPatientId ? 'patient' : 'clinic',
    patientId: ui.selectedPatientId,
    question: question.value
  });
  loading.value = false;
}
</script>
```

- [ ] **Step 6: Style layout and remaining primitives**

Implement `MetricTile.vue`, `StatusPill.vue`, `LargeTabs.vue`, `EmptyState.vue`, and `SourceCitation.vue` using the same CSS variables. Give every button at least `min-height: 44px`, every repeated card a clear heading, and every AI surface a `✦` label.

- [ ] **Step 7: Run tests**

Run: `npm run test:unit -- tests/unit/provenance.spec.ts`

Expected: all provenance tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/stores src/components tests/unit/provenance.spec.ts
git commit -m "feat: add patient360 shell and shared ui"
```

---

### Task 4: Patient 360 Overview Vertical Slice

**Files:**
- Create: `src/features/patient360/PatientOverviewView.vue`
- Create: `src/features/patient360/PatientHeader.vue`
- Create: `src/features/patient360/ClinicalBrief.vue`
- Create: `src/features/patient360/SinceLastVisit.vue`
- Create: `src/features/patient360/CurrentSnapshot.vue`
- Create: `tests/unit/patientOverview.spec.ts`

**Interfaces:**
- Consumes: `mockApi.getPatient(patientId)`, `mockApi.getTimeline(patientId)`, `useUiStore.openAskPanel(patientId)`.
- Produces: A polished `/patients/emma-laurent/overview` page with immediate clinical context, review prompts, latest measurements, labs, medications, and AI brief.

- [ ] **Step 1: Write the overview test**

`tests/unit/patientOverview.spec.ts`

```ts
import { render, screen } from '@testing-library/vue';
import { createTestingPinia } from '@pinia/testing';
import { createRouter, createWebHistory } from 'vue-router';
import PatientOverviewView from '../../src/features/patient360/PatientOverviewView.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: '/patients/:patientId/overview', component: PatientOverviewView }]
});

describe('PatientOverviewView', () => {
  it('surfaces the Patient 360 five-second context', async () => {
    router.push('/patients/emma-laurent/overview');
    await router.isReady();

    render(PatientOverviewView, {
      global: { plugins: [router, createTestingPinia({ stubActions: false })] }
    });

    expect(await screen.findByText('Emma Laurent')).toBeInTheDocument();
    expect(screen.getByText('Penicillin')).toBeInTheDocument();
    expect(screen.getByText('✦ Clinical Brief')).toBeInTheDocument();
    expect(screen.getByText('Since your last consultation')).toBeInTheDocument();
    expect(screen.getByText('LDL cholesterol')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement `PatientOverviewView.vue`**

```vue
<template>
  <div v-if="patient" class="overview">
    <PatientHeader :patient="patient" />
    <section class="overview__grid">
      <ClinicalBrief :patient="patient" />
      <SinceLastVisit :patient="patient" />
      <CurrentSnapshot :patient="patient" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { mockApi } from '../../services/mockApi';
import type { Patient } from '../../types/patient360';
import PatientHeader from './PatientHeader.vue';
import ClinicalBrief from './ClinicalBrief.vue';
import SinceLastVisit from './SinceLastVisit.vue';
import CurrentSnapshot from './CurrentSnapshot.vue';

const route = useRoute();
const patient = ref<Patient | null>(null);

onMounted(async () => {
  patient.value = await mockApi.getPatient(route.params.patientId as string);
});
</script>
```

- [ ] **Step 3: Implement `PatientHeader.vue`**

Show `fullName`, `age`, `sex`, `patientId`, `status`, `assignedClinician`, `majorAllergies`, `bloodType`, `majorDiagnoses`, and `riskIndicators`. Make severe allergies textually explicit with the label `Severe allergy` next to the allergy name.

- [ ] **Step 4: Implement `ClinicalBrief.vue`**

Render a light-yellow AI card titled `✦ Clinical Brief` with exactly these three source-backed statements:

```ts
const briefStatements = [
  'Emma’s migraine frequency has increased from approximately once per month to three times per month since June.',
  'Her latest LDL measurement is elevated compared with her previous result.',
  'No neurological red flags have been documented.'
];
```

Add buttons labeled `View sources`, `Regenerate summary`, and `Ask follow-up`. `Ask follow-up` calls `useUiStore().openAskPanel(patient.id)`.

- [ ] **Step 5: Implement `SinceLastVisit.vue`**

Render the following clickable change items as large rows:

```ts
const changes = [
  { label: '3 new symptom entries', target: 'event-patient-update-sept-02' },
  { label: '1 new laboratory result', target: 'event-lab-aug-18' },
  { label: 'LDL increased 12%', target: 'event-lab-aug-18' },
  { label: 'Patient reported starting magnesium', target: 'event-patient-update-sept-02' },
  { label: 'No new allergies', target: 'allergies' },
  { label: 'No clinician-entered medication changes', target: 'medications' }
];
```

Clicking a row calls `useUiStore().highlightSource(target)`.

- [ ] **Step 6: Implement `CurrentSnapshot.vue`**

Render sections for `Conditions`, `Medications`, `Allergies`, `Latest measurements`, `Latest labs`, and `Things to review`. Labs with `abnormal: true` show the text `Above reference range` and an upward icon from lucide-vue-next.

- [ ] **Step 7: Run tests and build**

Run: `npm run test:unit -- tests/unit/patientOverview.spec.ts`

Run: `npm run build`

Expected: test and build pass.

- [ ] **Step 8: Commit**

```bash
git add src/features/patient360 tests/unit/patientOverview.spec.ts
git commit -m "feat: build patient360 overview slice"
```

---

### Task 5: Timeline, Citation Highlighting, Labs, Medications, Documents, And Notes

**Files:**
- Create: `src/features/patient360/TimelineView.vue`
- Create: `src/features/patient360/TimelineEventCard.vue`
- Create: `src/features/patient360/LabsView.vue`
- Create: `src/features/patient360/MedicationsView.vue`
- Create: `src/features/patient360/DocumentsView.vue`
- Create: `src/features/patient360/NotesView.vue`
- Create: `tests/unit/timeline.spec.ts`

**Interfaces:**
- Consumes: `mockApi.getPatient()`, `mockApi.getTimeline()`, `mockApi.uploadDocument()`, `mockApi.applyExtractedFact()`, and `useUiStore.highlightedSourceId`.
- Produces: Patient section routes that support the signature demo sequence: timeline filtering, cited AI source highlighting, upload extraction, and clinician accept/edit/reject decisions.

- [ ] **Step 1: Write timeline filtering test**

`tests/unit/timeline.spec.ts`

```ts
import { timelineEvents } from '../../src/data/mockPatient360';

function filterEvents(kind: string) {
  return kind === 'all' ? timelineEvents : timelineEvents.filter(event => event.kind === kind);
}

describe('timeline filtering', () => {
  it('keeps all events visible by default', () => {
    expect(filterEvents('all')).toHaveLength(timelineEvents.length);
  });

  it('filters labs without losing the abnormal LDL event', () => {
    const labs = filterEvents('lab');
    expect(labs).toHaveLength(1);
    expect(labs[0].id).toBe('event-lab-aug-18');
  });
});
```

- [ ] **Step 2: Implement `TimelineView.vue`**

Use large pill tabs for `All`, `Visits`, `Labs`, `Medications`, `Patient updates`, `Documents`, and `Notes`. Default to `All`. Render chronological cards with date, title, summary, tags, and `ProvenanceBadge`.

- [ ] **Step 3: Implement `TimelineEventCard.vue`**

Accept props `{ event: TimelineEvent; highlighted: boolean }`. If `highlighted` is true, apply a thick pink outline and include visible text `Source highlighted from AI answer`.

- [ ] **Step 4: Implement `LabsView.vue`**

Render current lab values with reference range, previous value, date, source, trend, and readable Chart.js line charts. Include buttons `✦ Explain trend`, `✦ Compare with previous results`, and `✦ Find related history`; each opens the AI panel for the current patient.

- [ ] **Step 5: Implement `MedicationsView.vue`**

Separate current and historical medication sections. For each medication show name, dosage, frequency, route, start date, stop date if present, prescriber, and reason. Add an AI action labeled `✦ Summarize changes over six months`.

- [ ] **Step 6: Implement `DocumentsView.vue`**

Render document type, date, source, processing state, and uploader. Add a mock upload control that calls `mockApi.uploadDocument('emma-laurent', selectedFileName)` and displays extracted facts under `Information detected`. Each fact has `Accept`, `Edit`, and `Reject` buttons that call `mockApi.applyExtractedFact()`. After accepting a fact, update the row status text to `Accepted into review queue`.

- [ ] **Step 7: Implement `NotesView.vue`**

Render note title, author, date, original text, and AI action buttons `✦ Summarize note`, `✦ Convert to structured fields`, `✦ Extract follow-up tasks`, `✦ Draft consultation summary`, and `✦ Find previous related notes`. The original note text remains visible after every action.

- [ ] **Step 8: Run tests and build**

Run: `npm run test:unit -- tests/unit/timeline.spec.ts`

Run: `npm run build`

Expected: test and build pass.

- [ ] **Step 9: Commit**

```bash
git add src/features/patient360 tests/unit/timeline.spec.ts
git commit -m "feat: add patient360 clinical detail views"
```

---

### Task 6: Clinic Home And Patients Search

**Files:**
- Create: `src/features/home/HomeView.vue`
- Create: `src/features/home/TodaysPatients.vue`
- Create: `src/features/home/MorningBriefing.vue`
- Create: `src/features/home/NeedsAttention.vue`
- Create: `src/features/home/RecentPatientActivity.vue`
- Create: `src/features/patients/PatientsView.vue`
- Create: `tests/unit/patientSearch.spec.ts`

**Interfaces:**
- Consumes: `mockApi.getHomeDashboard()`, `mockApi.searchPatients()`, and Patient 360 route `/patients/:patientId/overview`.
- Produces: A daily command center and a patient search screen with standard and AI-generated search modes.

- [ ] **Step 1: Write patient search test**

`tests/unit/patientSearch.spec.ts`

```ts
import { mockApi } from '../../src/services/mockApi';

describe('patient search', () => {
  it('supports structured search by name', async () => {
    const results = await mockApi.searchPatients('Emma', 'standard');
    expect(results[0].fullName).toBe('Emma Laurent');
    expect(results[0].resultMode).toBe('standard');
  });

  it('supports AI discovery queries', async () => {
    const results = await mockApi.searchPatients('patients with diabetes who recently reported dizziness', 'ai');
    expect(results.some(patient => patient.fullName === 'Jonas Meier')).toBe(true);
    expect(results[0].reason).toContain('AI matched');
  });
});
```

- [ ] **Step 2: Implement `HomeView.vue`**

Fetch `mockApi.getHomeDashboard()` on mount. Render page title `Today`, then `TodaysPatients`, `MorningBriefing`, `NeedsAttention`, and `RecentPatientActivity` in a responsive two-column layout that collapses to one column on narrow screens.

- [ ] **Step 3: Implement home sections**

`TodaysPatients.vue` renders large patient cards with patient name, age, appointment time, appointment type, reason for visit, warning, and avatar. Clicking a card routes to `/patients/{id}/overview`.

`MorningBriefing.vue` renders the AI-generated briefing in a yellow card with `✦ Morning Briefing` and links each patient-specific statement to the patient overview.

`NeedsAttention.vue` renders alerts with severity text `Review`, `Warning`, or `Urgent`, plus provenance badges.

`RecentPatientActivity.vue` renders recent timeline items with date, title, summary, and provenance.

- [ ] **Step 4: Implement `PatientsView.vue`**

Provide a search input, mode switch with buttons `Standard search` and `Natural-language AI search`, filter chips for `Assigned clinician`, `Active`, `Diagnosis`, `Appointment status`, and `Recent activity`, and result cards. AI-mode result cards must show `✦ AI generated result` and the mock reason from `PatientSummary.reason`.

- [ ] **Step 5: Run tests and build**

Run: `npm run test:unit -- tests/unit/patientSearch.spec.ts`

Run: `npm run build`

Expected: test and build pass.

- [ ] **Step 6: Commit**

```bash
git add src/features/home src/features/patients tests/unit/patientSearch.spec.ts
git commit -m "feat: add home dashboard and patient search"
```

---

### Task 7: Supporting Clinic And Patient Portal Screens

**Files:**
- Create: `src/features/clinic/TasksView.vue`
- Create: `src/features/clinic/CohortInsightsView.vue`
- Create: `src/features/clinic/AuditPrivacyView.vue`
- Create: `src/features/portal/PatientPortalView.vue`

**Interfaces:**
- Consumes: shared UI primitives and mock data.
- Produces: Convincing supporting routes for Tasks / Follow-ups, Cohort Insights, Audit & Privacy, and Patient Portal.

- [ ] **Step 1: Implement `TasksView.vue`**

Render tasks:

```ts
const tasks = [
  { patient: 'Emma Laurent', description: 'Review newly uploaded neurology report', dueDate: '2026-09-14', assignee: 'Dr. Müller', priority: 'High', status: 'Pending', source: '✦ AI suggested' },
  { patient: 'Emma Laurent', description: 'Repeat lipid panel in three months', dueDate: '2026-12-18', assignee: 'Nurse Keller', priority: 'Normal', status: 'Needs confirmation', source: 'Clinical plan' },
  { patient: 'Jonas Meier', description: 'Call patient about dizziness after medication change', dueDate: '2026-09-15', assignee: 'Clinical assistant', priority: 'High', status: 'Pending', source: 'Patient questionnaire' }
];
```

AI-suggested tasks show `Confirm task` and `Dismiss` buttons.

- [ ] **Step 2: Implement `CohortInsightsView.vue`**

Render clinic-level AI answer cards for outstanding blood tests, worsening symptoms this week, and hypertensive patients without recent blood pressure measurement. Include one Chart.js bar chart and an underlying patient list.

- [ ] **Step 3: Implement `AuditPrivacyView.vue`**

Render audit rows exactly matching the spec examples:

```ts
const auditRows = [
  { time: '17:04', actor: 'Dr. Müller', action: 'Viewed Emma Laurent → Laboratory results' },
  { time: '16:52', actor: 'AI Assistant', action: 'Accessed 3 records to answer clinical query' },
  { time: '16:44', actor: 'Access denied', action: 'Restricted document requested' }
];
```

Add visible explanatory labels `AI query access`, `Patient record access`, and `Blocked access`.

- [ ] **Step 4: Implement `PatientPortalView.vue`**

Render a simpler patient-facing surface with sections for personal information, questionnaires, medications, allergies, symptom reports, measurements, document upload, clinic requests, and submitted information. Keep copy patient-friendly and avoid clinical dashboard complexity.

- [ ] **Step 5: Run build**

Run: `npm run build`

Expected: build passes.

- [ ] **Step 6: Commit**

```bash
git add src/features/clinic src/features/portal
git commit -m "feat: add supporting patient360 demo screens"
```

---

### Task 8: Signature Demo Flow And End-To-End Verification

**Files:**
- Create: `playwright.config.ts`
- Create: `tests/e2e/patient360.spec.ts`
- Modify: `package.json`
- Create: `README.md`

**Interfaces:**
- Consumes: all route and UI behavior from Tasks 1-7.
- Produces: An automated smoke test for the hackathon demo sequence and a short README for running the app.

- [ ] **Step 1: Create Playwright config**

`playwright.config.ts`

```ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  webServer: {
    command: 'npm run dev -- --port 5173',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: true
  },
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'on-first-retry'
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } }
  ]
});
```

- [ ] **Step 2: Write the demo-flow test**

`tests/e2e/patient360.spec.ts`

```ts
import { expect, test } from '@playwright/test';

test('signature Patient360 demo flow', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible();
  await page.getByText('Emma Laurent').first().click();

  await expect(page.getByRole('heading', { name: 'Emma Laurent' })).toBeVisible();
  await expect(page.getByText('✦ Clinical Brief')).toBeVisible();
  await expect(page.getByText('Since your last consultation')).toBeVisible();

  await page.getByRole('link', { name: 'Timeline' }).click();
  await expect(page.getByText('Consultation')).toBeVisible();
  await expect(page.getByText('Patient update')).toBeVisible();
  await expect(page.getByText('Laboratory result')).toBeVisible();

  await page.getByRole('button', { name: '✦ Ask Patient360' }).click();
  await page.getByRole('button', { name: 'Ask with sources' }).click();
  await expect(page.getByText("Emma's migraine pattern changed")).toBeVisible();
  await page.getByRole('button', { name: '12 Sep consultation' }).click();
  await expect(page.getByText('Source highlighted from AI answer')).toBeVisible();

  await page.getByRole('link', { name: 'Documents' }).click();
  await page.getByLabel('Upload document').setInputFiles({
    name: 'neurology-report.pdf',
    mimeType: 'application/pdf',
    buffer: Buffer.from('demo report')
  });
  await expect(page.getByText('Information detected')).toBeVisible();
  await page.getByRole('button', { name: 'Accept' }).first().click();
  await expect(page.getByText('Accepted into review queue')).toBeVisible();
});
```

- [ ] **Step 3: Create README**

`README.md`

```md
# Patient360

Vue.js frontend demo for the Patient360 clinical workspace.

## Run Locally

```bash
npm install
npm run dev
```

Open `http://localhost:5173`.

## Demo Path

1. Open the Home dashboard.
2. Select Emma Laurent.
3. Review the Patient 360 overview, Clinical Brief, Since Last Visit, and Current Snapshot.
4. Open Timeline.
5. Ask Patient360 what changed with Emma's migraines over the last six months.
6. Click an AI citation to highlight the source event.
7. Open Documents, upload a mock report, and accept an extracted fact.

## Backend Integration

All data access is isolated in `src/services/mockApi.ts`. Replace those functions with real backend clients when the backend is ready.
```

- [ ] **Step 4: Run full verification**

Run: `npm run test`

Run: `npm run test:e2e`

Expected: unit tests, production build, and Playwright tests pass on desktop and mobile projects.

- [ ] **Step 5: Commit**

```bash
git add playwright.config.ts tests/e2e README.md package.json
git commit -m "test: cover patient360 signature demo flow"
```

---

## Self-Review

**Spec coverage:** The plan covers the core dashboard layout, Home, Patients, Patient 360 overview, timeline, labs, medications, documents, notes, Ask Patient360, clinic-level AI, tasks, audit/privacy, patient portal, provenance, visual design constraints, accessibility constraints, AI loading states, empty-state primitive, and signature demo sequence.

**Intentional limits:** ABAC is represented through permission-ready types and component boundaries, while exact policies are deferred because the spec says those policies are undefined. Backend behavior is represented by typed mock services because the requested stack is frontend-only for this phase.

**Placeholder scan:** The plan avoids incomplete implementation markers and gives concrete files, interfaces, tests, data, labels, and expected behavior for every task. Backend integration is isolated behind `mockApi.ts`.

**Type consistency:** Later tasks use the route names, mock API methods, store actions, and domain type names introduced in earlier tasks.

---

Plan complete and saved to `docs/superpowers/plans/2026-09-14-patient360-vue-frontend.md`. Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
