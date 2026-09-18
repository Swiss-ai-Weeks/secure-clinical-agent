# Shared synthetic ingestion snapshot

The user explicitly requested including `.data` in the `ingestion-pipeline` branch on 2026-09-18. This snapshot includes generated **synthetic** FHIR and raw notes, prepared structured records, the matching opaque identity registry and its backups, adversarial fixtures, and validation evidence. Anyone with repository access can read these files, including their synthetic names and source-to-opaque mappings. They are not real patient records.

The root `.gitignore` permits only the selected directories. Database rebuild backups (`pg-rebuild-*`) remain excluded because the cluster dump contains role password hashes. Runtime locks, SQLite journal files and the PostgreSQL debug log also remain excluded. `.env`, `.secrets` and future unlisted `.data` directories remain ignored. Do not put real patient data, credentials or production database dumps into these tracked directories.

## Using a checkout

Git preserves file contents and executable bits, not owner-only permissions. Before running the adapters, restrict the selected data directories and files on the local checkout:

```bash
python3 - <<'PY'
from pathlib import Path
root = Path('.data')
root.chmod(0o700)
for path in root.rglob('*'):
    if path.is_symlink():
        raise SystemExit('Review unexpected data symlink before using this checkout')
    path.chmod(0o700 if path.is_dir() else 0o600)
PY
```

The SQLite registry is a snapshot, not a database to share concurrently through Git. Preserve its existing identities; do not initialize a new registry for the supplied cohort. Back it up before further ingestion, and coordinate updates rather than merging independently modified SQLite files. The synthetic database-backup files in `identity/` are registry copies; the excluded `pg-rebuild-*` backups are PostgreSQL dumps with different contents and recovery purposes.

A checkout does not populate PostgreSQL or Qdrant. Use the [ingestion runbook](../backend/ingestion/RUNBOOK.md) to validate source and load structured data into an initialized deployment. Raw clinical/evaluation notes remain unsanitized and unpublished; the fixtures do not establish successful security evaluation.

Prepared corpus IDs include code/policy digests. Importing newer `main` code can produce new prepared versions while leaving opaque patient identities unchanged. Older prepared artifacts and validation records are retained as historical evidence. Evidence files may contain paths from the original NVIDIA server; use repository-relative equivalents on a different machine.

The snapshot is approximately 1.1 GiB before Git compression and contains large JSON/SQLite files. It is intentionally tracked as ordinary Git files, with no Git LFS dependency. Source and derived files retain their original bytes so their manifests remain verifiable.
