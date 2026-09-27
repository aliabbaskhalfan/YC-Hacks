"""Export the MuJoCo Menagerie Go2 to web/public/go2.glb with one node per body.

Node names match the MuJoCo body names (base, FR_hip, FR_thigh, FR_calf, ...) so the
Three.js viewer can index nodes by name for pose streaming, picking and highlighting.
Geometry for each node is baked into that body's frame.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mujoco
import numpy as np
import trimesh

REPO = Path(__file__).resolve().parents[1]
DEFAULT_MJCF = Path.home() / "Documents/YC Hacks/third_party/mujoco_menagerie/unitree_go2/go2.xml"
DEFAULT_OUT = REPO / "web/public/go2_procedure.glb"

VISUAL_GROUP = 2  # class="visual" in go2.xml


def quat_to_matrix(quat_wxyz: np.ndarray) -> np.ndarray:
    """MuJoCo [w,x,y,z] -> 4x4 homogeneous rotation."""
    m = np.zeros(9)
    mujoco.mju_quat2Mat(m, quat_wxyz)
    out = np.eye(4)
    out[:3, :3] = m.reshape(3, 3)
    return out


def geom_mesh(model: mujoco.MjModel, gid: int) -> trimesh.Trimesh | None:
    """Vertices/faces of a mesh geom, transformed into its parent body's frame."""
    if model.geom_type[gid] != mujoco.mjtGeom.mjGEOM_MESH:
        return None

    did = model.geom_dataid[gid]
    v0, nv = model.mesh_vertadr[did], model.mesh_vertnum[did]
    f0, nf = model.mesh_faceadr[did], model.mesh_facenum[did]

    verts = model.mesh_vert[v0 : v0 + nv].reshape(-1, 3).astype(np.float64)
    faces = model.mesh_face[f0 : f0 + nf].reshape(-1, 3).astype(np.int64)

    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)

    # geom local pose within the body
    xform = quat_to_matrix(model.geom_quat[gid])
    xform[:3, 3] = model.geom_pos[gid]
    mesh.apply_transform(xform)

    rgba = model.geom_rgba[gid]
    matid = model.geom_matid[gid]
    if matid >= 0:
        rgba = model.mat_rgba[matid]
    color = (np.clip(rgba, 0, 1) * 255).astype(np.uint8)
    # per-vertex (not per-face) so concatenate + glTF export need no scipy round-trip
    mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=np.tile(color, (len(verts), 1)))
    return mesh


def build_scene(mjcf: Path) -> tuple[trimesh.Scene, dict]:
    model = mujoco.MjModel.from_xml_path(str(mjcf))
    scene = trimesh.Scene()
    manifest: dict[str, dict] = {}

    for bid in range(model.nbody):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, bid)
        if not name or name == "world":
            continue

        parts = [
            m
            for gid in range(model.ngeom)
            if model.geom_bodyid[gid] == bid
            and model.geom_group[gid] == VISUAL_GROUP
            and (m := geom_mesh(model, gid)) is not None
        ]
        if not parts:
            continue

        body_mesh = trimesh.util.concatenate(parts)
        scene.add_geometry(body_mesh, node_name=name, geom_name=f"{name}_geom")

        manifest[name] = {
            "vertices": int(len(body_mesh.vertices)),
            "faces": int(len(body_mesh.faces)),
            # body-frame bounds: the viewer uses these to place service hardware
            "bounds": [[round(v, 6) for v in row] for row in body_mesh.bounds.tolist()],
            "body_pos": [round(v, 6) for v in model.body_pos[bid].tolist()],
            "parent": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, model.body_parentid[bid]),
        }

    return scene, manifest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mjcf", type=Path, default=DEFAULT_MJCF)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if not args.mjcf.exists():
        raise SystemExit(f"MJCF not found: {args.mjcf}")

    scene, manifest = build_scene(args.mjcf)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(trimesh.exchange.gltf.export_glb(scene, include_normals=True))

    manifest_path = args.out.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2))

    total = sum(m["faces"] for m in manifest.values())
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    print(f"{len(manifest)} body nodes, {total} faces")
    for name, m in manifest.items():
        print(f"  {name:10s} faces={m['faces']:7d} parent={m['parent']}")


if __name__ == "__main__":
    main()
