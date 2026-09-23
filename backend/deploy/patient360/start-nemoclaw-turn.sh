#!/usr/bin/env bash
# Host-side NemoClaw adapter for Patient360 Ask. The backend posts to
# http://172.21.0.1:17999 (docker-bridge gateway).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PATH="${HOME}/.local/bin:${PATH}"
export PATIENT360_NEMOCLAW_TURN_HOST="${PATIENT360_NEMOCLAW_TURN_HOST:-0.0.0.0}"
export PATIENT360_NEMOCLAW_TURN_PORT="${PATIENT360_NEMOCLAW_TURN_PORT:-17999}"
LOG="${PATIENT360_NEMOCLAW_TURN_LOG:-${HOME}/.local/state/patient360-nemoclaw-turn.log}"
PIDFILE="${PATIENT360_NEMOCLAW_TURN_PID:-${HOME}/.local/state/patient360-nemoclaw-turn.pid}"
mkdir -p "$(dirname "$LOG")" "$(dirname "$PIDFILE")"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "nemoclaw-turn already running pid=$(cat "$PIDFILE")"
  exit 0
fi

if ss -lptn 2>/dev/null | grep -q ":${PATIENT360_NEMOCLAW_TURN_PORT} "; then
  echo "port ${PATIENT360_NEMOCLAW_TURN_PORT} already listening"
  exit 0
fi

nohup env PYTHONUNBUFFERED=1 python3 "${ROOT}/nemoclaw-turn.py" >>"$LOG" 2>&1 &
echo $! >"$PIDFILE"
echo "nemoclaw-turn started pid=$! log=$LOG"
