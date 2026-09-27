"""
Go2 fault-injection demo: a thermal-inspection Go2 walks a data center aisle, then a fault hits.
  --fault trip  (default) front left foot steps on a tool case, a gentle 50 N lean (ramped over 0.5 s) tips it onto its right side;
                FR thigh motor cover impacts the floor -> fr.thigh.cover
  --fault fall  250 N shove at --fault_at, same impact signal
  --fault motor front right knee motor dies -> fr.calf.motor
Setup (from the repo root):
  pip install -r sim/requirements.txt
  bash sim/fetch_menagerie.sh
  python sim/build_datacenter.py
Run:
  mjpython sim/go2_fault_demo.py --unit go2-02         (macOS viewer; Tab / Shift+Tab bring the side panels back)
  python sim/go2_fault_demo.py --headless sim/out/     (no window: writes walk.mp4 and key-frame PNGs)
  python sim/go2_fault_demo.py --export-replays web/public/replays   (pose replays for the three.js viewer)
"""
import argparse, json, subprocess, time
from pathlib import Path
import numpy as np
import mujoco
import requests

p = argparse.ArgumentParser()
p.add_argument("--unit", default="go2-02")
p.add_argument("--url", default="http://localhost:8000/events")  # your pipeline endpoint
p.add_argument("--fault", choices=("trip", "fall", "motor"), default="trip")
p.add_argument("--push", type=float, default=50.0)                 # trip: peak N toward the right once FL is on the toolbox
p.add_argument("--push_s", type=float, default=0.5)               # trip: push duration (half-sine ramp up and down)
p.add_argument("--strength", type=float, default=0.0)             # motor fault: 0.0 = fully dead motor
p.add_argument("--fault_at", type=float, default=6.0)             # seconds into the run (1 s settle + 5 s walking)
p.add_argument("--scene", default=str(Path(__file__).resolve().parent.parent / "third_party" / "mujoco_menagerie"
                                         / "unitree_go2" / "scene_datacenter.xml"))
p.add_argument("--headless", metavar="DIR", help="render to DIR instead of opening the viewer")
p.add_argument("--duration", type=float, default=12.0)            # headless only
p.add_argument("--export-replays", metavar="DIR", help="write pose replays for the web viewer to DIR and exit")
args = p.parse_args()

m = mujoco.MjModel.from_xml_path(args.scene)
d = mujoco.MjData(m)

if m.nkey > 0:
    mujoco.mj_resetDataKeyframe(m, d, 0)
mujoco.mj_forward(m, d)

names = [m.actuator(i).name for i in range(m.nu)]
jid = m.actuator_trnid[:, 0]
qadr, vadr = m.jnt_qposadr[jid], m.jnt_dofadr[jid]
is_position = m.actuator_biastype == mujoco.mjtBias.mjBIAS_AFFINE
KP, KD = 80.0, 3.0  # only used if actuators are raw torque motors

STAND = d.qpos[qadr].copy()
STAND_Z = float(d.qpos[2])
idx = {n: i for i, n in enumerate(names)}

# Open-loop trot: diagonal pairs (FR+RL, FL+RR) half a stride apart.
LEGS = [(idx[f"{leg}_thigh"], idx[f"{leg}_calf"], off)
        for leg, off in (("FL", 0.5), ("FR", 0.0), ("RL", 0.0), ("RR", 0.5))]
T_GAIT, STANCE_DUTY = 0.6, 0.5
THIGH_AMP, CALF_LIFT = 0.35, 0.7
SETTLE_T, RAMP_T = 1.0, 1.0

def leg_angles(phase, thigh0, calf0, amp, lift):
    # Decreasing thigh angle swings the foot toward +x (the Go2's nose), so stance sweeps - -> + to push the body forward.
    if phase < STANCE_DUTY:
        u = phase / STANCE_DUTY
        return thigh0 - amp * (1 - 2 * u), calf0
    u = (phase - STANCE_DUTY) / (1 - STANCE_DUTY)
    return thigh0 + amp * np.cos(np.pi * u), calf0 - lift * np.sin(np.pi * u)

def target(t):
    q = STAND.copy()
    if t <= SETTLE_T:
        return q
    amp = min(1.0, (t - SETTLE_T) / RAMP_T)
    phase_base = ((t - SETTLE_T) / T_GAIT) % 1.0
    for thigh_i, calf_i, off in LEGS:
        q[thigh_i], q[calf_i] = leg_angles((phase_base + off) % 1.0, STAND[thigh_i], STAND[calf_i],
                                           THIGH_AMP * amp, CALF_LIFT * amp)
    return q

FAULT = next(i for i, n in enumerate(names) if "FR" in n and "calf" in n)
PART_ID = {names[FAULT]: "fr.calf.motor"}

BASE = m.body("base").id
FLOOR = m.geom("floor").id
COVER = [g for g in range(m.ngeom) if m.geom_bodyid[g] == m.body("FR_hip").id and m.geom_contype[g]][0]
SHOVE = np.array([0, -250 if args.fault == "fall" else -args.push, 0, 0, 0, 0])  # N toward the robot's right (-y)
SHOVE_S = 0.2 if args.fault == "fall" else args.push_s
IMPACT_N = 500.0
FL_FOOT = m.geom("FL").id
TOOLBOX = m.geom("toolbox").id if args.fault == "trip" else -1
shove_start = args.fault_at if args.fault == "fall" else None
peak_impact = 0.0

def touching(a, b):
    return any({d.contact[c].geom1, d.contact[c].geom2} == {a, b} for c in range(d.ncon))

def impact(m, d, a, b):
    """Total normal contact force (N) between geoms a and b."""
    total, f6 = 0.0, np.zeros(6)
    for c in range(d.ncon):
        con = d.contact[c]
        if {con.geom1, con.geom2} == {a, b}:
            mujoco.mj_contactForce(m, d, c, f6)
            total += abs(f6[0])
    return total

def break_motor(i, strength):
    if m.actuator_forcelimited[i]:
        max_f = np.abs(m.actuator_forcerange[i]).max()
    else:
        max_f = np.abs(m.actuator_ctrlrange[i]).max() or 45.0
    m.actuator_forcelimited[i] = 1
    m.actuator_forcerange[i] = [-strength * max_f, strength * max_f]
    print(f"[fault] {names[i]} limited to {strength*max_f:.1f} Nm")

THRESH, HOLD = 0.25, 0.5
alpha = m.opt.timestep / 0.5
err_avg = np.zeros(m.nu)
over_since = np.full(m.nu, np.nan)
faulted = fired = False
last_report = -1.0

def fire(part_id, signal, **values):
    event = {"unit_id": args.unit, "part_id": part_id, "signal": signal,
             **{k: round(float(v), 3) for k, v in values.items()}, "sim_time": round(d.time, 2)}
    print("[alert]", event)
    try:
        requests.post(args.url, json=event, timeout=2)
    except Exception as e:
        print("[alert] post failed:", e)

def step():
    global faulted, fired, err_avg, last_report, peak_impact, shove_start
    q_des = target(d.time)
    if d.time - last_report >= 1.0:
        print(f"[pose] t={d.time:.1f}s  root_xyz={d.qpos[:3].round(3).tolist()}")
        last_report = d.time
    if args.fault != "motor" and fired:
        d.ctrl[:] = -KD * d.qvel[vadr]      # fall detected: drop into damping mode like a real Go2
    elif is_position.all():
        d.ctrl[:] = q_des
    else:
        d.ctrl[:] = KP * (q_des - d.qpos[qadr]) - KD * d.qvel[vadr]

    if args.fault == "motor":
        if not faulted and d.time >= args.fault_at:
            break_motor(FAULT, args.strength)
            faulted = True
    else:
        if shove_start is None and touching(FL_FOOT, TOOLBOX):
            shove_start = d.time
            print(f"[trip] front left foot stepped on the toolbox at t={d.time:.2f}s")
        shoving = shove_start is not None and shove_start <= d.time < shove_start + SHOVE_S
        ramp = 1.0 if args.fault == "fall" else np.sin(np.pi * (d.time - shove_start) / SHOVE_S) if shoving else 0
        d.xfrc_applied[BASE] = SHOVE * ramp if shoving else 0
        if shoving and not faulted and SHOVE[1]:
            print(f"[fault] pushing base {SHOVE[:3].tolist()} N for {SHOVE_S} s")
            faulted = True

    mujoco.mj_step(m, d)

    if args.fault != "motor":
        f_n = impact(m, d, COVER, FLOOR)
        if f_n > peak_impact:
            peak_impact = f_n
        if not fired and f_n > IMPACT_N:
            fire("fr.thigh.cover", "impact", force_n=f_n); fired = True
        return

    err = np.abs(q_des - d.qpos[qadr])
    err_avg = (1 - alpha) * err_avg + alpha * err
    for i in range(m.nu):
        if err_avg[i] > THRESH:
            if np.isnan(over_since[i]): over_since[i] = d.time
            if not fired and d.time - over_since[i] > HOLD:
                fire(PART_ID.get(names[i], names[i]), "tracking_error", value_rad=err_avg[i]); fired = True
        else:
            over_since[i] = np.nan

def chase_camera(cam):
    cam.type = mujoco.mjtCamera.mjCAMERA_TRACKING
    cam.trackbodyid = m.body("base").id
    cam.distance, cam.azimuth, cam.elevation = 2.2, 0.0, -12.0  # behind the dog, looking down the aisle (+x)

BODY_NAMES = ["base"] + [f"{leg}_{seg}" for leg in ("FL", "FR", "RL", "RR") for seg in ("hip", "thigh", "calf")]
BODY_IDS = [m.body(n).id for n in BODY_NAMES]
REPLAY_FPS = 30

def pose_frame(data, t, shift):
    return {"t": round(t, 4), "bodies": {
        n: {"p": [round(float(v), 5) for v in data.xpos[b] + shift], "q": [round(float(v), 5) for v in data.xquat[b]]}
        for n, b in zip(BODY_NAMES, BODY_IDS)}}

def write_replay(path, frames, loop, note, **extra):
    t0 = frames[0]["t"]
    for fr in frames:
        fr["t"] = round(fr["t"] - t0, 4)
    period = round(frames[-1]["t"] + 1.0 / REPLAY_FPS, 4)
    path.write_text(json.dumps({"fps": REPLAY_FPS, "period": period, "loop": loop, "note": note, **extra, "frames": frames}))
    print(f"[replay] {path}  {len(frames)} frames, {period:.2f} s")

def export_replays(out):
    """Walk loop, trip-and-fall, stand-up and a fallen still, shifted so the fall lands near the viewer origin."""
    WALK_T0, WALK_T1, FALL_T0, FALL_T1 = 3.0, 3.0 + T_GAIT, 3.0, 9.5
    samples, trip_t, impact = [], None, None
    next_t = 0.0
    while d.time < FALL_T1:
        step()
        if trip_t is None and shove_start is not None:
            trip_t = shove_start
        if impact is None and fired:
            impact = (d.time, peak_impact, d.xpos[BASE].copy())
        if d.time >= next_t:
            samples.append((d.time, d.xpos.copy(), d.xquat.copy(), d.qpos.copy()))
            next_t += 1.0 / REPLAY_FPS
    assert impact, "no cover impact in the export run"
    shift = np.array([-impact[2][0], -impact[2][1] / 2, 0.0])
    view = mujoco.MjData(m)

    def frame_from(t, xpos, xquat):
        view.xpos[:], view.xquat[:] = xpos, xquat
        return pose_frame(view, t, shift)

    fall = [frame_from(t, xp, xq) for t, xp, xq, _ in samples if FALL_T0 <= t <= FALL_T1]
    export_scene(out.parent / "scenes" / "datacenter.json", shift)
    write_replay(out / "go2-02_trip_fall.json", fall, False, "go2-02 walks the aisle, steps on a toolbox, falls on its right side (MuJoCo sim)",
                 events=[{"t": round(trip_t - FALL_T0, 3), "type": "trip"},
                         {"t": round(impact[0] - FALL_T0, 3), "type": "impact", "part_id": "fr.thigh.cover",
                          "force_n": round(float(impact[1]), 1)}])

    # Walk in place at the fall's starting spot: remove the forward progress over one stride.
    walk = [s for s in samples if WALK_T0 <= s[0] < WALK_T1]
    v = (walk[-1][1][BASE] - walk[0][1][BASE]) / (walk[-1][0] - walk[0][0])
    loop = []
    for t, xp, xq, _ in walk:
        drift = v * (t - walk[0][0])
        drift[2] = 0.0
        loop.append(frame_from(t, xp - drift, xq))
    write_replay(out / "go2_walk_loop.json", loop, True, "one trot stride in place (MuJoCo sim)")

    last_q = samples[-1][3]
    write_replay(out / "go2_fallen_right.json", [frame_from(0.0, samples[-1][1], samples[-1][2])], False,
                 "Go2 lying on its right side after a fall (MuJoCo sim)")

    # Stand-up: interpolate the joints and root from the fallen pose to the stand keyframe, then run kinematics.
    stand_q = last_q.copy()
    stand_q[2] = STAND_Z
    stand_q[3:7] = [1, 0, 0, 0]
    stand_q[qadr] = STAND
    up = []
    for i in range(int(1.6 * REPLAY_FPS) + 1):
        a = i / (1.6 * REPLAY_FPS)
        a = a * a * (3 - 2 * a)
        view.qpos[:] = last_q + (stand_q - last_q) * a
        view.qpos[3:7] = slerp(last_q[3:7], stand_q[3:7], a)
        mujoco.mj_kinematics(m, view)
        up.append(pose_frame(view, i / REPLAY_FPS, shift))
    write_replay(out / "go2-02_stand_up.json", up, False, "go2-02 back on its feet after the fix (kinematic, not simulated)")
    write_replay(out / "go2_standing.json", [dict(up[-1], t=0.0)], False, "Go2 standing still, same spot as the stand-up's end")

def export_scene(path, shift):
    """Static world geoms (racks, trays, lights, toolbox...) for the web viewer, in the replays' shifted frame."""
    geoms = {"box": [], "cylinder": [], "sphere": []}
    kinds = {int(mujoco.mjtGeom.mjGEOM_BOX): "box", int(mujoco.mjtGeom.mjGEOM_CYLINDER): "cylinder", int(mujoco.mjtGeom.mjGEOM_SPHERE): "sphere"}
    quat = np.zeros(4)
    for g in range(m.ngeom):
        kind = kinds.get(int(m.geom_type[g]))
        if m.geom_bodyid[g] != 0 or kind is None:
            continue
        mid = m.geom_matid[g]
        rgba = m.mat_rgba[mid] if mid >= 0 else m.geom_rgba[g]
        emission = float(m.mat_emission[mid]) if mid >= 0 else 0.0
        mujoco.mju_mat2Quat(quat, d.geom_xmat[g])
        row = [*(d.geom_xpos[g] + shift), *m.geom_size[g], *quat, *rgba, emission]
        geoms[kind].append([round(float(v), 4) for v in row])
    fmid = m.geom_matid[FLOOR]
    floor = {"rgb1": [0.87, 0.88, 0.89], "rgb2": [0.85, 0.86, 0.87], "mark": [0.7, 0.71, 0.73], "tile_m": 0.6,
             "reflectance": float(m.mat_reflectance[fmid]) if fmid >= 0 else 0.0}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"note": "data center aisle from scene_datacenter.xml; rows are pos3 size3 quat4(wxyz) rgba4 emission",
                                "shift": [round(float(v), 4) for v in shift], "floor": floor, "geoms": geoms}))
    print(f"[scene] {path}  " + ", ".join(f"{len(v)} {k}" for k, v in geoms.items()))

def slerp(q0, q1, a):
    q0, q1 = np.asarray(q0, float), np.asarray(q1, float)
    dot = float(np.dot(q0, q1))
    if dot < 0:
        q1, dot = -q1, -dot
    if dot > 0.9995:
        q = q0 + a * (q1 - q0)
        return q / np.linalg.norm(q)
    th = np.arccos(dot)
    return (np.sin((1 - a) * th) * q0 + np.sin(a * th) * q1) / np.sin(th)

if args.export_replays:
    out = Path(args.export_replays); out.mkdir(parents=True, exist_ok=True)
    export_replays(out)
    raise SystemExit

if args.headless:
    out = Path(args.headless); out.mkdir(parents=True, exist_ok=True)
    W_PX, H_PX, FPS = 1280, 720, 30
    renderer = mujoco.Renderer(m, H_PX, W_PX)
    cam = mujoco.MjvCamera(); chase_camera(cam)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W_PX}x{H_PX}", "-r", str(FPS), "-i", "-", "-pix_fmt", "yuv420p",
                           "-vcodec", "libx264", "-crf", "20", str(out / "walk.mp4")], stdin=subprocess.PIPE)
    stills = {6.1, 6.6, 7.0, 7.6}
    next_frame = 0.0
    while d.time < args.duration:
        step()
        if d.time >= next_frame:
            renderer.update_scene(d, camera=cam)
            px = renderer.render()
            ff.stdin.write(px.tobytes())
            for s in list(stills):
                if d.time >= s:
                    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                    "-s", f"{W_PX}x{H_PX}", "-i", "-", str(out / f"t{s:04.1f}.png")], input=px.tobytes())
                    stills.discard(s)
            next_frame += 1.0 / FPS
    ff.stdin.close(); ff.wait()
    print(f"[headless] wrote {out/'walk.mp4'}  peak cover impact {peak_impact:.0f} N")
else:
    import mujoco.viewer
    with mujoco.viewer.launch_passive(m, d, show_left_ui=False, show_right_ui=False) as viewer:
        with viewer.lock():
            chase_camera(viewer.cam)
        while viewer.is_running():
            t0 = time.time()
            step()
            viewer.sync()
            time.sleep(max(0, m.opt.timestep - (time.time() - t0)))
