#!/bin/sh
# Patient360 linkage vault bootstrap (Build Plan §4.5). Runs once per `compose up` with the
# root token and leaves two least-privilege tokens behind:
#
#   p360-backend   read  secret/data/linkage/self/*      resolve_self at login
#                  read  secret/data/linkage/identity/*  identity_banner, break_glass_identity
#   p360-worker    create/update/read secret/data/linkage/*   register (seed_demo.py, worker)
#
# Token ids are fixed from the environment so the backend and the seed can be configured
# without a secret exchange; creating a token with a chosen id needs the root token, which
# only this container holds. Idempotent: policies are rewritten, tokens are created only if
# `bao token lookup` does not find them. OpenBao runs in -dev mode here (unsealed, in-memory),
# so this runs again after every restart; identities are restored by re-running seed_demo.py.
set -eu

: "${BAO_ADDR:?BAO_ADDR must be set}"
: "${BAO_TOKEN:?BAO_TOKEN (root) must be set}"
: "${PATIENT360_LINKAGE_BACKEND_TOKEN:?PATIENT360_LINKAGE_BACKEND_TOKEN must be set}"
: "${PATIENT360_LINKAGE_WORKER_TOKEN:?PATIENT360_LINKAGE_WORKER_TOKEN must be set}"
mount="${PATIENT360_LINKAGE_MOUNT:-secret}"

case "$PATIENT360_LINKAGE_BACKEND_TOKEN$PATIENT360_LINKAGE_WORKER_TOKEN" in
  *.*) echo "openbao-init: token ids must not contain '.'" >&2; exit 1 ;;
esac
if [ "$PATIENT360_LINKAGE_BACKEND_TOKEN" = "$PATIENT360_LINKAGE_WORKER_TOKEN" ] \
   || [ "$PATIENT360_LINKAGE_BACKEND_TOKEN" = "$BAO_TOKEN" ] \
   || [ "$PATIENT360_LINKAGE_WORKER_TOKEN" = "$BAO_TOKEN" ]; then
  echo "openbao-init: backend, worker and root tokens must differ" >&2
  exit 1
fi

i=0
until bao status >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo "openbao-init: openbao not ready at $BAO_ADDR" >&2
    exit 1
  fi
  sleep 2
done

bao policy write p360-backend - <<EOF
# Read-only on the two linkage paths the backend uses. No list, no write, nothing else.
path "${mount}/data/linkage/self/*" {
  capabilities = ["read"]
}
path "${mount}/data/linkage/identity/*" {
  capabilities = ["read"]
}
EOF

bao policy write p360-worker - <<EOF
# register: the ingestion worker and seed_demo.py write linkage records.
path "${mount}/data/linkage/*" {
  capabilities = ["create", "update", "read"]
}
path "${mount}/metadata/linkage/*" {
  capabilities = ["read", "list"]
}
EOF

ensure_token() {
  # $1 token id, $2 policy, $3 display name
  if bao token lookup "$1" >/dev/null 2>&1; then
    echo "openbao-init: token '$3' present"
  else
    bao token create -id="$1" -policy="$2" -orphan -no-default-policy -display-name="$3" >/dev/null
    echo "openbao-init: token '$3' created with policy $2"
  fi
}

ensure_token "$PATIENT360_LINKAGE_BACKEND_TOKEN" p360-backend p360-backend
ensure_token "$PATIENT360_LINKAGE_WORKER_TOKEN" p360-worker p360-worker

# Prove the boundary: the backend token cannot write.
if BAO_TOKEN="$PATIENT360_LINKAGE_BACKEND_TOKEN" bao kv put -mount="$mount" linkage/self/_probe patient_key=p_000 >/dev/null 2>&1; then
  echo "openbao-init: backend token can write linkage/self; policy is wrong" >&2
  exit 1
fi
echo "openbao-init: policies p360-backend, p360-worker applied; backend token is read-only"
