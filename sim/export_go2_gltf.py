#!/usr/bin/env python3
"""Export the Menagerie Unitree Go2 to a glTF with one node per MuJoCo body.

BUILD_SPEC.md Section 6.1. The live viewer (web/src/three/) needs to address
each body independently — set its world transform every WS frame, raycast
onto it, highlight it red/green — so the node structure produced here (one
node per body, named exactly like the MuJoCo body, geometry already in that
body's local frame) is the contract the rest of the 3D pipeline is built on.

Only *visual* mesh geoms are exported (collision geoms are primitive
box/cylinder shapes in this model, so filtering by geom_type == mesh already
excludes them). Each geom's `geom_pos`/`geom_quat` is MuJoCo's own
body-relative transform — no forward kinematics needed to place a mesh in its
body's frame, only to sanity-check the assembled pose below.

Usage:
    export_go2_gltf.py [--menagerie PATH] [--out PATH] [--preview PATH]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import mujoco
import numpy as np
import trimesh

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MENAGERIE = REPO_ROOT / "third_party" / "mujoco_menagerie" / "unitree_go2"
DEFAULT_OUT = REPO_ROOT / "web" / "public" / "go2.glb"

# Section 4.1: exactly these bodies must exist as nodes in the export.
EXPECTED_BODIES = {
    "base",
    *(f"{leg}_{seg}" for leg in ("FL", "FR", "RL", "RR") for seg in ("hip", "thigh", "calf")),
}


def quat_to_matrix(quat_wxyz: np.ndarray) -> np.ndarray:
    """MuJoCo quaternions are (w, x, y, z); build the 3x3 rotation matrix."""
    w, x, y, z = quat_wxyz
    n = w * w + x * x + y * y + z * z
    if n < 1e-12:
        return np.eye(3)
    s = 2.0 / n
    wx, wy, wz = s * w * x, s * w * y, s * w * z
    xx, xy, xz = s * x * x, s * x * y, s * x * z
    yy, yz, zz = s * y * y, s * y * z, s * z * z
    return np.array(
        [
            [1 - (yy + zz), xy - wz, xz + wy],
            [xy + wz, 1 - (xx + zz), yz - wx],
            [xz - wy, yz + wx, 1 - (xx + yy)],
        ]
    )


def mesh_geoms_by_body(model: "mujoco.MjModel") -> dict[int, list[int]]:
    by_body: dict[int, list[int]] = {}
    for geom_id in range(model.ngeom):
        if model.geom_type[geom_id] != mujoco.mjtGeom.mjGEOM_MESH:
            continue
        by_body.setdefault(model.geom_bodyid[geom_id], []).append(geom_id)
    return by_body


def geom_color(model: "mujoco.MjModel", geom_id: int) -> np.ndarray:
    mat_id = model.geom_matid[geom_id]
    if mat_id >= 0:
        return np.array(model.mat_rgba[mat_id], dtype=np.float64)
    return np.array(model.geom_rgba[geom_id], dtype=np.float64)


def build_body_mesh(model: "mujoco.MjModel", geom_ids: list[int]) -> trimesh.Trimesh:
    """Concatenate every visual geom on one body into a single body-frame mesh."""
    parts = []
    for geom_id in geom_ids:
        mesh_id = model.geom_dataid[geom_id]
        v_start, v_num = model.mesh_vertadr[mesh_id], model.mesh_vertnum[mesh_id]
        f_start, f_num = model.mesh_faceadr[mesh_id], model.mesh_facenum[mesh_id]

        verts_local = model.mesh_vert[v_start : v_start + v_num].copy()
        faces = model.mesh_face[f_start : f_start + f_num].copy()

        rot = quat_to_matrix(model.geom_quat[geom_id])
        verts_body = verts_local @ rot.T + model.geom_pos[geom_id]

        color = (np.clip(geom_color(model, geom_id), 0, 1) * 255).astype(np.uint8)
        part = trimesh.Trimesh(vertices=verts_body, faces=faces, process=False)
        part.visual.face_colors = np.tile(color, (len(faces), 1))
        parts.append(part)

    merged = trimesh.util.concatenate(parts)
    merged.process(validate=False)
    return merged


def export(menagerie_dir: Path, out_path: Path, preview_path: Path | None) -> None:
    scene_xml = menagerie_dir / "scene.xml"
    if not scene_xml.is_file():
        raise SystemExit(
            f"no Go2 model at {scene_xml} — run sim/fetch_menagerie.sh first"
        )

    model = mujoco.MjModel.from_xml_path(str(scene_xml))
    data = mujoco.MjData(model)
    key_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "home")
    if key_id < 0:
        raise SystemExit("keyframe 'home' not found in the model")
    mujoco.mj_resetDataKeyframe(model, data, key_id)
    mujoco.mj_forward(model, data)  # sanity: verifies the model evaluates cleanly

    scene = trimesh.Scene()
    by_body = mesh_geoms_by_body(model)

    exported_names: set[str] = set()
    for body_id, geom_ids in by_body.items():
        name = model.body(body_id).name
        if not name:
            continue
        mesh = build_body_mesh(model, geom_ids)
        scene.add_geometry(mesh, node_name=name, geom_name=name, transform=np.eye(4))
        exported_names.add(name)

    missing = EXPECTED_BODIES - exported_names
    if missing:
        raise SystemExit(f"export incomplete — missing bodies: {sorted(missing)}")
    extra = exported_names - EXPECTED_BODIES
    if extra:
        print(f"note: exporting extra bodies beyond Section 4.1: {sorted(extra)}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(out_path))
    print(f"wrote {out_path}  ({len(exported_names)} body nodes)")

    if preview_path is not None:
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        _render_preview(model, data, preview_path)
        print(f"wrote {preview_path}")


def _render_preview(model: "mujoco.MjModel", data: "mujoco.MjData", preview_path: Path) -> None:
    import os

    os.environ.setdefault("MUJOCO_GL", "osmesa")
    renderer = mujoco.Renderer(model, height=480, width=640)
    renderer.update_scene(data)
    from PIL import Image

    Image.fromarray(renderer.render()).save(preview_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--menagerie", type=Path, default=DEFAULT_MENAGERIE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--preview", type=Path, default=None, help="also render a keyframe preview PNG")
    args = parser.parse_args()
    export(args.menagerie, args.out, args.preview)


if __name__ == "__main__":
    main()
