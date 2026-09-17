#!/bin/sh
# Creates the OpenFGA datastore: a separate database `openfga` owned by a separate
# login role `openfga`, in this same Postgres instance. OpenFGA's own tables (tuples,
# authorization models, stores) live there; `openfga migrate` creates them on first
# start, which works because PG16 hands `public` to pg_database_owner.
#
# Isolation is by CONNECT privilege: only `openfga` may connect to `openfga`, and
# 05-grants.sql revokes CONNECT on `fhir` from PUBLIC, so the p360_* roles cannot read
# or edit grants behind the OpenFGA API and `openfga` cannot read clinical data.
#
# Only .sh init scripts can read environment variables; .sql files cannot. Runs once
# with the other initdb files against the empty volume.
set -eu

: "${PATIENT360_OPENFGA_DB_PASSWORD:?PATIENT360_OPENFGA_DB_PASSWORD must be set for the postgres service}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v openfga_pw="$PATIENT360_OPENFGA_DB_PASSWORD" <<'EOF'
CREATE ROLE openfga LOGIN PASSWORD :'openfga_pw';
CREATE DATABASE openfga OWNER openfga;
COMMENT ON DATABASE openfga IS 'OpenFGA datastore: grant tuples and authorization models. Written only through the OpenFGA API, never by p360_* roles.';
REVOKE CONNECT ON DATABASE openfga FROM PUBLIC;
GRANT  CONNECT ON DATABASE openfga TO openfga;
EOF

echo "patient360 openfga datastore: database openfga owned by role openfga"
