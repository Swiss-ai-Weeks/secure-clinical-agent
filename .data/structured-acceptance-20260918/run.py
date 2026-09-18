import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

os.umask(0o077)
ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'backend/ingestion'))
import postgres
from worker import canonical, sha256

OUT = ROOT / '.data/structured-acceptance-20260918'
SMOKE = 'fb8bc7f697698fe7a37ca1a0a37a08e9d9ff12409c71bdaea8cf9f8888c960e4'
SEED = '71289501d068daa74e87a40619e942617c02663b8f675e5231631f50adea9f36'
EXPECTED_SMOKE = dict(patients=10, encounters=500, conditions=388, observations=8914)
EXPECTED_SEED = dict(patients=100, encounters=4645, conditions=3579, observations=70843)
record_path = OUT / 'execution.json'
record = json.loads(record_path.read_text()) if record_path.exists() else {'started':datetime.now(timezone.utc).isoformat(),'steps':[]}

def save():
    record_path.write_text(json.dumps(record,indent=2)+'\n')

def load(batch, label):
    result = subprocess.run([sys.executable, 'backend/ingestion/structured.py', 'load', '.data/ingestion/'+batch],
                            capture_output=True,text=True,timeout=300)
    if result.returncode:
        record['steps'].append({'step':label,'error':json.loads(result.stderr)}); save()
        raise RuntimeError('load failed; see restricted execution record')
    info=json.loads(result.stdout)
    assert info['status']=='structured_loaded' and not info['rolled_back']
    record['steps'].append({'step':label, **info}); save()
    print(json.dumps({'step':label,'counts':info['counts'],'changed':info['changed']}),flush=True)
    return info

def snapshot(where=''):
    result={}
    for table in postgres.TABLES:
        key='patient_key' if table=='patients' else 'source_id'
        sql=f"SELECT json_build_object('count',count(*),'digest',md5(string_agg(to_jsonb(t)::text,'' ORDER BY {key}))) FROM clinical.{table} t {where};"
        result[table]=json.loads(postgres.query(sql))
    return result

def relationships():
    sql="""SELECT json_build_object(
    'condition_encounter_mismatches',(SELECT count(*) FROM clinical.conditions c LEFT JOIN clinical.encounters e ON c.encounter_id=e.id WHERE c.encounter_id IS NOT NULL AND (e.id IS NULL OR c.patient_key<>e.patient_key)),
    'observation_encounter_mismatches',(SELECT count(*) FROM clinical.observations o LEFT JOIN clinical.encounters e ON o.encounter_id=e.id WHERE o.encounter_id IS NOT NULL AND (e.id IS NULL OR o.patient_key<>e.patient_key)),
    'component_parent_mismatches',(SELECT count(*) FROM clinical.observations o LEFT JOIN clinical.observations p ON o.parent_id=p.id WHERE o.parent_id IS NOT NULL AND (p.id IS NULL OR o.patient_key<>p.patient_key OR o.encounter_id IS DISTINCT FROM p.encounter_id)),
    'excluded_observation_codes',(SELECT count(*) FROM clinical.observations WHERE code_system='http://loinc.org' AND code IN ('56799-0','32624-9','56051-6','54899-0')),
    'notes',(SELECT count(*) FROM clinical.notes));"""
    checks=json.loads(postgres.query(sql))
    assert all(v==0 for v in checks.values()), checks
    return checks

phase=sys.argv[1]
if phase=='smoke':
    first=load(SMOKE,'smoke_initial')
    assert first['counts']==EXPECTED_SMOKE and first['changed']==EXPECTED_SMOKE
    before=snapshot()
    assert {k:v['count'] for k,v in before.items()}==EXPECTED_SMOKE
    replay=load(SMOKE,'smoke_replay')
    assert all(v==0 for v in replay['changed'].values())
    assert snapshot()==before
    record['smoke_snapshot']=before
    record['smoke_relationships']=relationships()
    record['smoke_prepared']=first['prepared']
    save()
elif phase in ('seed','seed-replay'):
    assert record.get('smoke_snapshot') and record.get('smoke_relationships')
    first=load(SEED,'seed_initial') if phase=='seed' else next(s for s in record['steps'] if s['step']=='seed_initial')
    assert first['counts']==EXPECTED_SEED
    assert first['changed']=={k:EXPECTED_SEED[k]-EXPECTED_SMOKE[k] for k in EXPECTED_SEED}
    before=snapshot()
    assert {k:v['count'] for k,v in before.items()}==EXPECTED_SEED
    replay=load(SEED,'seed_replay')
    assert all(v==0 for v in replay['changed'].values())
    assert snapshot()==before
    smoke=load(SMOKE,'smoke_after_seed')
    assert all(v==0 for v in smoke['changed'].values())
    assert snapshot()==before
    patient_rows=json.loads((Path(record['smoke_prepared'])/'artifacts/patients.json').read_text())
    where='WHERE patient_key IN ('+','.join(postgres.literal(p['patient_key']) for p in patient_rows)+')'
    assert snapshot(where)==record['smoke_snapshot']
    record['seed_snapshot']=before
    record['seed_relationships']=relationships()
    record['seed_prepared']=replay['prepared']
    record['smoke_identities_citations_and_timestamps_preserved']=True
    save()
else:
    raise RuntimeError('unknown phase')
print(json.dumps({'phase':phase,'checks':'passed'}),flush=True)
