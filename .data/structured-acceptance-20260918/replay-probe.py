import sys,time
sys.path.insert(0,'backend/ingestion')
import postgres
from worker import BatchError
sql='''BEGIN; SET LOCAL statement_timeout='2s';
CREATE TEMP TABLE stage_patients ON COMMIT DROP AS SELECT patient_key FROM clinical.patients;
CREATE TEMP TABLE stage_observations ON COMMIT DROP AS SELECT source_id FROM clinical.observations;
CREATE UNIQUE INDEX ON stage_patients (patient_key); ANALYZE stage_patients;
CREATE UNIQUE INDEX ON stage_observations (source_id); ANALYZE stage_observations;
SELECT EXISTS (SELECT 1 FROM clinical.observations t JOIN stage_patients p USING(patient_key)
 LEFT JOIN stage_observations s ON s.source_id=t.source_id WHERE s.source_id IS NULL);
ROLLBACK;'''
start=time.monotonic()
try:
 assert postgres.query(sql)=='f'
 print('PASS',round(time.monotonic()-start,3))
except BatchError:
 print('FAIL: replay existence check exceeds two-second limit',round(time.monotonic()-start,3))
 sys.exit(1)
