#!/usr/bin/env bash
# Runs once when a new Superset workspace is created (and again if you re-run
# it by hand). Must stay idempotent and fast: it only installs dependencies,
# mirrors untracked env files from the root checkout, and reserves this
# workspace's port block. It never starts a long-running process — that's
# `run.sh`'s job — so `teardown.sh` only has the port reservation to release.
set -uo pipefail

SUPERSET_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SUPERSET_SCRIPT_DIR/lib/common.sh"
resolve_superset_env
cd "$SUPERSET_WORKSPACE_PATH"

log "workspace: $SUPERSET_WORKSPACE_NAME  ($SUPERSET_WORKSPACE_PATH)"

# ---------------------------------------------------------------------------- #
# 1. Untracked env files, mirrored from the root checkout ($SUPERSET_ROOT_PATH
#    is never a secret store to write to — only ever read from here).
# ---------------------------------------------------------------------------- #

if is_root_checkout; then
  skip "env files: this is the root checkout, nothing to mirror"
else
  copied=0
  shopt -s nullglob dotglob
  for src in "$SUPERSET_ROOT_PATH"/.env "$SUPERSET_ROOT_PATH"/.env.*; do
    name="$(basename "$src")"
    [ "$name" = ".env.example" ] && continue   # tracked; already in every workspace
    [ -f "$src" ] || continue
    cp -n "$src" "$SUPERSET_WORKSPACE_PATH/$name" && copied=$((copied + 1))
  done
  shopt -u nullglob dotglob
  if [ "$copied" -gt 0 ]; then
    ok "env files: copied $copied from root checkout"
  else
    warn "env files: none found in $SUPERSET_ROOT_PATH (copy .env.example to .env there first)"
  fi
fi

# ---------------------------------------------------------------------------- #
# 2. Python deps (sim/ + server/): one venv at the workspace root.
# ---------------------------------------------------------------------------- #

PY_REQ_FILES=(requirements.txt sim/requirements.txt server/requirements.txt)
py_reqs_found=()
for f in "${PY_REQ_FILES[@]}"; do
  [ -f "$f" ] && py_reqs_found+=("$f")
done

if [ ${#py_reqs_found[@]} -gt 0 ] || [ -f pyproject.toml ]; then
  have python3 || die "python3 not found on this machine"
  if [ ! -d .venv ]; then
    log "python: creating .venv"
    python3 -m venv .venv
  else
    skip "python: reusing .venv"
  fi
  # shellcheck source=/dev/null
  source .venv/bin/activate
  pip install --quiet --upgrade pip

  for f in "${py_reqs_found[@]}"; do
    log "python: pip install -r $f"
    pip install --quiet -r "$f" || die "pip install -r $f failed"
  done
  if [ -f pyproject.toml ]; then
    log "python: pip install -e ."
    pip install --quiet -e . || die "pip install -e . failed"
  fi
  deactivate
  ok "python deps installed"
else
  skip "python deps: no requirements.txt / pyproject.toml yet"
fi

# ---------------------------------------------------------------------------- #
# 3. Node deps (web/): lockfile picks the package manager.
# ---------------------------------------------------------------------------- #

if [ -f web/package.json ]; then
  pm="$(cd web && detect_node_pm)"
  install_cmd="$(node_install_cmd "$pm")"
  if [ -n "$install_cmd" ]; then
    have "$pm" || die "web/ needs '$pm' but it is not installed"
    log "web: $install_cmd"
    ( cd web && eval "$install_cmd" ) || die "web dependency install failed"
    ok "web deps installed ($pm)"
  fi
else
  skip "web deps: no web/package.json yet"
fi

# ---------------------------------------------------------------------------- #
# 4. Port block, so this workspace never collides with a sibling running the
#    same dev servers. See BUILD_SPEC.md / docs.superset.sh/ports.
# ---------------------------------------------------------------------------- #

reserve_ports
ok "ports reserved: web=$WEB_PORT api=$API_PORT sim=$SIM_PORT"

log "setup complete"
