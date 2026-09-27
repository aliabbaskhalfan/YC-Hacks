#!/usr/bin/env bash
# Triggered by the Run button. Starts every dev server this workspace has
# code for, each pinned to this workspace's reserved port so parallel
# workspaces never collide (docs.superset.sh/ports). Restartable: Superset
# reruns this whole script, so it must tear down its own children first.
set -uo pipefail

SUPERSET_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SUPERSET_SCRIPT_DIR/lib/common.sh"
resolve_superset_env
cd "$SUPERSET_WORKSPACE_PATH"

load_ports
log "ports: web=$WEB_PORT api=$API_PORT sim=$SIM_PORT"

pids=()
cleanup() {
  trap - INT TERM EXIT
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

started_any=0

# ---- web (Vite/React/Three.js) ---------------------------------------------
if [ -f web/package.json ]; then
  # Vite only exposes import.meta.env.VITE_* vars it loads itself (from an
  # actual .env file) — a custom `define` targeting that namespace is
  # silently overridden by Vite's own per-module injection in dev mode.
  cat > web/.env.local <<EOF
VITE_API_PORT=$API_PORT
VITE_SIM_PORT=$SIM_PORT
EOF
  pm="$(cd web && detect_node_pm)"
  dev_cmd="$(node_dev_cmd "$pm")"
  log "web: $dev_cmd --port $WEB_PORT"
  ( cd web && eval "$dev_cmd -- --port $WEB_PORT --strictPort" ) &
  pids+=($!)
  started_any=1
else
  skip "web: no web/package.json yet"
fi

# ---- backend (FastAPI) ------------------------------------------------------
if [ -f server/main.py ]; then
  [ -f .venv/bin/activate ] && source .venv/bin/activate
  log "api: uvicorn server.main:app --port $API_PORT"
  uvicorn server.main:app --host 0.0.0.0 --port "$API_PORT" --reload &
  pids+=($!)
  started_any=1
else
  skip "api: no server/main.py yet"
fi

# ---- sim WS server -----------------------------------------------------------
if [ -f sim/sim_server.py ]; then
  [ -f .venv/bin/activate ] && source .venv/bin/activate
  log "sim: python sim/sim_server.py --port $SIM_PORT"
  "$(python_bin)" sim/sim_server.py --port "$SIM_PORT" &
  pids+=($!)
  started_any=1
else
  skip "sim: no sim/sim_server.py yet"
fi

if [ "$started_any" -eq 0 ]; then
  warn "nothing to run yet — no web/package.json, server/main.py, or sim/sim_server.py"
  exit 0
fi

wait
