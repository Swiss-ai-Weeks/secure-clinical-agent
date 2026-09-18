#!/bin/sh
# Loads the Patient360 grant store from stores/openfga/store.fga.yaml (model.fga +
# tuples.demo.yaml) into the OpenFGA store named $OPENFGA_STORE_NAME.
#
# Idempotent: the store is looked up by name and reused; tuples already present are
# ignored (file-import default); each run writes one new immutable model version, which
# the backend pins at startup and stamps into audit rows as policy_version.
# More than one store with the same name is a hard error, never a guess.
#
# Env (set by compose): FGA_API_URL, FGA_API_TOKEN, OPENFGA_STORE_NAME, OPENFGA_STORE_FILE.
set -eu

: "${FGA_API_URL:?FGA_API_URL must be set}"
: "${FGA_API_TOKEN:?FGA_API_TOKEN must be set}"
store_name="${OPENFGA_STORE_NAME:-patient360-grants}"
store_file="${OPENFGA_STORE_FILE:-/openfga/store.fga.yaml}"

[ -r "$store_file" ] || { echo "openfga-init: store file not readable: $store_file" >&2; exit 1; }

i=0
until fga store list >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo "openfga-init: openfga not ready at $FGA_API_URL" >&2
    exit 1
  fi
  sleep 2
done

find_store_ids() {
  # Exact-name match in jq; the CLI (v0.7.x) has no server-side name filter.
  fga store list | jq -r --arg n "$store_name" '.stores[] | select(.name == $n) | .id'
}

store_ids="$(find_store_ids)"
count="$(printf '%s' "$store_ids" | grep -c . || true)"

if [ "$count" -gt 1 ]; then
  echo "openfga-init: $count stores named '$store_name'; refusing to guess:" >&2
  echo "$store_ids" >&2
  exit 1
fi

if [ "$count" -eq 1 ]; then
  store_id="$store_ids"
  echo "openfga-init: importing into existing store $store_id ($store_name)"
  fga store import --file "$store_file" --store-id "$store_id" >/dev/null
else
  echo "openfga-init: creating store '$store_name' from $store_file"
  fga store import --file "$store_file" >/dev/null
  store_id="$(find_store_ids)"
fi

model_id="$(fga model list --store-id "$store_id" | jq -r '.authorization_models[0].id')"
tuple_count="$(fga tuple read --store-id "$store_id" --max-pages 0 | jq '.tuples | length')"

echo "openfga-init: store_id=$store_id model_id=$model_id tuples=$tuple_count"
