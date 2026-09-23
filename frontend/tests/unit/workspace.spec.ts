import { describe, expect, it } from 'vitest';
import {
  allergyQueryDataset,
  canLaunchAsk,
  chartQueryDatasets,
  defaultPatientPath,
  directoryCopy,
  familyPeople,
  navItemsFor,
  patientTabsFor,
  workspaceFor
} from '../../src/services/workspace';
import type { PatientSummary } from '../../src/types/patient360';

const visible: PatientSummary = {
  id: 'p_104',
  fullName: 'Jonas Haller',
  age: 16,
  dateOfBirth: '2010-01-01',
  phone: '',
  email: '',
  status: 'Visible',
  avatarInitials: 'JH',
  assignedClinician: ''
};

describe('workspaceFor', () => {
  it('maps each demo role to a distinct workspace', () => {
    expect(workspaceFor('attending')).toBe('clinical');
    expect(workspaceFor('care_team')).toBe('clinical');
    expect(workspaceFor('consultant')).toBe('clinical');
    expect(workspaceFor('caregiver')).toBe('family');
    expect(workspaceFor('patient')).toBe('family');
    expect(workspaceFor('dietary_staff')).toBe('kitchen');
    expect(workspaceFor('researcher')).toBe('research');
    expect(workspaceFor('auditor')).toBe('audit');
  });
});

describe('navItemsFor', () => {
  it('keeps the clinical staff chrome for an attending', () => {
    expect(navItemsFor('clinical', ['labs', 'notes', 'imaging', 'appointments', 'aggregate_own_patients', 'break_glass'], {}).map(item => item.label)).toEqual([
      'Home',
      'Patients',
      'Tasks / Follow-ups',
      'Cohort Insights',
      'Red team'
    ]);
  });

  it('keeps Documents off the sidebar; chart tabs own that link', () => {
    expect(navItemsFor('clinical', ['notes', 'imaging'], {}).map(item => item.label)).not.toContain('Documents');
    expect(navItemsFor('clinical', ['notes', 'imaging'], { patientId: 'p_101' }).map(item => item.label)).not.toContain('Documents');
    expect(patientTabsFor('clinical', ['notes', 'imaging'], 'p_101').map(tab => tab.to)).toContain('/patients/p_101/documents');
  });

  it('gives caregivers a family portal, not Today or BTG tools', () => {
    expect(navItemsFor('family', ['portal', 'labs', 'consents', 'appointments', 'ask'], {}).map(item => item.label)).toEqual([
      'Home',
      'My people'
    ]);
  });

  it('adds family appointments from home only when the session has a self record', () => {
    expect(navItemsFor('family', ['appointments'], { selfPatientId: 'p_103' }).map(item => item.to)).toContain('/patients/p_103/appointments');
    expect(navItemsFor('family', ['appointments'], { selfPatientId: 'p_103', patientId: 'p_103' }).map(item => item.label)).not.toContain('Appointments');
  });

  it('gives dietary staff a kitchen board, not cohort or patients census', () => {
    expect(navItemsFor('kitchen', ['diet', 'allergies_food', 'aggregate_ward', 'ask'], {}).map(item => item.label)).toEqual([
      'Home',
      'Ward trays'
    ]);
  });

  it('keeps researcher and auditor off the clinical chart', () => {
    expect(navItemsFor('research', ['aggregate', 'ask'], {}).map(item => item.label)).toEqual(['Home', 'Cohort Insights']);
    expect(navItemsFor('audit', ['audit'], {}).map(item => item.label)).toEqual(['Home', 'Audit & Privacy']);
  });
});

describe('patientTabsFor', () => {
  it('limits the family chart and kitchen surface', () => {
    expect(patientTabsFor('family', ['labs', 'meds', 'appointments', 'notes', 'imaging'], 'p_104').map(tab => tab.label)).toEqual([
      'Overview',
      'Labs',
      'Medications',
      'Appointments'
    ]);
    expect(patientTabsFor('kitchen', ['diet', 'allergies_food'], 'p_101').map(tab => tab.to)).toEqual(['/patients/p_101/diet']);
    expect(patientTabsFor('research', ['aggregate'], 'p_101')).toEqual([]);
  });

  it('exposes Documents once on the clinical chart tabs', () => {
    const labels = patientTabsFor('clinical', ['labs', 'notes', 'imaging', 'meds', 'appointments'], 'p_101').map(tab => tab.label);
    expect(labels.filter(label => label === 'Documents')).toHaveLength(1);
    expect(labels).toEqual([
      'Overview',
      'Timeline',
      'Labs',
      'Medications',
      'Appointments',
      'Documents',
      'Notes',
      'Imaging'
    ]);
  });
});

describe('familyPeople', () => {
  it('uses the vault self key for a patient even without an identity banner', () => {
    const people = familyPeople({ self_patient_id: 'p_103', display: 'Maria Santos' }, []);
    expect(people).toEqual([expect.objectContaining({ id: 'p_103', fullName: 'Maria Santos', status: 'Visible' })]);
  });

  it('lists only identity-visible people for a caregiver', () => {
    expect(familyPeople({ self_patient_id: null, display: 'Nina Haller' }, [visible, { ...visible, id: 'p_205', status: 'Hidden' }])).toEqual([visible]);
  });
});

describe('workspace helpers', () => {
  it('routes kitchen cards to diet and maps food-allergy panel to the allergies dataset', () => {
    expect(defaultPatientPath('kitchen', 'p_101')).toBe('/patients/p_101/diet');
    expect(defaultPatientPath('family', 'p_104')).toBe('/patients/p_104/overview');
    expect(allergyQueryDataset(['allergies_food'])).toBe('allergies');
    expect(allergyQueryDataset(['allergies'])).toBe('allergies');
    expect(allergyQueryDataset(['labs'])).toBeNull();
    expect(chartQueryDatasets(['labs', 'conditions', 'meds', 'encounters', 'allergies', 'notes', 'imaging', 'ask'])).toEqual([
      'labs', 'conditions', 'meds', 'encounters', 'allergies'
    ]);
    expect(chartQueryDatasets(['diet', 'allergies_food'])).toEqual(['allergies', 'diet']);
    expect(directoryCopy('kitchen').title).toBe('Ward trays');
    expect(directoryCopy('family').title).toBe('My people');
  });
});

describe('canLaunchAsk', () => {
  const clinicalAsk = { panels: ['ask', 'labs'], workspace: 'clinical' as const, patientId: 'p_101', onDuty: true };

  it('allows clinical staff with ask panel, open chart, and on duty', () => {
    expect(canLaunchAsk(clinicalAsk)).toBe(true);
  });

  it('hides Ask on Today with no chart, off duty, or non-clinical workspaces', () => {
    expect(canLaunchAsk({ ...clinicalAsk, patientId: undefined })).toBe(false);
    expect(canLaunchAsk({ ...clinicalAsk, onDuty: false })).toBe(false);
    expect(canLaunchAsk({ ...clinicalAsk, panels: ['labs'] })).toBe(false);
    expect(canLaunchAsk({ ...clinicalAsk, workspace: 'family' })).toBe(false);
    expect(canLaunchAsk({ ...clinicalAsk, workspace: 'kitchen' })).toBe(false);
    expect(canLaunchAsk({ ...clinicalAsk, workspace: 'research' })).toBe(false);
  });
});
