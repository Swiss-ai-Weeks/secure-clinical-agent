#!/usr/bin/env bash
set -euo pipefail

IMAGE="${OHIF_IMAGE:-ohif/app:v3.11.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PUBLIC="$ROOT/public"
CONFIG="$ROOT/ohif/app-config.js"
TMP="$(mktemp -d)"
CID=""

cleanup() {
  if [[ -n "$CID" ]]; then
    docker rm -f "$CID" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT

if [[ ! -f "$CONFIG" ]]; then
  echo "missing $CONFIG" >&2
  exit 1
fi

docker pull "$IMAGE"
CID="$(docker create "$IMAGE")"
mkdir -p "$TMP/html"
if ! docker cp "$CID:/usr/share/nginx/html/." "$TMP/html/"; then
  echo "OHIF image has no /usr/share/nginx/html" >&2
  exit 1
fi

mkdir -p "$PUBLIC"
find "$PUBLIC" -mindepth 1 -maxdepth 1 ! -name .gitkeep -exec rm -rf {} +
cp -a "$TMP/html/." "$PUBLIC/"
mkdir -p "$PUBLIC/ohif"

python3 - "$PUBLIC" "$CONFIG" <<'PY'
import gzip
import pathlib
import re
import sys

public = pathlib.Path(sys.argv[1])
config = pathlib.Path(sys.argv[2]).read_text()
for gz in public.rglob("*.gz"):
    dest = gz.with_suffix("")
    if dest.exists() and dest.stat().st_size > 0:
        continue
    dest.write_bytes(gzip.decompress(gz.read_bytes()))
index = public / "index.html"
if not index.exists():
    raise SystemExit("OHIF image did not contain index.html")
html = index.read_text()
html = re.sub(
    r'<script[^>]+src="/init-service-worker\.js"[^>]*>\s*</script>',
    "",
    html,
    flags=re.I,
)
html = re.sub(
    r"<script[^>]*>\s*if\s*\(\s*['\"]serviceWorker['\"].*?</script>",
    "",
    html,
    flags=re.I | re.S,
)
dest = public / "ohif" / "index.html"
dest.write_text(html)
index.unlink()
for name in ("sw.js", "service-worker.js", "init-service-worker.js"):
    path = public / name
    if path.exists():
        path.unlink()
(public / "app-config.js").write_text(config)
(public / "ohif" / "app-config.js").write_text(config)
print(f"wrote {dest}")
PY
