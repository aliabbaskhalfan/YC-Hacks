#!/usr/bin/env python3
"""Bake a stand -> crouch -> stand replay for the 3D viewer's replay mode.

BUILD_SPEC.md Section 6.2 calls for "Replay mode: same animation from a
recorded JSON (for the backup and for incidents from the dataset)". This is
pure forward kinematics (set qpos, mj_forward, read world xpos/xquat) — no PD
controller, no physics rollout — so it has nothing to do with Syon's fault
sim; it exists so the viewer has a real, non-flat demo animation to render
and be tested against before the live `WS /sim/stream` exists.

The crouch pose's joint angles are a placeholder guess, not measured from any
controller — good enough to prove the rig articulates correctly, not a claim
about the real sim's crouch.

Usage:
    export_idle_cycle.py [--menagerie PATH] [--out PATH] [--fps N] [--period SECONDS]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mujoco
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MENAGERIE = REPO_ROOT / "third_party" / "mujoco_menagerie" / "unitree_go2"
DEFAULT_OUT = REPO_ROOT / "web" / "public" / "replays" / "idle_stand_crouch.json"

LEGS = ("FL", "FR", "RL", "RR")
# hip, thigh, calf — same order the "home" keyframe lists joints in (Section 5.1).
STAND_JOINTS = (0.0, 0.9, -1.8)
CROUCH_JOINTS = (0.0, 1.4, -2.5)
STAND_HEIGHT = 0.27
CROUCH_HEIGHT = 0.15


def ease_in_out(u: float) -> float:
    return 0.5 - 0.5 * np.cos(np.pi * u)


def qpos_for(model: "mujoco.MjModel", height: float, joints: tuple[float, float, float]) -> np.ndarray:
    qpos = np.zeros(model.nq)
    qpos[0:3] = [0.0, 0.0, height]
    qpos[3:7] = [1.0, 0.0, 0.0, 0.0]  # upright quaternion (w, x, y, z)
    for leg_idx in range(len(LEGS)):
        base = 7 + leg_idx * 3
        qpos[base : base + 3] = joints
    return qpos


def sample_pose(model: "mujoco.MjModel", data: "mujoco.MjData", qpos: np.ndarray) -> dict:
    data.qpos[:] = qpos
    mujoco.mj_forward(model, data)
    bodies = {}
    for body_id in range(1, model.nbody):  # skip 0: "world"
        name = model.body(body_id).name
        if not name:
            continue
        p = data.xpos[body_id].tolist()
        q = data.xquat[body_id].tolist()  # already (w, x, y, z), world frame
        bodies[name] = {"p": p, "q": q}
    return bodies


def build_frames(model: "mujoco.MjModel", data: "mujoco.MjData", fps: int, period: float) -> list[dict]:
    n_frames = max(2, int(round(period * fps)))
    frames = []
    for i in range(n_frames):
        t = i / fps
        # one full stand->crouch->stand cycle per `period`
        phase = (i / n_frames) * 2 * np.pi
        u = ease_in_out(0.5 - 0.5 * np.cos(phase))  # 0 at stand, 1 at crouch, back to 0
        height = STAND_HEIGHT + (CROUCH_HEIGHT - STAND_HEIGHT) * u
        joints = tuple(
            s + (c - s) * u for s, c in zip(STAND_JOINTS, CROUCH_JOINTS)
        )
        qpos = qpos_for(model, height, joints)
        frames.append({"t": round(t, 4), "bodies": sample_pose(model, data, qpos)})
    return frames


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--menagerie", type=Path, default=DEFAULT_MENAGERIE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--period", type=float, default=3.0, help="seconds per stand/crouch/stand cycle")
    args = parser.parse_args()

    scene_xml = args.menagerie / "scene.xml"
    if not scene_xml.is_file():
        raise SystemExit(f"no Go2 model at {scene_xml} — run sim/fetch_menagerie.sh first")

    model = mujoco.MjModel.from_xml_path(str(scene_xml))
    data = mujoco.MjData(model)

    frames = build_frames(model, data, args.fps, args.period)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "fps": args.fps,
                "period": args.period,
                "loop": True,
                "note": "placeholder kinematic stand/crouch cycle, not from the live sim",
                "frames": frames,
            },
            indent=None,
        )
    )
    print(f"wrote {args.out}  ({len(frames)} frames @ {args.fps}fps)")


if __name__ == "__main__":
    main()
