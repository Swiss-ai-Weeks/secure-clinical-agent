"""Real local source/registry boundary tests for isolated evaluation artifacts."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evaluation
from identity import Registry
from worker import BatchError, canonical, extract_bundle, inspect_source, inventory, sha256, write_json, batch_id
from test_structured import fixture


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.batch = self.root / 'source'
        self.fhir = self.batch / 'artifacts/source/fhir'
        self.fhir.mkdir(parents=True)
        self.registry_path = self.root / 'identity/registry.sqlite'
        self.registry = Registry.initialize(self.registry_path)
        self.addCleanup(self.registry.close)
        self.selection = self.root / 'selection.json'
        self.output = self.root / 'evaluation'
        self.contract = {'population': 3}
        self.batch_id = batch_id(self.contract)
        candidates=[]
        for i,alias in enumerate(evaluation.SOURCES):
            bundle=fixture()
            for entry in bundle['entry']:
                r=entry['resource']
                r['id'] += str(i)
                entry['fullUrl']='urn:uuid:'+r['id']
                if 'subject' in r: r['subject']={'reference':f'urn:uuid:p{i}'}
                if 'encounter' in r: r['encounter']={'reference':f'urn:uuid:e{i}'}
                if r['resourceType']=='DocumentReference':
                    r['context']={'encounter':[{'reference':f'urn:uuid:e{i}'}]}
                    r['status']='superseded' if i==0 else 'current'
                    r['date']='2026-01-01T01:00:00Z'
            path=self.fhir/f'{i}.json'
            write_json(path,bundle)
            patient,_,notes=extract_bundle(bundle)
            for kind,identifier in [('Patient',f'p{i}'),('Encounter',f'e{i}'),('DocumentReference',f'd{i}')]:
                self.registry.allocate(f'{kind}/{identifier}',patient)
            self.registry.link(self.batch_id,f'DocumentReference/d{i}','encounter',f'Encounter/e{i}')
            candidates.append({'alias':alias,'source_patient_id':patient,
                'encounter':{'resource_id':f'Encounter/e{i}'},
                'document':{'resource_id':f'DocumentReference/d{i}'},
                'bundle_sha256':sha256(path),'note_sha256':evaluation.digest(notes[0]['text'])})
        self.registry.db.commit()
        counts,notes=inspect_source(self.batch/'artifacts/source',3)
        (self.batch/'artifacts/raw-notes.jsonl').write_bytes(b''.join(canonical(n)+b'\n' for n in notes))
        self.manifest={'schema_version':1,'status':'source_ready','synthetic':True,'sanitized':False,
                       'published':False,'batch_id':self.batch_id,'contract':self.contract,'counts':counts,
                       'artifacts':inventory(self.batch/'artifacts')}
        write_json(self.batch/'manifest.json',self.manifest)
        self.evidence={'status':'approved_demonstration_examples','batch_id':self.batch_id,
                       'source_manifest_sha256':sha256(self.batch/'manifest.json'),
                       'raw_notes_sha256':sha256(self.batch/'artifacts/raw-notes.jsonl'),'candidates':candidates}
        write_json(self.selection,self.evidence)

    def build(self, output=None):
        return evaluation.build(self.batch,self.selection,self.registry_path,output or self.output)

    def test_eight_variants_controls_and_reproducible_read_only_build(self):
        source_before=inventory(self.batch)
        registry_before=sha256(self.registry_path)
        one=self.build()
        self.assertEqual(one['counts'],{'controls':3,'variants':8,'cases':8})
        self.assertFalse(one['sanitized'])
        self.assertEqual(one['security_evaluation'],'not_run')
        self.assertEqual(one,self.build())
        other=self.build(self.root/'independent')
        self.assertEqual(inventory(Path(one['corpus'])),inventory(Path(other['corpus'])))
        self.assertEqual(inventory(self.batch),source_before)
        self.assertEqual(sha256(self.registry_path),registry_before)
        root=Path(one['corpus'])/'artifacts'
        controls=[json.loads(s) for s in (root/'raw-controls.jsonl').read_text().splitlines()]
        variants=[json.loads(s) for s in (root/'raw-variants.jsonl').read_text().splitlines()]
        self.assertEqual(len({d['document_key'] for d in controls+variants}),11)
        for v in variants:
            c=next(c for c in controls if c['source_alias']==v['source_alias'])
            self.assertTrue(v['text'].startswith(c['text']+evaluation.SEPARATOR))
            self.assertEqual(v['text'][:v['attack_start']-len(evaluation.SEPARATOR)],c['text'])
            self.assertEqual(evaluation.digest(v['text'][v['attack_start']:]),v['attack_sha256'])
            self.assertEqual(v['patient_key'],c['patient_key'])
            self.assertNotEqual(v['document_key'],v['source_document_key'])
            self.assertTrue(v['evaluation_only'])
            self.assertEqual(v['source_status'],c['source_status'])
            self.assertFalse(v['published'])
        cases=json.loads((root/'cases.json').read_text())
        self.assertTrue(all(c['execution_status']=='not_run' for c in cases))
        access=next(c for c in cases if c['case_id']=='access-other-patient')
        self.assertNotEqual(access['source_patient_key'],access['unauthorized_target_patient_key'])
        self.assertEqual(controls[0]['source_status'],'superseded')
        for path in Path(one['corpus']).rglob('*'):
            self.assertEqual(path.stat().st_mode & 0o077,0)

    def test_source_corruption_rejected(self):
        (self.fhir/'0.json').write_text('{}')
        with self.assertRaisesRegex(BatchError,'artifact_integrity_failure'): self.build()
        self.assertFalse(self.output.exists())

    def test_selection_wrong_batch_or_unapproved_rejected(self):
        for field,value in [('batch_id','wrong'),('status','candidate')]:
            e=copy.deepcopy(self.evidence); e[field]=value; write_json(self.selection,e)
            with self.assertRaisesRegex(BatchError,'selection_not_approved'): self.build()

    def test_selection_wrong_patient_encounter_or_content_rejected(self):
        for change in ('patient','encounter','hash'):
            e=copy.deepcopy(self.evidence)
            if change=='patient': e['candidates'][0]['source_patient_id']='Patient/p1'
            elif change=='encounter': e['candidates'][0]['encounter']['resource_id']='Encounter/e1'
            else: e['candidates'][0]['note_sha256']='wrong'
            write_json(self.selection,e)
            with self.assertRaises(BatchError): self.build()
        self.assertFalse(self.output.exists())

    def test_missing_or_wrong_registry_mapping_fails_without_allocating(self):
        self.registry.db.execute("DELETE FROM identities WHERE source='DocumentReference/d0'")
        self.registry.db.commit()
        before=sha256(self.registry_path)
        with self.assertRaisesRegex(BatchError,'registry_lineage_mismatch'): self.build()
        self.assertEqual(before,sha256(self.registry_path))

    def test_missing_document_encounter_link_rejected(self):
        self.registry.db.execute('DELETE FROM resource_links');self.registry.db.commit()
        with self.assertRaisesRegex(BatchError,'registry_document_link_missing'): self.build()

    def test_corrupt_completed_corpus_not_overwritten(self):
        result=self.build()
        path=Path(result['corpus'])/'artifacts/raw-variants.jsonl'
        path.write_text('CANARY corrupt artifact')
        with self.assertRaisesRegex(BatchError,'evaluation_artifact_corrupt'): self.build()
        self.assertEqual(path.read_text(),'CANARY corrupt artifact')

    def test_output_cannot_overlap_source_or_identity_or_parent(self):
        for output in (self.batch,self.fhir,self.registry_path.parent,self.root):
            with self.subTest(output=output):
                with self.assertRaisesRegex(BatchError,'evaluation_output_must_be_isolated'): self.build(output)

    def test_source_worker_rejects_evaluation_as_clinical_batch(self):
        from worker import verify_batch
        result=self.build()
        with self.assertRaisesRegex(BatchError,'batch_not_source_ready'):
            verify_batch(Path(result['corpus']))


if __name__=='__main__': unittest.main()
