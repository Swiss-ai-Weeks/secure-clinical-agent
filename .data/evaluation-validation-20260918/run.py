import json,os,subprocess,sys
from pathlib import Path
os.umask(0o077)
sys.path.insert(0,'backend/ingestion')
from worker import inventory,read_json,sha256,write_json
import postgres
root=Path('.data/evaluation-validation-20260918')
batch=Path('.data/ingestion/71289501d068daa74e87a40619e942617c02663b8f675e5231631f50adea9f36')
selection=Path('.data/clinical-demo')/batch.name/'candidate-evidence.json'
steps=[]
for name,extra in [('initial',[]),('replay',[]),('independent',['--output',str(root/'independent')])]:
 result=subprocess.run([sys.executable,'backend/ingestion/evaluation.py',str(batch),'--selection',str(selection),*extra],capture_output=True,text=True,timeout=180)
 if result.returncode:
  print(result.stderr,end='');raise SystemExit(1)
 value=json.loads(result.stdout);steps.append({'step':name,**value})
 write_json(root/'execution.json',{'steps':steps,'status':'in_progress'})
 print(json.dumps({'step':name,**value}),flush=True)
assert steps[0]['corpus']==steps[1]['corpus']
assert inventory(Path(steps[0]['corpus']))==inventory(Path(steps[2]['corpus']))
before=read_json(root/'before.json')
assert before['registry_sha256']==sha256(Path('.data/identity/registry.sqlite'))
for t,expected in before['clinical'].items():
 key='patient_key' if t=='patients' else 'source_id'
 actual=json.loads(postgres.query(f"SELECT json_build_object('count',count(*),'digest',md5(string_agg(to_jsonb(t)::text,'' ORDER BY {key}))) FROM clinical.{t} t;"))
 assert actual==expected
assert int(postgres.query('SELECT count(*) FROM clinical.notes;'))==before['clinical_notes']==0
p=Path(steps[0]['corpus'])/'artifacts'
controls=[json.loads(s) for s in (p/'raw-controls.jsonl').read_text().splitlines()]
variants=[json.loads(s) for s in (p/'raw-variants.jsonl').read_text().splitlines()]
assert len({d['document_key'] for d in controls+variants})==11
for v in variants:
 c=next(c for c in controls if c['source_document_key']==v['source_document_key'])
 assert v['text'].startswith(c['text']) and v['document_key']!=c['document_key']
 assert v['patient_key']==c['patient_key'] and v['encounter_key']==c['encounter_key']
result={'status':'fixture_acceptance_passed','steps':steps,'independent_bytes_identical':True,
        'source_registry_unchanged':True,'clinical_row_snapshots_unchanged':True,'clinical_notes':0,
        'distinct_evaluation_documents':11,'original_clinical_narrative_preserved':True,
        'sanitized':False,'published':False,'security_evaluation':'not_run'}
write_json(root/'execution.json',result)
print(json.dumps({k:v for k,v in result.items() if k!='steps'}),flush=True)
