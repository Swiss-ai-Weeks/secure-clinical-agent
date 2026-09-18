import base64
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import sys

os.umask(0o077)
ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/'backend/ingestion'))
import postgres
from worker import sha256

OUT=ROOT/'.data/structured-acceptance-20260918'
BATCH=ROOT/'.data/ingestion/71289501d068daa74e87a40619e942617c02663b8f675e5231631f50adea9f36'
evidence=json.loads((ROOT/'.data/clinical-demo'/BATCH.name/'candidate-evidence.json').read_text())
registry=sqlite3.connect(ROOT/'.data/identity/registry.sqlite')

def key(kind, value):
    return value if value.startswith(kind+'/') else kind+'/'+value

def mapping(source):
    result=registry.execute('SELECT opaque FROM identities WHERE source=?',(source,)).fetchone()
    assert result
    return result[0]

def row(table, source):
    result=postgres.query('SELECT row_to_json(t) FROM clinical.'+table+' t WHERE source_id='+postgres.literal(source)+';')
    assert result
    return json.loads(result)

results=[]
for c in evidence['candidates']:
    path=ROOT/c['bundle']
    if not path.exists(): path=BATCH/c['bundle']
    assert sha256(path)==c['bundle_sha256']
    bundle=json.loads(path.read_text())
    resources={key(e['resource']['resourceType'],e['resource']['id']):e['resource'] for e in bundle['entry']}
    patient=mapping(key('Patient',c['source_patient_id']))
    enc_source=key('Encounter',c['encounter']['resource_id'])
    encounter=mapping(enc_source)
    actual_encounter=row('encounters',enc_source)
    assert actual_encounter['id']==encounter and actual_encounter['patient_key']==patient
    doc_source=key('DocumentReference',c['document']['resource_id'])
    assert registry.execute('SELECT 1 FROM resource_links WHERE batch=? AND source=? AND relation=? AND target=?',
                            (BATCH.name,doc_source,'encounter',enc_source)).fetchone()
    document=resources[doc_source]
    note=base64.b64decode(document['content'][0]['attachment']['data']).decode()
    assert all(x['text'] in note for x in c['clinical_note_excerpts'])
    condition_status=[]
    for expected in c['conditions']:
        source=key('Condition',expected['resource_id'])
        actual=row('conditions',source)
        assert actual['patient_key']==patient and actual['encounter_id']==encounter
        assert actual['id']==mapping(source)
        coding=expected['code']['coding'][0]
        assert (actual['code_system'],actual['code'])==(coding['system'],coding['code'])
        status=expected['clinical_status']['coding'][0]['code']
        assert actual['clinical_status']==status
        condition_status.append(status)
    measurements=[]
    for expected in c['observations']:
        source=key('Observation',expected['resource_id'])
        original=resources[source]
        parent=row('observations',source)
        assert parent['patient_key']==patient and parent['encounter_id']==encounter
        assert datetime.fromisoformat(parent['effective_at'])==datetime.fromisoformat(expected['effectiveDateTime'])
        assert parent['id']==mapping(source)
        assert [(x['system'],x['code']) for x in parent['resource']['code']['coding']]==[(x['system'],x['code']) for x in expected['code']['coding']]
        parts=expected.get('component',[expected])
        source_parts=original.get('component',[original])
        for e in parts:
            coding=e['code']['coding'][0]
            original_part=next(p for p in source_parts if p['code']['coding'][0]['code']==coding['code'])
            q=e['valueQuantity']
            assert original_part['valueQuantity']==q
            actual=row('observations',source+'#'+coding['code']) if 'component' in expected else parent
            assert actual['patient_key']==patient and actual['encounter_id']==encounter
            assert actual['code_system']==coding['system'] and actual['code']==coding['code']
            assert actual['value_num']==q['value'] and actual['unit']==q['code']
            assert datetime.fromisoformat(actual['effective_at'])==datetime.fromisoformat(expected['effectiveDateTime'])
            if 'component' in expected: assert actual['parent_id']==parent['id']
            measurements.append({'code':actual['code'],'value':actual['value_num'],'unit':actual['unit']})
    results.append({'example':c['alias'],'conditions':condition_status,'measurements':measurements,
                    'patient_encounter_and_document_links':'verified','source_bundle_hash':'verified',
                    'note':'raw source lineage only; not sanitized or loaded'})
registry.close()
(OUT/'clinical-examples.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
