// Maps a part_id (BUILD_SPEC.md Section 4.2) to the glTF/MuJoCo body node it
// should highlight. Derived directly from the deterministic naming scheme
// ("fr.calf.motor" <- "FR_calf") rather than from data/registry/parts.json,
// so the viewer works standalone before that registry exists. Once the
// backend serves the real registry (with its `mesh_nodes` lists), prefer
// that — this stays as the fallback for anything the registry doesn't cover.

const LEG_PREFIXES = ["fl", "fr", "rl", "rr"];

// Segment -> body node suffix. Feet are geoms on the calf body (Section 4.1);
// the leg harness has no single owning body, so it's pinned to the thigh as
// a representative segment for highlighting purposes only.
const SEGMENT_TO_SUFFIX = {
  hip: "hip",
  thigh: "thigh",
  calf: "calf",
  foot: "calf",
  leg: "thigh",
};

export function partIdToBodyNode(partId) {
  if (!partId) return null;
  const parts = partId.split(".");
  if (parts[0] === "base") return "base";

  const [legPrefix, segment] = parts;
  if (!LEG_PREFIXES.includes(legPrefix)) return null;

  const suffix = SEGMENT_TO_SUFFIX[segment];
  if (!suffix) return null;

  return `${legPrefix.toUpperCase()}_${suffix}`;
}
