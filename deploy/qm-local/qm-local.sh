#!/bin/sh
set -eu

deploy_dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$deploy_dir/../.." && pwd)
source_root="$repo_root/deploy/qm-source-0.1.12"

if [ ! -f "$source_root/.skillify-qm-ready" ]; then
  "$deploy_dir/bootstrap.sh"
fi

export PATH="/opt/homebrew/opt/node@24/bin:$PATH"
export DOCKER_HOST="unix:///Users/aliabbaskhalfan/.colima/default/docker.sock"

if ! colima status >/dev/null 2>&1; then
  colima start --cpu 4 --memory 8 --disk 30
fi

socket_gid=$(docker run --rm -v /var/run/docker.sock:/sock alpine:3.22 stat -c '%g' /sock)
export QM_DOCKER_SOCKET_MOUNT=/var/run/docker.sock
export QM_DOCKER_SOCKET_GID="$socket_gid"

command_name=${1:-status}
if [ "$#" -gt 0 ]; then
  shift
fi

if [ "$command_name" = "up" ] || [ "$command_name" = "plan" ]; then
  set -- "$command_name" --build-from "$source_root" "$@"
else
  set -- "$command_name" "$@"
fi

exec node "$source_root/cli/bin/qm.ts" "$@" \
  --config "$deploy_dir/qm.config.jsonc" \
  --env-file "$deploy_dir/.env" \
  --sandbox-dir "$deploy_dir/sandbox"
