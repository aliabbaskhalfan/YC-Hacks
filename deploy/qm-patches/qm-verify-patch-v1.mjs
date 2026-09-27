#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, isAbsolute, resolve } from 'node:path';

const [sourceArg, manifestArg, state = 'before'] = process.argv.slice(2);
if (!sourceArg || !manifestArg || !['before', 'after'].includes(state)) {
  throw new Error('Usage: node qm-verify-patch-v1.mjs <QM-source-directory> <manifest.json> [before|after]');
}
const source = resolve(sourceArg), manifestPath = resolve(manifestArg);
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const safePath = value => typeof value === 'string' && !isAbsolute(value) && !value.split(/[\\/]/).some(part => part === '..' || !part);
if (manifest.schema !== 'memorable.qm-patch.v1' || manifest.tag !== 'v0.1.12' || !safePath(manifest.patch) || !Array.isArray(manifest.files)) throw new Error('Unsupported patch manifest');
if (digest(readFileSync(resolve(dirname(manifestPath), manifest.patch))) !== manifest.patch_sha256) throw new Error('Patch checksum mismatch');
for (const file of manifest.files) {
  if (!safePath(file.path) || !/^(src|test)\//.test(file.path)) throw new Error('Unexpected source path');
  const target = resolve(source, file.path);
  const actual = existsSync(target) ? digest(readFileSync(target)) : null;
  const expected = state === 'before' ? file.baseline_sha256 : file.patched_sha256;
  if (actual !== expected) throw new Error(`QM ${state}-patch hash mismatch: ${file.path}. Preserve local changes; do not force this patch.`);
}
console.log(`Verified ${manifest.files.length} ${state}-patch file hashes and patch SHA-256 for QM v0.1.12.`);
