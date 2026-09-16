#!/bin/sh
set -eu
base="http://openfga:8080"
auth=""
if [ -n "${PATIENT360_OPENFGA_KEY:-}" ]; then
  auth="Authorization: Bearer ${PATIENT360_OPENFGA_KEY}"
fi
i=0
until wget -q -O /dev/null "${base}/healthz" 2>/dev/null || wget -q -O /dev/null "${base}/stores" 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo "openfga not ready" >&2
    exit 1
  fi
  sleep 2
done
store_json="$(wget -q -O - ${auth:+--header="$auth"} --post-data='{"name":"patient360-grants"}' --header='Content-Type: application/json' "${base}/stores" || true)"
echo "$store_json"
echo "openfga store create attempted"
