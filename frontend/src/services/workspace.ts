import type { Me } from '../types/api';
import type { PatientSummary } from '../types/patient360';

export type Workspace = 'clinical' | 'family' | 'kitchen' | 'research' | 'audit';

export interface WorkspaceNavItem {
  label: string;
  to: string;
}

export interface WorkspaceTab {
  label: string;
  to: string;
}

export function workspaceFor(role: string | null | undefined): Workspace {
  if (role === 'caregiver' || role === 'patient') return 'family';
  if (role === 'dietary_staff') return 'kitchen';
  if (role === 'researcher') return 'research';
  if (role === 'auditor') return 'audit';
  return 'clinical';
}

/**
 * When the Ask Patient360 launcher may appear.
 * Matches usable Ask: server `ask` panel, clinical workspace (not portal/kitchen/research),
 * an open chart (Ask always needs a patient_key), and not off-duty.
 * API /chat remains the real gate; this only hides dead UI.
 */
export function canLaunchAsk(opts: {
  panels: readonly string[];
  workspace: Workspace;
  patientId?: string | null;
  onDuty?: boolean | null;
}): boolean {
  if (!opts.panels.includes('ask')) return false;
  if (opts.workspace !== 'clinical') return false;
  if (!opts.patientId) return false;
  if (opts.onDuty === false) return false;
  return true;
}

export function defaultPatientPath(workspace: Workspace, patientId: string): string {
  if (workspace === 'kitchen') return `/patients/${patientId}/diet`;
  return `/patients/${patientId}/overview`;
}

/** Food-allergy panel maps to the allergies dataset (dietary staff use can_read_diet). */
export function allergyQueryDataset(panels: readonly string[]): 'allergies' | null {
  if (panels.includes('allergies_food') || panels.includes('allergies')) return 'allergies';
  return null;
}

const CHART_DATASETS = ['labs', 'conditions', 'meds', 'encounters', 'allergies', 'diet'] as const;

export type ChartDataset = (typeof CHART_DATASETS)[number];

/** Datasets this session may ask /tools/query for. A missing panel is a uniform 404. */
export function chartQueryDatasets(panels: readonly string[]): ChartDataset[] {
  return CHART_DATASETS.filter(dataset => {
    if (dataset === 'allergies') return allergyQueryDataset(panels) === 'allergies';
    return panels.includes(dataset);
  });
}

export function navItemsFor(
  workspace: Workspace,
  panels: readonly string[],
  opts: { patientId?: string; selfPatientId?: string | null } = {}
): WorkspaceNavItem[] {
  const has = (panel: string) => panels.includes(panel);
  const items: WorkspaceNavItem[] = [{ label: 'Home', to: '/' }];

  if (workspace === 'clinical') {
    if (has('labs') || has('diet') || has('allergies_food')) items.push({ label: 'Patients', to: '/patients' });
    if (has('labs') || has('appointments')) items.push({ label: 'Tasks / Follow-ups', to: '/tasks' });
    // Documents lives in patientTabsFor only (chart open) — do not mirror it here.
    if (has('aggregate') || has('aggregate_own_patients')) items.push({ label: 'Cohort Insights', to: '/cohort' });
    if (has('audit')) items.push({ label: 'Audit & Privacy', to: '/audit' });
    if (has('audit') || has('break_glass')) items.push({ label: 'Red team', to: '/redteam' });
  }

  if (workspace === 'family') {
    items.push({ label: 'My people', to: '/patients' });
    // Chart tabs already expose Appointments for the open person. Keep a home
    // shortcut only for the session's own record when no chart is open.
    if (has('appointments') && !opts.patientId && opts.selfPatientId) {
      items.push({ label: 'Appointments', to: `/patients/${opts.selfPatientId}/appointments` });
    }
  }

  if (workspace === 'kitchen') {
    items.push({ label: 'Ward trays', to: '/patients' });
  }

  if (workspace === 'research' && has('aggregate')) {
    items.push({ label: 'Cohort Insights', to: '/cohort' });
  }

  if (workspace === 'audit' && has('audit')) {
    items.push({ label: 'Audit & Privacy', to: '/audit' });
  }

  return items;
}

export function patientTabsFor(
  workspace: Workspace,
  panels: readonly string[],
  patientId: string
): WorkspaceTab[] {
  const has = (panel: string) => panels.includes(panel);
  if (!patientId || workspace === 'research' || workspace === 'audit') return [];

  if (workspace === 'kitchen') {
    return [{ label: 'Diet', to: `/patients/${patientId}/diet` }];
  }

  if (workspace === 'family') {
    const tabs: Array<WorkspaceTab & { show: boolean }> = [
      { label: 'Overview', to: `/patients/${patientId}/overview`, show: true },
      { label: 'Labs', to: `/patients/${patientId}/labs`, show: has('labs') },
      { label: 'Medications', to: `/patients/${patientId}/medications`, show: has('meds') },
      { label: 'Appointments', to: `/patients/${patientId}/appointments`, show: has('appointments') },
      { label: 'Diet', to: `/patients/${patientId}/diet`, show: has('diet') || has('allergies_food') }
    ];
    return tabs.filter(tab => tab.show).map(({ label, to }) => ({ label, to }));
  }

  const tabs: Array<WorkspaceTab & { show: boolean }> = [
    { label: 'Overview', to: `/patients/${patientId}/overview`, show: ['labs', 'meds', 'encounters', 'diet', 'allergies'].some(has) },
    { label: 'Timeline', to: `/patients/${patientId}/timeline`, show: has('labs') },
    { label: 'Labs', to: `/patients/${patientId}/labs`, show: has('labs') },
    { label: 'Medications', to: `/patients/${patientId}/medications`, show: has('meds') },
    { label: 'Appointments', to: `/patients/${patientId}/appointments`, show: has('appointments') },
    { label: 'Diet', to: `/patients/${patientId}/diet`, show: has('diet') || has('allergies_food') },
    { label: 'Documents', to: `/patients/${patientId}/documents`, show: has('notes') || has('imaging') || has('imaging_metadata') },
    { label: 'Notes', to: `/patients/${patientId}/notes`, show: has('notes') },
    { label: 'Imaging', to: `/patients/${patientId}/imaging`, show: has('imaging') || has('imaging_metadata') }
  ];
  return tabs.filter(tab => tab.show).map(({ label, to }) => ({ label, to }));
}

export function directoryCopy(workspace: Workspace): { eyebrow: string; title: string; hint: string } {
  if (workspace === 'kitchen') {
    return {
      eyebrow: 'Kitchen',
      title: 'Ward trays',
      hint: 'Diet orders on your ward. Identity and MRN are not shown.'
    };
  }
  if (workspace === 'family') {
    return {
      eyebrow: 'Family',
      title: 'My people',
      hint: 'Only people this session can identify.'
    };
  }
  return {
    eyebrow: 'Directory',
    title: 'Patients',
    hint: 'Only patients this session can identify. Unauthorized keys are omitted, not listed as hidden.'
  };
}

export function familyPeople(
  me: Pick<Me, 'self_patient_id' | 'display'>,
  patients: PatientSummary[]
): PatientSummary[] {
  if (me.self_patient_id) {
    const mine = patients.find(patient => patient.id === me.self_patient_id);
    if (mine) return [mine];
    const label = me.display?.trim() || 'Your record';
    return [{
      id: me.self_patient_id,
      fullName: label,
      age: 0,
      dateOfBirth: '',
      phone: '',
      email: '',
      status: 'Visible',
      avatarInitials: label.slice(0, 2).toUpperCase(),
      assignedClinician: ''
    }];
  }
  return patients.filter(patient => patient.status === 'Visible');
}
