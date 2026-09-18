"""Atomic structured imports through psql using the existing worker role."""

import json
import subprocess

from worker import BatchError, canonical

TABLES = ("patients", "encounters", "conditions", "observations")


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def query(sql, container="patient360-postgres"):
    # Password stays inside the container environment; no credentials or source SQL
    # appear in command arguments or diagnostics. -X excludes operator psqlrc files.
    command = ["docker", "exec", "-i", container, "sh", "-c",
               'PGPASSWORD="$PATIENT360_WORKER_PASSWORD" exec psql -X -qAt '
               '-v ON_ERROR_STOP=1 -h 127.0.0.1 -U p360_worker -d fhir']
    try:
        result = subprocess.run(command, input=sql, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BatchError("postgres_unavailable") from error
    if result.returncode:
        # PostgreSQL errors can contain the offending full row; never echo them.
        raise BatchError("postgres_transaction_rejected")
    return result.stdout.strip()


def load(rows, manifest, container="patient360-postgres", dry_run=False):
    sql = ["BEGIN; SET LOCAL timezone='UTC'; SET LOCAL standard_conforming_strings=on;",
           "SET LOCAL lock_timeout='10s'; SET LOCAL statement_timeout='120s';",
           "SELECT pg_advisory_xact_lock(7360360);"]
    for table in TABLES:
        data = rows[table]
        if not data:
            raise BatchError("empty_projection_table")
        columns = sorted(data[0])
        if any(sorted(row) != columns for row in data):
            raise BatchError("inconsistent_projection_columns")
        quoted = ",".join('"' + col + '"' for col in columns)
        sql.append(f"CREATE TEMP TABLE stage_{table} ON COMMIT DROP AS SELECT {quoted} "
                   f"FROM jsonb_populate_recordset(NULL::clinical.{table}, "
                   f"{literal(canonical(data).decode())}::jsonb);")
        # EXISTS favours a cheap-start nested-loop plan. Without an indexed,
        # analysed stage it can scan all 70k rows for every stored observation.
        key = "patient_key" if table == "patients" else "source_id"
        sql.append(f"CREATE UNIQUE INDEX ON stage_{table} ({key}); ANALYZE stage_{table};")
    # Treat each included patient's bundle as a full snapshot. Patients absent
    # from this batch are untouched (in particular seed -> smoke replay).
    for table in TABLES[1:]:
        sql.append(f"""
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM clinical.{table} t JOIN stage_patients p USING(patient_key)
            LEFT JOIN stage_{table} s ON s.source_id=t.source_id WHERE s.source_id IS NULL)
 THEN RAISE EXCEPTION 'source_removal_requires_policy'; END IF;
 IF EXISTS (SELECT 1 FROM clinical.{table} t JOIN stage_{table} s USING(source_id)
            WHERE (t.id,t.patient_key,t.cite_id) IS DISTINCT FROM (s.id,s.patient_key,s.cite_id))
 THEN RAISE EXCEPTION 'registry_or_ownership_mismatch'; END IF;
END $$;
""")
    for table in TABLES:
        columns = sorted(rows[table][0])
        key = "patient_key" if table == "patients" else "source_id"
        mutable = [c for c in columns if c not in {key, "id", "cite_id", "patient_key"}]
        quoted = ",".join('"' + c + '"' for c in columns)
        assignments = ",".join(f'"{c}"=EXCLUDED."{c}"' for c in mutable)
        old = ",".join(f't."{c}"' for c in mutable)
        new = ",".join(f'EXCLUDED."{c}"' for c in mutable)
        sql.append(f"""WITH changed AS (
 INSERT INTO clinical.{table} AS t ({quoted}) SELECT {quoted} FROM stage_{table}
 ON CONFLICT ({key}) DO UPDATE SET {assignments}
 WHERE ROW({old}) IS DISTINCT FROM ROW({new}) RETURNING 1)
 SELECT json_build_object('table','{table}','changed',count(*)) FROM changed;
""")
    # Check every projected field after the upsert, including numeric values,
    # opaque keys, codes, units, timestamps and parent/encounter relationships.
    for table in TABLES:
        columns = sorted(rows[table][0])
        key = "patient_key" if table == "patients" else "source_id"
        compare = " OR ".join(f't."{c}" IS DISTINCT FROM s."{c}"' for c in columns)
        sql.append(f"""DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM stage_{table} s LEFT JOIN clinical.{table} t USING({key})
 WHERE t.{key} IS NULL OR {compare}) THEN RAISE EXCEPTION 'projection_mismatch'; END IF;
END $$;""")
    detail = {k: manifest[k] for k in ("batch_id", "policy", "counts", "source_contract", "skipped")}
    sql.append("INSERT INTO audit.audit_events(event_type,agent_software,outcome,detail) VALUES "
               f"('ingest','structured-ingest-worker','0',{literal(canonical(detail).decode())}::jsonb);")
    sql.append("ROLLBACK;" if dry_run else "COMMIT;")
    output = query("\n".join(sql), container)
    changes = {}
    for line in output.splitlines():
        if line.startswith("{"):
            item = json.loads(line)
            changes[item["table"]] = item["changed"]
    if set(changes) != set(TABLES):
        raise BatchError("postgres_result_incomplete")
    return {"changed": changes, "verified_all_projected_fields": True, "rolled_back": dry_run}
