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

ensure_collection() {
  name="$1"
  existing="$(curl -sS -H "api-key: ${QDRANT__SERVICE__API_KEY}" "${base}/collections/${name}" || true)"
  if echo "${existing}" | grep -q '"status":"ok"'; then
    size="$(echo "${existing}" | sed -n 's/.*"size":\([0-9][0-9]*\).*/\1/p' | head -n 1)"
    if [ -n "${size}" ] && [ "${size}" != "2048" ]; then
      echo "qdrant collection ${name} has incompatible size ${size}" >&2
      exit 1
    fi
  else
    curl -fsS -X PUT "${base}/collections/${name}" \
      -H "api-key: ${QDRANT__SERVICE__API_KEY}" \
      -H "Content-Type: application/json" \
      -d '{"vectors":{"size":2048,"distance":"Cosine"}}'
    echo
  fi
  for field in patient_key confidentiality published; do
    curl -fsS -X PUT "${base}/collections/${name}/index" \
      -H "api-key: ${QDRANT__SERVICE__API_KEY}" \
      -H "Content-Type: application/json" \
      -d "{\"field_name\":\"${field}\",\"field_schema\":\"keyword\"}" >/dev/null
  done
}

ensure_collection note_chunks
ensure_collection note_chunks_eval
echo "qdrant collections note_chunks and note_chunks_eval (2048-d) ensured"
