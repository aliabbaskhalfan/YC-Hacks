"""Pull the real thigh motor cover out of the customer STL.

data/cad/UnitreeGo2.stl is a single Blender-exported solid, but it splits into
connected components, and four of them are the thin discs that cap the thigh
actuators (one per leg). This lifts the front-right one, re-expresses it in the
FR_thigh body frame used by go2.glb, and writes it out for the viewer.

The STL and the Menagerie model are different CAD sources, so rather than trusting
the disc to land correctly on its own it is snapped onto the joint axis and its
inner face zeroed. The viewer mounts it from there.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import trimesh

REPO = Path(__file__).resolve().parents[1]
DEFAULT_STL = REPO / "data/cad/UnitreeGo2.stl"
DEFAULT_OUT = REPO / "web/public/fr_thigh_cover.glb"

# The STL is posed with the legs straight down, so each thigh body sits at its
# MJCF offset from base with no rotation: FR_hip (0.1934,-0.0465,0) + (0,-0.0955,0).
FR_THIGH_ORIGIN = np.array([0.1934, -0.1420, 0.0])

# A cover disc: broad in X/Z, thin in Y, sitting out at the thigh joint.
DISC_MIN_SPAN = 0.070
DISC_MAX_THICKNESS = 0.012


def find_cover_components(mesh: trimesh.Trimesh) -> list[tuple[trimesh.Trimesh, np.ndarray]]:
    """Every thin, broad disc in the mesh, with its centroid."""
    out = []
    for part in mesh.split(only_watertight=False):
        if len(part.faces) < 2000:
            continue
        ext = part.bounds[1] - part.bounds[0]
        if ext[1] > DISC_MAX_THICKNESS and min(ext[0], ext[2]) > DISC_MIN_SPAN:
            continue
        # thin along Y, broad in X and Z
        if ext[1] <= DISC_MAX_THICKNESS and ext[0] >= DISC_MIN_SPAN and ext[2] >= DISC_MIN_SPAN:
            out.append((part, part.bounds.mean(axis=0)))
    return out


def pick_front_right(cands: list[tuple[trimesh.Trimesh, np.ndarray]]):
    """The disc nearest the front-right thigh joint."""
    if not cands:
        return None
    target = FR_THIGH_ORIGIN
    return min(cands, key=lambda c: np.linalg.norm(c[1] - target))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl", type=Path, default=DEFAULT_STL)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    mesh = trimesh.load(args.stl, process=True)
    print(f"loaded {args.stl.name}: {len(mesh.faces)} faces")

    cands = find_cover_components(mesh)
    print(f"disc-shaped components: {len(cands)}")
    for part, c in sorted(cands, key=lambda c: (-c[1][0], c[1][1])):
        ext = part.bounds[1] - part.bounds[0]
        print(f"  faces={len(part.faces):6d} centre={np.round(c, 4).tolist()} extent={np.round(ext, 4).tolist()}")

    picked = pick_front_right(cands)
    if picked is None:
        raise SystemExit("no cover disc found in the STL")

    cover, centre = picked
    cover = cover.copy()
    ext = cover.bounds[1] - cover.bounds[0]
    radius = float(max(ext[0], ext[2]) / 2)
    thickness = float(ext[1])
    print(f"\npicked disc at {np.round(centre, 4).tolist()}  r={radius:.4f} t={thickness:.4f}")

    # Into the FR_thigh body frame, then square it up on the joint axis.
    cover.apply_translation(-FR_THIGH_ORIGIN)
    c = cover.bounds.mean(axis=0)
    cover.apply_translation([-c[0], 0.0, -c[2]])

    # Zero the inner face so the viewer can mount the cover at a local origin:
    # the assembly root carries the position onto the Menagerie actuator boss.
    cover.apply_translation([0.0, -cover.bounds[0][1], 0.0])

    cover.visual = trimesh.visual.ColorVisuals(
        mesh=cover,
        vertex_colors=np.tile(np.array([90, 100, 122, 255], np.uint8), (len(cover.vertices), 1)),
    )

    scene = trimesh.Scene()
    scene.add_geometry(cover, node_name="fr_thigh_cover", geom_name="fr_thigh_cover")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(trimesh.exchange.gltf.export_glb(scene, include_normals=True))

    meta = {
        "source": str(args.stl.relative_to(REPO)),
        "frame": "FR_thigh",
        "radius": round(radius, 5),
        "thickness": round(thickness, 5),
        "bounds": [[round(v, 6) for v in row] for row in cover.bounds.tolist()],
        "faces": int(len(cover.faces)),
        "note": "Snapped to the joint axis, inner face zeroed; the viewer mounts it on the Menagerie boss.",
    }
    args.out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))

    print(f"\nwrote {args.out} ({args.out.stat().st_size / 1e3:.0f} KB)")
    print(f"final bounds in FR_thigh frame: {np.round(cover.bounds, 4).tolist()}")


if __name__ == "__main__":
    main()
