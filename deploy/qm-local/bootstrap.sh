#!/bin/sh
set -eu

deploy_dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$deploy_dir/../.." && pwd)
source_root="$repo_root/deploy/qm-source-0.1.12"
patch_dir="$repo_root/deploy/qm-patches"
ready_marker="$source_root/.skillify-qm-ready"

export PATH="/opt/homebrew/opt/node@24/bin:$PATH"

if [ -f "$ready_marker" ]; then
  echo "QM source is already bootstrapped at $source_root"
  exit 0
fi

if [ -e "$source_root" ]; then
  echo "Refusing to overwrite existing QM source without $ready_marker" >&2
  exit 1
fi

git clone --depth 1 --branch v0.1.12 https://github.com/yc-software/qm.git "$source_root"

check_sha() {
  expected=$1
  file=$2
  actual=$(shasum -a 256 "$file" | awk '{print $1}')
  if [ "$actual" != "$expected" ]; then
    echo "Checksum mismatch: $file" >&2
    exit 1
  fi
}

check_sha cd2fdea442895699ec945c0f747534056ab511703b53226bd545f51d968ce7f6 "$patch_dir/qm-0.1.12-memorable-v1.patch"
check_sha 2a3b28da8ff0cfcdda129636d144f031e66a1be70e0919e56a092aaddbc03e7d "$patch_dir/qm-0.1.12-memorable-v1.json"
check_sha b5baae2b65ac06878f909fce420c17c3197c1e98be35f49a595c83143e837321 "$patch_dir/qm-verify-patch-v1.mjs"
check_sha e4012310c4f71928c6ec75618daaaa72cec0e2ebaa3176a6c00b950dd3a62981 "$patch_dir/qm-0.1.12-local-core-network-v1.patch"
check_sha 4de22ec804a33cf0ef08f003c23093a4d2fad20a25482fdf4d2ae7b4c9f5fb0b "$patch_dir/qm-0.1.12-local-core-network-v1.json"
check_sha 7b130a2e27978a927aa5935ddbc00358a4eea9963d5bbd5beb2b257bc441b047 "$patch_dir/memorable-cli-0.5.31-shared-env.1.tgz"

node "$patch_dir/qm-verify-patch-v1.mjs" "$source_root" "$patch_dir/qm-0.1.12-memorable-v1.json" before
node "$patch_dir/qm-verify-patch-v1.mjs" "$source_root" "$patch_dir/qm-0.1.12-local-core-network-v1.json" before

git -C "$source_root" apply --check "$patch_dir/qm-0.1.12-memorable-v1.patch"
git -C "$source_root" apply --check "$patch_dir/qm-0.1.12-local-core-network-v1.patch"
git -C "$source_root" apply "$patch_dir/qm-0.1.12-memorable-v1.patch"
git -C "$source_root" apply "$patch_dir/qm-0.1.12-local-core-network-v1.patch"

node "$patch_dir/qm-verify-patch-v1.mjs" "$source_root" "$patch_dir/qm-0.1.12-memorable-v1.json" after
node "$patch_dir/qm-verify-patch-v1.mjs" "$source_root" "$patch_dir/qm-0.1.12-local-core-network-v1.json" after

git -C "$source_root" apply --check "$patch_dir/qm-0.1.12-hackathon-local.patch"
git -C "$source_root" apply "$patch_dir/qm-0.1.12-hackathon-local.patch"
mkdir -p "$source_root/vendor"
cp "$patch_dir/memorable-cli-0.5.31-shared-env.1.tgz" "$source_root/vendor/"

npm ci --prefix "$source_root"
npm run typecheck --prefix "$source_root"
node --test \
  "$source_root/test/memorable-inject.test.ts" \
  "$source_root/test/memorable-native-turn.test.ts" \
  "$source_root/test/memorable-provider.test.ts" \
  "$source_root/test/memorable-relay.test.ts" \
  "$source_root/test/memory-capture-async.test.ts" \
  "$source_root/test/memory-provider-config.test.ts" \
  "$source_root/test/local-sandbox-config.test.ts" \
  "$source_root/cli/test/docker-socket.test.ts"

touch "$ready_marker"
echo "QM source bootstrapped at $source_root"
