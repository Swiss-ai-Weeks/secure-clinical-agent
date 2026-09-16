#!/bin/sh
set -eu
base="http://qdrant:6333"
i=0
until curl -fsS "${base}/readyz" >/dev/null; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo "qdrant not ready" >&2
    exit 1
  fi
  sleep 2
done
curl -fsS -X PUT "${base}/collections/note_chunks" \
  -H "api-key: ${QDRANT__SERVICE__API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"vectors":{"size":2048,"distance":"Cosine"}}'
echo
echo "qdrant collection note_chunks (2048-d) ensured"
