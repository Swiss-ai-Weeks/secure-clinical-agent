import { describe, expect, it } from 'vitest';
import { briefStatements, cleanSyntheaName, cleanSyntheaNote, composePatient, formatDietOrder, groupLabs, identityLine, kitchenCardFromDiet, sessionCanOpenSignedFiles, snapshotLabGroups, summariesFromKeys } from '../../src/services/patientRecord';
import type { QueryResponse } from '../../src/types/api';

function query(rows: Record<string, unknown>[], redacted_count = 0): QueryResponse {
  return {
    patient_key: 'p_101',
    dataset: 'labs',
    rows,
    row_count: rows.length,
    redacted_count,
    suppressed_cells: 0,
    obligations: {},
    decision: {
      effect: 'permit',
      reason_code: '',
      policy_id: '',
      policy_version: '',
      relation: '',
      purpose_of_event: 'TREAT',
      compliance_flag: false
    },
    audit_id: 'audit'
  };
}

describe('composePatient', () => {
  it('keeps ward placement out of risk indicators', () => {
    const patient = composePatient('p_101', null, {
      conditions: query([
        { display: 'Type 2 diabetes mellitus' },
        { display: 'Chronic kidney disease stage 3' }
      ]),
      labs: query([
        { cite_id: 'l1', display: 'HbA1c', value_num: 7.9, unit: '%', interpretation: 'H' },
        { cite_id: 'l2', display: 'HbA1c', value_num: 7.6, unit: '%', interpretation: 'H' },
        { cite_id: 'l3', display: 'Creatinine', value_num: 1.1, unit: 'mg/dL', interpretation: 'N' }
      ]),
      diet: query([
        { ward: 'w_3b', diet_codes: ['160670007', '386619000'] }
      ])
    });

    expect(patient.majorDiagnoses).toEqual([
      'Type 2 diabetes mellitus',
      'Chronic kidney disease stage 3'
    ]);
    expect(patient.placement).toBe('Ward w_3b · diabetic diet · low sodium diet');
    expect(patient.riskIndicators).toEqual(['HbA1c 7.9 %']);
    expect(patient.riskIndicators.join(' ')).not.toMatch(/w_3b/);
  });

  it('shows imaging report text instead of a dead signed-copy handle', () => {
    const patient = composePatient('p_101', null, {}, {
      imaging: {
        patient_key: 'p_101',
        studies: [],
        reports: [{
          cite_id: 'rep1',
          display: 'Chest X-ray',
          category: 'RAD',
          issued_at: '2026-09-11T10:00:00Z',
          conclusion_text: 'No acute cardiopulmonary process.',
          report_ref: 'reports/p_101/cxr.txt',
          study_id: 'study-row-1'
        }],
        obligations: {},
        audit_id: 'a'
      }
    });
    expect(patient.documents[0]).toMatchObject({
      title: 'Chest X-ray',
      type: 'Radiology',
      source: 'Imaging',
      date: '2026-09-11',
      summary: 'No acute cardiopulmonary process.'
    });
    expect(patient.documents[0].objectKey).toBeUndefined();
    expect(patient.documents[0].studyId).toBeUndefined();
  });

  it('shows an uploaded file in notes and documents beside clinical notes', () => {
    const patient = composePatient('p_101', null, {}, {
      notes: {
        patient_key: 'p_101',
        chunks: [{
          cite_id: 'abcd1234',
          note_id: 'notes/p_101/Backilyan.pdf.txt',
          provenance: 'patient-reported',
          published: true,
          text: 'Co-Founder and COO.'
        }],
        notes: [{
          cite_id: 'note-1',
          note_id: 'p101-admission-2026-09-10',
          type_display: 'Discharge summary',
          provenance: 'clinical',
          authored_at: '2026-09-10T18:00:00Z',
          published: true,
          text: 'Discharge summary body.'
        }],
        chunk_count: 1,
        obligations: {},
        audit_id: 'a'
      }
    });
    expect(patient.notes.map(note => note.title)).toEqual(['Backilyan.pdf', 'Discharge summary']);
    expect(patient.notes[0].author).toBe('Clinical');
    expect(patient.notes[0].storageKey).toBe('notes/p_101/Backilyan.pdf.txt');
    expect(patient.notes[0].text).toContain('Co-Founder');
    expect(patient.documents[0]).toMatchObject({
      title: 'Backilyan.pdf',
      type: 'Clinical',
      source: 'upload',
      objectKey: 'notes/p_101/Backilyan.pdf.txt'
    });
  });

  it('lists a clinical note when its sanitized file is a pdf', () => {
    const patient = composePatient('p_101', null, {}, {
      notes: {
        patient_key: 'p_101',
        chunks: [],
        notes: [{
          cite_id: 'note-1',
          note_id: 'p101-admission-2026-09-10',
          type_display: 'Discharge summary',
          provenance: 'clinical',
          authored_at: '2026-09-10T18:00:00Z',
          published: true,
          sanitized_ref: 'notes/p_101/p101-admission-2026-09-10.pdf'
        }],
        chunk_count: 0,
        obligations: {},
        audit_id: 'a'
      }
    });
    expect(patient.documents[0]).toMatchObject({
      title: 'Discharge summary',
      type: 'clinical',
      objectKey: 'notes/p_101/p101-admission-2026-09-10.pdf'
    });
  });

  it('keeps the historical pneumonia note and omits the signed file when it cannot be opened', () => {
    const notes = {
      patient_key: 'p_485ba8c8597d4c5cb0fbda55317119a3',
      chunks: [],
      notes: [{
        cite_id: 'note-hp',
        note_id: 'p_485ba8c8597d4c5cb0fbda55317119a3-historical-pneumonia',
        type_display: 'Historical pneumonia',
        provenance: 'clinical',
        authored_at: '2019-03-01T00:00:00Z',
        published: true,
        text: 'Prior pneumonia with hypoxemia, now resolved.',
        sanitized_ref: 'notes/p_485ba8c8597d4c5cb0fbda55317119a3/p_485ba8c8597d4c5cb0fbda55317119a3-historical-pneumonia.pdf'
      }],
      chunk_count: 0,
      obligations: {},
      audit_id: 'a'
    };
    const hidden = composePatient('p_485ba8c8597d4c5cb0fbda55317119a3', null, {}, {
      notes,
      canOpenSignedFiles: false
    });
    expect(hidden.documents.map(document => document.title)).not.toContain('Historical pneumonia');
    expect(hidden.notes[0]).toMatchObject({
      title: 'Historical pneumonia',
      text: 'Prior pneumonia with hypoxemia, now resolved.'
    });
    const shown = composePatient('p_485ba8c8597d4c5cb0fbda55317119a3', null, {}, { notes });
    expect(shown.documents[0]).toMatchObject({
      title: 'Historical pneumonia',
      objectKey: notes.notes[0].sanitized_ref
    });
  });

  it('turns raw observations into readable lab groups', () => {
    const patient = composePatient('p_101', null, {
      labs: query([
        { cite_id: 'p', display: 'Blood pressure panel with all children optional', effective_at: '2026-09-11' },
        { cite_id: 's', display: 'Systolic blood pressure', value_num: 148, unit: 'mm[Hg]', ref_low: 90, ref_high: 140, interpretation: 'H', effective_at: '2026-09-11' },
        { cite_id: 'd', display: 'Diastolic blood pressure', value_num: 92, unit: 'mm[Hg]', ref_low: 60, ref_high: 90, interpretation: 'H', effective_at: '2026-09-11' },
        { cite_id: 'a1', display: 'Hemoglobin A1c/Hemoglobin.total in Blood', value_num: 7.2, unit: '%', ref_low: 4, ref_high: 5.6, interpretation: 'H', effective_at: '2026-09-11' },
        { cite_id: 'a2', display: 'Hemoglobin A1c/Hemoglobin.total in Blood', value_num: 7.9, unit: '%', ref_low: 4, ref_high: 5.6, interpretation: 'H', effective_at: '2026-06-15' },
        { cite_id: 'g', display: 'Glomerular filtration rate/1.73 sq M.predicted', value_num: 48, unit: 'mL/min/{1.73_m2}', ref_low: 60, interpretation: 'L', effective_at: '2026-09-11' }
      ])
    });

    expect(patient.labs.map(lab => lab.label).sort()).toEqual(['Blood pressure', 'HbA1c', 'HbA1c', 'eGFR']);
    expect(patient.labs.find(lab => lab.label === 'Blood pressure')).toMatchObject({
      value: '148/92',
      unit: 'mmHg',
      flag: 'high'
    });
    expect(patient.labs.find(lab => lab.label === 'eGFR')).toMatchObject({
      unit: 'mL/min/1.73m²',
      flag: 'low',
      abnormal: true
    });

    const groups = groupLabs(patient.labs);
    expect(groups.map(group => group.label)).toEqual(['Blood pressure', 'eGFR', 'HbA1c']);
    expect(groups.find(group => group.label === 'HbA1c')?.prior).toHaveLength(1);
  });

  it('keeps Synthea charts on clinical conditions and labs', () => {
    const patient = composePatient('p_485ba8c8597d4c5cb0fbda55317119a3', {
      patient_key: 'p_485ba8c8597d4c5cb0fbda55317119a3',
      given_name: 'Norman647',
      family_name: 'Hettinger594',
      birth_date: '1999-11-25',
      sex: 'male',
      mrn: '4c7c0101-5383-203c-825e-9fa8dfca8721',
      purpose_of_event: 'TREAT',
      compliance_flag: false,
      audit_id: 'a',
      identity_audit_id: 'b'
    }, {
      conditions: query([
        { display: 'Prediabetes (finding)', clinical_status: 'active' },
        { display: 'Unemployed (finding)', clinical_status: 'active' },
        { display: 'Lack of access to transportation (finding)', clinical_status: 'active' },
        { display: 'Full-time employment (finding)', clinical_status: 'active' },
        { display: 'Received higher education (finding)', clinical_status: 'active' },
        { display: 'Medication review due (situation)', clinical_status: 'active' },
        { display: 'Social isolation (finding)', clinical_status: 'active' },
        { display: 'Pneumonia (disorder)', clinical_status: 'resolved' },
        { display: 'Hypoxemia (disorder)', clinical_status: 'resolved' },
        { display: 'Cough (finding)', clinical_status: 'resolved' },
        { display: 'Viral sinusitis (disorder)', clinical_status: 'resolved' }
      ]),
      labs: query([
        { cite_id: 'q1', category: 'survey', display: 'Are you a refugee', value_text: 'No', effective_at: '2026-09-01' },
        { cite_id: 'q2', category: 'social-history', display: 'Housing status', value_text: 'I have housing', effective_at: '2026-09-01' },
        { cite_id: 's1', category: 'vital-signs', display: 'Oxygen saturation', value_num: 92.19, unit: '%', effective_at: '2026-08-01' },
        { cite_id: 'r1', category: 'vital-signs', display: 'Respiratory rate', value_num: 13, unit: '/min', effective_at: '2026-08-01' },
        { cite_id: 'a1', category: 'laboratory', display: 'Hemoglobin A1c/Hemoglobin.total in Blood', value_num: 6.35, unit: '%', effective_at: '2026-07-01' },
        { cite_id: 'g1', category: 'laboratory', display: 'Glomerular filtration rate/1.73 sq M.predicted', value_num: 13.687, unit: 'mL/min/{1.73_m2}', effective_at: '2026-07-01' }
      ])
    });

    expect(patient.fullName).toBe('Norman Hettinger');
    expect(patient.majorDiagnoses).toEqual([
      'Prediabetes',
      'Pneumonia (resolved)',
      'Hypoxemia (resolved)'
    ]);
    expect(patient.labs.map(lab => lab.label).sort()).toEqual(['HbA1c', 'Oxygen saturation', 'Respiratory rate', 'eGFR']);
    expect(patient.dateOfBirth).toBe('1999-11-25');
    expect(identityLine(patient)).toContain('born 25 Nov 1999');
    expect(patient.labs.find(lab => lab.label === 'eGFR')?.flag).toBe('low');
    expect(patient.riskIndicators.join(' ')).toMatch(/eGFR/);
    expect(briefStatements(patient).join(' ')).toContain('Active conditions: Prediabetes');
    expect(briefStatements(patient).join(' ')).toContain('Latest Oxygen saturation: 92.19 %');
    expect(briefStatements(patient).join(' ')).toContain('Chart for Norman Hettinger');
    expect(briefStatements(patient).join(' ')).not.toMatch(/p_485b|Record p_/);
    expect(briefStatements(patient).join(' ')).not.toMatch(/refugee|unemploy|employment|education|transportation/i);
    expect(snapshotLabGroups(patient.labs).map(group => group.label)).toEqual([
      'eGFR',
      'HbA1c',
      'Oxygen saturation',
      'Respiratory rate'
    ]);
  });

  it('marks a live break-glass identity on the composed chart', () => {
    const patient = composePatient('p_205', {
      patient_key: 'p_205',
      given_name: 'Jonas',
      family_name: 'Weber',
      birth_date: '1989-02-09',
      sex: 'male',
      mrn: 'MRN-4472051',
      purpose_of_event: 'BTG',
      compliance_flag: true,
      audit_id: 'a',
      identity_audit_id: 'b'
    }, {});
    expect(patient.warning).toBe('Break-glass active');
    expect(patient.fullName).toBe('Jonas Weber');
  });
});

describe('sessionCanOpenSignedFiles', () => {
  it('follows the imaging panel and the patient role', () => {
    expect(sessionCanOpenSignedFiles({ role: 'attending', panels: ['imaging', 'notes'] })).toBe(true);
    expect(sessionCanOpenSignedFiles({ role: 'care_team', panels: ['imaging_metadata', 'notes'] })).toBe(false);
    expect(sessionCanOpenSignedFiles({ role: 'patient', panels: ['notes', 'imaging_metadata'] })).toBe(true);
    expect(sessionCanOpenSignedFiles(null)).toBe(false);
  });
});

describe('cleanSyntheaName', () => {
  it('strips the generator digits from Synthea names', () => {
    expect(cleanSyntheaName('Jerold208 Michel472')).toBe('Jerold Michel');
    expect(cleanSyntheaName('Schiller186')).toBe('Schiller');
  });
});

describe('summariesFromKeys', () => {
  it('omits patients without an identity banner', () => {
    const list = summariesFromKeys(['p_101', 'p_103', 'p_205'], [
      {
        patient_key: 'p_101',
        given_name: 'Elisabeth',
        family_name: 'Keller',
        birth_date: '1961-04-17',
        sex: 'female',
        mrn: 'MRN-101',
        purpose_of_event: 'TREAT',
        compliance_flag: false,
        audit_id: 'a',
        identity_audit_id: 'b'
      },
      null,
      null
    ]);
    expect(list.map(patient => patient.id)).toEqual(['p_101']);
    expect(list[0].fullName).toBe('Elisabeth Keller');
  });
});

describe('identity and encounter placement', () => {
  it('shows last ambulatory visit when there is no diet ward', () => {
    const patient = composePatient('p_485ba8c8597d4c5cb0fbda55317119a3', {
      patient_key: 'p_485ba8c8597d4c5cb0fbda55317119a3',
      given_name: 'Norman',
      family_name: 'Hettinger',
      birth_date: '1999-11-25',
      sex: 'male',
      mrn: 'mrn-norman',
      purpose_of_event: 'TREAT',
      compliance_flag: false,
      audit_id: 'a',
      identity_audit_id: 'b'
    }, {
      encounters: query([
        {
          class: 'AMB',
          type_display: 'Encounter for check up (procedure)',
          status: 'finished',
          started_at: '2025-02-13T20:42:12Z'
        }
      ])
    }, {
      notes: {
        patient_key: 'p_485ba8c8597d4c5cb0fbda55317119a3',
        chunks: [{
          patient_key: 'p_485ba8c8597d4c5cb0fbda55317119a3',
          note_id: 'p_485ba8c8597d4c5cb0fbda55317119a3-historical-pneumonia',
          provenance: 'clinical',
          text: 'Prior pneumonia with hypoxemia, now resolved.'
        }],
        notes: [],
        chunk_count: 1,
        obligations: {},
        audit_id: 'n'
      }
    });
    expect(patient.placement).toContain('Last visit');
    expect(patient.placement).toContain('Ambulatory');
    expect(patient.notes[0]).toMatchObject({
      title: 'Historical Pneumonia',
      text: 'Prior pneumonia with hypoxemia, now resolved.'
    });
  });
});

describe('cleanSyntheaNote', () => {
  it('keeps the pneumonia encounter and drops leftover template fragments', () => {
    const cleaned = cleanSyntheaNote(`
      Alex is a 21 year-old nonhispanic white male. Patient has a history of acute bronchitis (disorder),
      severe anxiety (panic) (finding). Patient is presenting with pneumonia (disorder), hypoxemia (disorder).
      Patient has never smoked. Patient identifies as heterosexual.
      The following procedures were conducted: - plain x-ray of chest - oxygen administration by mask.
      The following lab reports were completed: - CBC panel - blood by automated count - CBC auto differential panel - blood
      - Comprehensive metabolic 2000 panel - serum or plasma - Troponin I.cardiac - serum or plasma by high sensitivity method
      The patient was prescribed the following medications: - 0.4 ML Enoxaparin sodium 100 MG/ML Prefilled Syringe.
      No Known Allergies.
    `);
    expect(cleaned.toLowerCase()).toContain('pneumonia');
    expect(cleaned.toLowerCase()).toContain('oxygen by mask');
    expect(cleaned).not.toMatch(/The patient was/i);
    expect(cleaned).not.toMatch(/blood by automated count/i);
    expect(cleaned).not.toMatch(/serum or plasma/i);
  });
});

describe('formatDietOrder', () => {
  it('maps SNOMED diet codes to readable orders', () => {
    expect(formatDietOrder({ ward: 'w_3b', diet_codes: ['160670007', '386619000'] }))
      .toBe('Ward w_3b · diabetic diet · low sodium diet');
  });
});

describe('kitchenCardFromDiet', () => {
  it('builds a tray card without identity or MRN', () => {
    const card = kitchenCardFromDiet('p_101', query([{ ward: 'w_3b', diet_codes: ['160670007'] }]));
    expect(card.fullName).toBe('Ward w_3b');
    expect(card.reason).toBe('diabetic diet');
    expect(card.dateOfBirth).toBe('');
    expect(card.assignedClinician).toBe('');
    expect(card.fullName).not.toMatch(/p_101/);
  });
});
