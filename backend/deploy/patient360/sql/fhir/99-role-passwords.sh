#!/bin/sh
# Gives the application roles LOGIN and a password from the environment.
# Only .sh init scripts can read environment variables; .sql files cannot.
# Runs once with the other initdb files against the empty volume.
set -eu

: "${PATIENT360_APP_PASSWORD:?PATIENT360_APP_PASSWORD must be set for the postgres service}"
: "${PATIENT360_WORKER_PASSWORD:?PATIENT360_WORKER_PASSWORD must be set for the postgres service}"
: "${PATIENT360_AUDITOR_PASSWORD:?PATIENT360_AUDITOR_PASSWORD must be set for the postgres service}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_pw="$PATIENT360_APP_PASSWORD" \
  -v worker_pw="$PATIENT360_WORKER_PASSWORD" \
  -v auditor_pw="$PATIENT360_AUDITOR_PASSWORD" <<'EOF'
ALTER ROLE p360_app     LOGIN PASSWORD :'app_pw';
ALTER ROLE p360_worker  LOGIN PASSWORD :'worker_pw';
ALTER ROLE p360_auditor LOGIN PASSWORD :'auditor_pw';
EOF

echo "patient360 roles p360_app, p360_worker, p360_auditor can log in"
