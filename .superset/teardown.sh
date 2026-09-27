#!/usr/bin/env bash
# Runs when a Superset workspace is deleted. setup.sh never starts a
# long-running process (installs only), so the only thing to undo is the
# port-block reservation — without releasing it, a deleted workspace's ports
# would stay reserved forever and shrink the pool for every new workspace.
set -uo pipefail

SUPERSET_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SUPERSET_SCRIPT_DIR/lib/common.sh"
resolve_superset_env

release_ports
ok "released port block for $SUPERSET_WORKSPACE_NAME"
