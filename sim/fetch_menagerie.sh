#!/usr/bin/env bash
# Fetches the Unitree Go2 model from MuJoCo Menagerie (BUILD_SPEC.md Section
# 4.1). Sparse + blobless + shallow so it only pulls the one robot's files.
# Vendored under third_party/, gitignored — this is upstream, not our code.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/third_party/mujoco_menagerie"

if [ -d "$DEST/unitree_go2" ]; then
  echo "already fetched: $DEST/unitree_go2"
  exit 0
fi

mkdir -p "$(dirname "$DEST")"
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/google-deepmind/mujoco_menagerie "$DEST"
git -C "$DEST" sparse-checkout set unitree_go2

echo "fetched: $DEST/unitree_go2"
