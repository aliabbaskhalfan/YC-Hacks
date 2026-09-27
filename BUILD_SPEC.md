# Machine Brain: Build Spec

> **Own your robot's intelligence.**
> A robot dog breaks in the field. It reports what went wrong and goes red. A tech records a 15-second voice note on how they fixed it. That note is stored as a memory and added to the procedural knowledge graph. Across a whole fleet, patterns surface, design changes get approved, and the 3D repair procedure updates for everyone. The next dog that breaks the same way arrives with the fix attached.

Built for the YC "Own Your Intelligence" hackathon. Team: Cadanima (Ali, Syon).

This file is the single source of truth for Claude Code. Build in the order given in **Section 12**. Anything marked **VERIFY** means the exact API shape was not confirmed; check the sponsor's docs or repo before coding and fall back to the local adapter if it takes more than 20 minutes.

---

## 1. The story (why each piece exists)

1. **Robots break often, and the fix lives in one tech's head.** Field techs skip tickets (heat, speed, inconvenience). Intelligence is never captured.
2. **The robot reports what went wrong and goes red.** A simulated Unitree Go2 fails (weak knee motor, worn foot pad, etc.). Telemetry catches it, the robot turns red in the 3D view and on the fleet grid, and it states in plain language what went wrong and which part. The robot does the diagnosis; nobody types a ticket.
3. **The tech records how it was fixed, in 15 seconds.** On their phone, the 3D procedure opens at the flagged part (already selected). The tech taps record and says how they fixed it. Recording auto-stops at 15 seconds. The robot goes from red to green once the fix is logged.
4. **The fix becomes memory and procedural knowledge.** An agent turns the voice note into an ordered fix (steps, parts, tools, verification), checks it against the SOP (addition / contradiction / duplicate), stores it in GBrain as a memory with provenance, and adds it to the procedural knowledge graph in Memorable (fault -> part -> fix steps -> outcome).
5. **The fleet learns.** A large synthetic dataset of Go2 deployment incidents (hundreds of incidents, dozens of units, several sites) lives in the same brain. Fleet intelligence finds patterns (e.g. one motor supplier lot fails far more in hot sites) and raises a design-review flag.
6. **Engineering approves; the procedure changes.** Approving the flag updates the 3D procedure step for every tech.
7. **The loop closes.** Inject the same fault on a different dog: the alert now arrives with the root cause, the fix, and a deep link into the updated 3D procedure. Any AI (Claude via MCP) can answer from the same brain.

---

## 2. Scope summary

| Area | What we build |
|---|---|
| Robot | Unitree Go2 from MuJoCo Menagerie, simulated in MuJoCo |
| Faults | Catalog of 8 injectable faults, each mapped to a `part_id` |
| Telemetry | Per-motor tracking error, torque, temperature proxy, foot slip; anomaly detection |
| 3D | Go2 exported to glTF with one node per body; Three.js viewer that animates from sim poses and supports tap-to-select |
| Procedures | 4 Go2 maintenance procedures with steps, highlighted parts, camera poses |
| Capture | Phone web page: tap part, hold to talk, send |
| Agent | Skillify agent: transcribe, extract, hygiene check, write |
| Brain | GBrain notes per part and per unit, with provenance; `skillify-repair` open-source skill |
| Procedural memory | Memorable traces per repair; recall on new incidents |
| Synthetic data | Generator for ~500 incidents across ~40 units / 6 sites / 90 days, with a hidden root-cause pattern |
| Fleet intelligence | Counters, pattern mining, design-review flags, approve flow |
| Recall | Ask box + Claude via MCP |
| Sponsors | GBrain (required), Memorable, QM, Superset. River and UFO are NOT used. |

---

## 3. Repo layout

```
machine-brain/
  BUILD_SPEC.md
  .env.example
  sim/
    go2_fault_sim.py          # EXISTS: stand/crouch cycle, 1 fault, anomaly event, mp4
    faults.py                 # fault catalog (Section 5)
    sim_server.py             # runs sim live, streams poses + telemetry over WebSocket
    export_go2_gltf.py        # MJCF -> go2.glb with one node per body
    synth/
      generate_incidents.py   # synthetic fleet dataset (Section 8)
      transcripts.py          # tech voice-note text generation
  server/
    main.py                   # FastAPI app, all HTTP + WS endpoints
    agent/skillify.py         # extraction + hygiene + writes
    agent/prompts.py
    integrations/gbrain.py    # GBrain adapter (+ local markdown fallback)
    integrations/memorable.py # Memorable adapter (+ local JSON fallback)
    integrations/stt.py       # Deepgram or Whisper
    fleet/intel.py            # counters, pattern mining, flags
    fleet/registry.py         # part registry + fleet registry
    procedures/               # procedure JSON files
    mcp/server.py             # MCP tools for Claude (Section 11)
  web/                        # Vite + React + Three.js
    src/tech/                 # phone view: procedure viewer + capture
    src/ops/                  # laptop view: fleet, alerts, brain, engineering, ask
    src/three/                # shared Go2 viewer, picking, highlight, pose streaming
    public/go2.glb
  skills/skillify-repair/     # open-source GBrain skill (Section 7.3)
  data/
    registry/parts.json
    registry/fleet.json
    synthetic/incidents.jsonl
    synthetic/telemetry/      # per-incident telemetry snippets
    brain/                    # local markdown fallback mirror of GBrain
```

**Stack:** Python 3.11 (MuJoCo, FastAPI, trimesh, numpy), Node 20 (Vite, React, three.js). LLM: Anthropic API (`claude-sonnet-5`). STT: Deepgram (preferred) or OpenAI Whisper.

**`.env.example`:**
```
ANTHROPIC_API_KEY=
DEEPGRAM_API_KEY=
GBRAIN_MCP_URL=            # VERIFY from gbrain.io
MEMORABLE_API_KEY=         # VERIFY from memorable.sh
MEMORABLE_BASE_URL=https://api.memorable.sh   # VERIFY
USE_LOCAL_FALLBACKS=true   # if true, write brain + traces locally as well
```

---

## 4. Robot model and part registry

### 4.1 Source
- `git clone --depth 1 --filter=blob:none --sparse https://github.com/google-deepmind/mujoco_menagerie && git sparse-checkout set unitree_go2`
- Files: `unitree_go2/scene.xml`, `go2.xml`, `assets/*.obj`.
- Bodies: `base`, `{FL,FR,RL,RR}_{hip,thigh,calf}`. Feet are geoms on the calf bodies.
- Actuators and joints: `{LEG}_{hip,thigh,calf}` and `{LEG}_{seg}_joint`. Keyframe `home` exists.

### 4.2 Part ID scheme (used everywhere: meshes, registry, brain, traces, flags)
- Motors: `fl.hip.motor`, `fl.thigh.motor`, `fl.calf.motor` ... (12 total). The calf motor is the knee actuator.
- Links: `fl.thigh.link`, `fl.calf.link` ...
- Feet: `fl.foot.pad` ...
- Hip mounts: `fl.hip.mount_bolts` ...
- Body: `base.battery`, `base.imu`, `base.shell`, `fl.leg.harness` (cable harness per leg).

Mapping from sim names: `"FR_calf" -> "fr.calf.motor"` (already implemented as `part_id()` in `go2_fault_sim.py`).

### 4.3 `data/registry/parts.json`
```json
[
  {"part_id": "fr.calf.motor", "name": "Front-right knee actuator", "kind": "motor",
   "parent": "fr.leg", "mesh_nodes": ["FR_calf"], "spec": "knee joint actuator (sim)",
   "supplier_lots": ["A", "B", "C"]},
  {"part_id": "fr.foot.pad", "name": "Front-right foot pad", "kind": "wear_part",
   "parent": "fr.leg", "mesh_nodes": ["FR_calf"], "spec": "rubber foot pad"}
]
```
Every `part_id` in Section 4.2 gets an entry. `mesh_nodes` lists the glTF nodes to highlight when the part is selected (several parts share the calf body; highlight the whole body and show the part name in the chip).

**Do not invent real Go2 specs** (torques, part numbers). Anything numeric in procedures is labeled "sim value" or "placeholder" in the UI.

### 4.4 `data/registry/fleet.json`
~40 units: `go2-01` ... `go2-40`. Each has `site` (6 sites, e.g. `austin-refinery`, `phoenix-solar`, `pittsburgh-plant`, `houston-port`, `denver-dc`, `sf-lab`), `ambient_class` (`hot` / `temperate`), `commissioned_at`, and per-motor `supplier_lot` (A / B / C).

---

## 5. Simulation and fault catalog

### 5.1 Existing baseline (`sim/go2_fault_sim.py`, works today)
- PD control holds a stand pose and runs a stand -> crouch -> stand cycle (period 3 s). `KP=60`, `KD=3`.
- Fault: caps one actuator's torque to `strength` x its limit after `fault_at` seconds.
- Anomaly: joint tracking error > `0.35 rad` for `0.4 s` -> emits:
```json
{"type":"anomaly","unit_id":"go2-02","part_id":"fr.calf.motor","signal":"joint_tracking_error",
 "value_rad":0.473,"threshold_rad":0.35,"t_sim":6.27,"context":"stand/crouch cycle"}
```
- The server enriches every anomaly with `what_went_wrong`: one plain-language sentence built from the signal, the part registry, and the fault signature (e.g. "Front-right knee actuator is losing torque under load and cannot hold the stand pose."). Template first; optionally polished by Claude, but it must only use the telemetry facts.
- Verified: with `--fault FR_calf --strength 0.08`, the FR calf error peaks ~0.54 rad and the alert fires at t=6.27 s; healthy legs stay under ~0.23 rad.
- TODO first: run with `--fault ''` and confirm **zero** events (no false alarms). Tune thresholds if needed.
- Render: `MUJOCO_GL=osmesa` (or `egl`) offscreen, HUD with per-motor error bars.

### 5.2 Fault catalog (`sim/faults.py`)
Each fault = a function that mutates the model/controller at `fault_at`, plus the signal that should detect it and the ground-truth part.

| fault_id | part_id | How to simulate in MuJoCo | Detection signal |
|---|---|---|---|
| `knee_motor_weak` | `{leg}.calf.motor` | cap actuator torque to 5-20% | calf tracking error |
| `knee_motor_overheat` | `{leg}.calf.motor` | torque cap decays over time (thermal derate); temp proxy = integral of torque^2 | temp proxy + rising error |
| `hip_bolts_loose` | `{leg}.hip.mount_bolts` | add backlash: deadband on hip command + extra joint damping noise | hip error oscillation (high-frequency energy) |
| `foot_pad_worn` | `{leg}.foot.pad` | lower foot geom friction (e.g. 1.0 -> 0.3) | foot slip velocity during stance |
| `encoder_drift` | `{leg}.thigh.motor` | add slowly growing bias to measured joint angle | steady offset between legs at rest |
| `harness_intermittent` | `{leg}.leg.harness` | random 50-200 ms windows of zero torque on all 3 motors of one leg | simultaneous error spikes on one leg |
| `battery_sag` | `base.battery` | global torque cap scales down over time | all motors' error rising together |
| `imu_bias` | `base.imu` | bias base orientation used by controller (add small posture target tilt) | body roll offset |

`sim_server.py` exposes: `POST /sim/start {unit_id}`, `POST /sim/inject {unit_id, fault_id, leg, severity}`, `POST /sim/clear {unit_id}`, `POST /sim/stop`, and `WS /sim/stream` sending at 30 Hz:
```json
{"unit_id":"go2-07","t":6.3,"bodies":{"base":{"p":[x,y,z],"q":[w,x,y,z]}, "FL_hip":{...}},
 "telemetry":{"err":{"FR_calf":0.47,...},"temp":{...},"slip":{...}},"alert":null}
```
On detection it sends one `anomaly` event (schema above, plus `fault_signature` with the top signals) to `POST /events/anomaly` on the main server.

**Live demo control:** the ops console has an **Inject fault** menu (unit, fault, leg). A judge can pick the fault.

### 5.3 Robot status: going red
Every unit has a status state machine shared by the sim, server, and all views:

| State | Trigger | Visual |
|---|---|---|
| `healthy` | default | normal materials, blue status dot |
| `red` | anomaly event | failing part turns solid red and pulses; the rest of the dog gets a faint red tint; fleet dot red; alert card shows `what_went_wrong` |
| `in_repair` | tech opens the deep link | amber dot; part stays red on the tech's phone |
| `fixed` | fix note saved | part flashes green for ~2 s, dot green, then back to `healthy` |

- The sim keeps the fault active while `red`; on `fixed` the server calls `POST /sim/clear {unit_id}` so the dog visibly stands back up (restore actuator/friction/etc.).
- A unit can only leave `red` through a logged fix note. That is the point: no fix note, no green.

---

## 6. 3D: Go2 in Three.js

### 6.1 `sim/export_go2_gltf.py`
- Load `scene.xml`, reset to keyframe `home`, `mj_forward`.
- For each body, collect its visual mesh geoms (`model.geom_bodyid`, `geom_type == mjGEOM_MESH`, `geom_dataid`), take vertices/faces from `model.mesh_vert` / `mesh_face`, transform by the geom's local pose (`geom_pos`, `geom_quat`) into the **body frame**.
- Build a trimesh `Scene` with **one node per body**, node name = MuJoCo body name (`FR_calf` etc.), geometry in body frame. Keep materials/colors from `geom_rgba` / model materials.
- Export `web/public/go2.glb`. Verify every node name matches Section 4.1.
- If this takes more than 45 minutes, fallback: load the OBJ files directly in Three.js using the transforms from the MJCF.

### 6.2 Viewer (`web/src/three/`)
- Load `go2.glb`; index nodes by name.
- **Pose streaming:** each WS frame sets every node's world position/quaternion from `bodies` (MuJoCo quat is `[w,x,y,z]`; three.js wants `x,y,z,w`). Z-up in MuJoCo vs Y-up in three.js: rotate the root by -90 deg about X.
- **Replay mode:** same animation from a recorded JSON (for the backup and for incidents from the dataset).
- **Picking:** raycast on tap -> node name -> candidate parts whose `mesh_nodes` include it -> if several, show a small part picker (motor / link / foot pad).
- **Highlight:** emissive glow on selected node; red pulse on the part in an active alert.
- **Tip badges:** pinned HTML callouts anchored to a node (`CSS2DRenderer`), showing brain tips ("3 field reports").
- **Telemetry overlay:** small per-motor error bars (same colors as the sim HUD).

---

## 7. Capture, agent, and brain

### 7.1 Procedures (`server/procedures/*.json`)
Four procedures. Content is sim/placeholder, clearly labeled.
1. `replace-knee-motor` (per leg): power down, remove leg cover, disconnect harness, remove actuator, check supplier lot label, install, reconnect, calibrate.
2. `replace-foot-pad`
3. `retorque-hip-mount`
4. `recalibrate-encoders`

Step schema:
```json
{"step_id":4,"title":"Remove knee actuator","text":"...","parts":["fr.calf.motor"],
 "camera":{"pos":[...],"target":[...]},"version":"1.0","tips":[]}
```

### 7.2 Fix capture (tech phone view, `web/src/tech/`)
The robot already said what went wrong. The tech only records **how it was fixed**.
- Opens from an alert deep link: `/tech?unit=go2-07&incident=inc-live-01&procedure=replace-knee-motor&leg=fr&step=4`.
- Top bar: unit, site, and a red banner with the robot's `what_went_wrong`.
- 3D viewer: failing part is red and pre-selected; procedure steps (next/prev); tip badges. The tech can tap a different part if the real cause was elsewhere (chip updates).
- Prompt on screen: **"How did you fix it?"**
- Big **Record fix** button: tap to start, tap to stop, **auto-stops at 15 s** with a countdown ring and live waveform (MediaRecorder, webm/opus).
- On stop: `POST /capture` multipart `{incident_id, unit_id, procedure_id, step_id, part_id, audio}` (`incident_id` required: every fix note closes a robot-reported incident).
- Toasts: "Transcribing" -> "Understanding" -> "Saved as memory" -> "Added to knowledge graph". Then the part flashes green.
- Shows the result card: the ordered fix steps the agent understood + hygiene label, with an **Edit** link if the agent got something wrong.
- **Fallback input:** a text box (loud room or mic permissions fail).

### 7.3 Skillify agent (`server/agent/skillify.py`), runs as a QM agent
Pipeline for each capture:
1. **STT** (Deepgram, word timestamps kept for future use).
2. **Extract** with Claude into `RepairRecord`. `what_went_wrong` comes from the robot's anomaly (telemetry); everything under `fix` comes from the tech's voice note:
```json
{"incident_id":"inc-0512","unit_id":"go2-07","part_id":"fr.calf.motor",
 "what_went_wrong":"Front-right knee actuator losing torque under load (tracking error 0.47 rad).",
 "fix":{
   "steps":["powered down","swapped front-right knee actuator","recalibrated encoders","ran stand cycle to verify"],
   "parts_used":["knee actuator"],"tools":[],
   "root_cause_per_tech":"old actuator was lot B and very hot",
   "verification":"stand cycle holding, no error",
   "tip":"check the lot label before installing a replacement"},
 "observations":{"supplier_lot":"B"},"confidence":0.84,"missing":[]}
```
The extraction prompt must keep the tech's step order, never invent steps, and put anything unclear in `missing`.
3. **Hygiene** (Claude): compare record to the current SOP step text and existing brain notes for that part. Output `addition | contradiction | duplicate` + one-line reason.
4. **Write brain note** (7.4), **send Memorable trace** (7.5), **update fleet counters** (Section 9), **close the incident**.
5. Return the record + hygiene label to the phone and push a `brain_update` event to the ops view over WS.

**QM (the fleet agent):** this pipeline runs as a QM agent named `go2-fleet`, built as a **QM extension for robot fleets**: it receives robot anomaly alerts, pages the tech with the deep link, and runs this skillify pipeline on each fix note (transcribe, extract steps, SOP check, write to GBrain and Memorable). VERIFY how QM handles triggers/webhooks in `github.com/yc-software/qm`. Optional: nightly fleet digest to the Engineering tab. **If it is not wired up by 4:00 PM, run the same code as a FastAPI background task and do not claim QM on stage.**

**Open-source skill:** package steps 2 to 4 as `skills/skillify-repair/` for GBrain: `SKILL.md` (what it does, inputs: transcript + asset/part context; outputs: note with provenance + hygiene label), the prompts, and a tiny example. Public repo, MIT. This is the reusable contribution to the sponsors.

### 7.4 GBrain (the brain)
Layout:
```
/fleet/go2/parts/fr.calf.motor.md
/fleet/go2/units/go2-07.md
/fleet/go2/sites/phoenix-solar.md
/fleet/go2/patterns/knee-motor-lot-b.md     # written by fleet intelligence
/fleet/go2/procedures/replace-knee-motor.md # current approved version + changelog
```
Note format (append per incident):
```markdown
## 2026-09-27 16:21 · go2-07 · phoenix-solar · replace-knee-motor step 4
- reported by robot: Front-right knee actuator losing torque under load (tracking error 0.47 rad, threshold 0.35; temp proxy high)
- [stated] fix note: "Swapped the front right knee actuator, old one was lot B and scorching. Recalibrated, ran a stand cycle, holding fine."
- fix steps: powered down -> swapped actuator -> recalibrated encoders -> verified with stand cycle
- root cause (tech): lot B actuator overheating
- tip: check the lot label before installing a replacement
- hygiene: ADDITION (SOP step 4 does not say to check the supplier lot)
- source: tech=Ali, incident=inc-0512, audio=/clips/inc-0512.webm, synthetic=false
```
- Integration: GBrain CLI or MCP (VERIFY at gbrain.io). Adapter writes to GBrain AND mirrors to `data/brain/` when `USE_LOCAL_FALLBACKS=true`.
- Synthetic incidents are written with `synthetic=true` in the source line. Be honest on stage.

### 7.5 Memorable (procedural knowledge graph)
Every fix note becomes a trace, and Memorable connects traces through shared steps into a graph. The graph is: **fault signature -> part -> fix steps -> outcome**, weighted by how often each path succeeded.
- For every closed incident (synthetic and live), send one trace to `POST /v1/extract` (VERIFY auth and exact schema at memorable.sh). Map the repair to their "tool call" format:
```json
{"task":"Go2 anomaly: fr.calf.motor tracking error in hot site",
 "steps":[
   {"tool":"diagnose","args":{"signal":"joint_tracking_error","part":"fr.calf.motor"}},
   {"tool":"inspect","args":{"part":"fr.calf.motor","check":"supplier_lot"}},
   {"tool":"replace","args":{"part":"fr.calf.motor"}},
   {"tool":"calibrate","args":{"procedure":"recalibrate-encoders"}}],
 "outcome":"success","metadata":{"unit_id":"go2-07","site":"phoenix-solar","incident_id":"inc-0512"}}
```
- Failed attempts in the synthetic data (e.g. "retightened hip bolts, fault came back") are sent with `outcome: failure` so Memorable learns which paths do NOT work.
- **Recall:** on every new anomaly, query Memorable with the fault signature and part; attach the returned procedure chain to the alert ("Proven fix, 23 successes, 0 failures").
- Fallback: local JSON store with simple matching by `part_id` + signal.
- **Knowledge graph view:** build nodes (faults, parts, fix steps, outcomes, units) and edges (weighted by success count) from Memorable's returned plans if the API exposes them (VERIFY); otherwise from the local trace store. When a live fix note is saved, the new path animates into the graph.

---

## 8. Synthetic fleet dataset

### 8.1 Goal
A believable 90-day history for 40 Go2 units across 6 sites so fleet intelligence has something real to find. It must contain a **hidden pattern** that the system discovers (not hard-coded in the UI).

### 8.2 Generator (`sim/synth/generate_incidents.py`)
- Seeded RNG (`--seed 7`) so the demo is reproducible.
- ~500 incidents. Base rates per fault type; site and ambient effects; per-unit usage.
- **Hidden patterns (ground truth kept in `data/synthetic/ground_truth.json`, never shown to the agent):**
  1. `knee_motor_overheat` / `knee_motor_weak` is ~4x more likely for calf motors from **supplier lot B** at **hot** sites.
  2. `foot_pad_worn` clusters at `phoenix-solar` (abrasive surface) and wears 2x faster there.
  3. `hip_bolts_loose` recurs on units where the fix was "retightened" (failure) and stops after "retightened with threadlocker" (success).
- For each incident, produce:
  - `incident_id`, `unit_id`, `site`, `timestamp`, `fault_id`, `part_id`, `leg`, `severity`
  - **Telemetry snippet:** run the real sim headless for ~8 s with that fault (or a cheap parametric approximation if sim time is too slow; cache per fault/severity bucket and add noise). Store signal summary + a small CSV.
  - **Anomaly event** (same schema as Section 5.1).
  - **Tech fix note (15 s or less, about how it was fixed, not what went wrong):** short, informal, varied (use Claude with a few-shot prompt: different tech personas, slang, partial info, occasional wrong guesses). Keep lot labels mentioned only sometimes, so the pattern must be mined from `observations` + registry, not read off one note.
  - **Repair record** (via the real skillify extraction prompt, so the dataset exercises the pipeline).
  - **Outcome:** success / failure / recurred after N days.
- Output: `data/synthetic/incidents.jsonl` + `telemetry/` + `ground_truth.json`.

### 8.3 Loader
`python -m server.fleet.load_synthetic` pushes every incident through: GBrain note (synthetic=true), Memorable trace, fleet counters. Idempotent (skips already-loaded `incident_id`s). Leave the **live demo incidents out** of the dataset so the counters move on stage.

---

## 9. Fleet intelligence (`server/fleet/intel.py`)

### 9.1 Counters
Per `part_id`, per site, per supplier lot, per fault type: incident counts, distinct units, recurrence rate, mean time between failures, success rate per fix.

### 9.2 Pattern mining
- Compute failure rate ratios across `supplier_lot`, `site`, `ambient_class`, and "fix used". Flag cells with ratio > 2.5 and at least 8 incidents.
- Ask Claude to write the pattern in one paragraph **only from the computed table** (no invention), with the numbers.
- Write the pattern to GBrain `/fleet/go2/patterns/*.md`.

### 9.3 Flags
Triggers:
- **Three-strike:** 3 incidents on the same `part_id` across 3 distinct units within 7 days -> flag.
- **Pattern:** any mined pattern above threshold -> flag.

Flag card (Engineering tab):
```json
{"flag_id":"flag-012","part_id":"fr.calf.motor","kind":"pattern",
 "summary":"Knee actuators from lot B fail 4.1x more often at hot sites (31 of 44 incidents).",
 "units":["go2-07","go2-12","go2-19"],"evidence_notes":["inc-0512","inc-0433"],
 "suggested_change":"Add a supplier-lot check to replace-knee-motor step 4; quarantine lot B for hot sites.",
 "status":"open"}
```
Buttons: **Approve**, **Assign**, **Dismiss**.

### 9.4 Approve flow
- Updates the procedure step text (e.g. adds "Check the actuator lot label. If lot B at a hot site, replace with lot A or C."), bumps version (`v1.1 · from 31 field reports`), writes the changelog to GBrain, pushes `procedure_updated` over WS.
- Every open tech viewer re-renders the step with the new tip badge on the part.
- The next matching anomaly's alert includes the new fix.

---

## 10. Ops console (laptop, `web/src/ops/`)

Tabs / panels:
1. **Fleet:** grid of 40 units by site, status dots (healthy / alert / in repair). Live sim unit shows the 3D dog animating.
2. **Live robot:** the streamed Go2 with telemetry bars, and the **Inject fault** menu.
3. **Alerts:** anomaly cards: unit, part, signal, and (after learning) "Known issue: ... Proven fix: ... Open procedure". Button sends the deep link to the tech phone (QR code on screen for the demo).
4. **Brain:** live feed of notes (newest first), with provenance and hygiene labels. Filter by part/unit/site.
5. **Engineering:** flags, patterns with the evidence table, approve flow, procedure changelog.
6. **Ask:** question box -> `/ask` -> answer with sources (incident ids, units, techs) + deep link.
7. **Knowledge graph:** force-directed graph (d3) of faults, parts, fix steps, and outcomes from Memorable; edge thickness = successes; failed paths dashed. New fix notes animate in.

Fleet grid and live robot panel must reflect the Section 5.3 states (red / in_repair / fixed) in real time.

Design: dark theme matching the Cadanima deck (near-black background, blue accent `#6aa6ff`-ish, red for alerts), monospace labels. Laptop screen split: left = mirrored phone, right = ops console.

---

## 11. Recall and MCP

### 11.1 `/ask`
- Input: free text. The agent: retrieves from GBrain (part notes, unit notes, patterns), queries Memorable recall, reads current procedure version.
- Output: answer (short), steps, the tip, sources, deep link.

### 11.2 MCP server (`server/mcp/server.py`)
Tools for Claude:
- `get_unit_status(unit_id)`
- `get_part_history(part_id, site?)`
- `get_open_flags()`
- `get_procedure(procedure_id, leg?)` -> steps + link to the 3D viewer
- `explain_anomaly(unit_id)` -> known issue, proven fix, sources

Demo: in the Claude app, "Why does go2-12 keep losing its front-right knee?" -> Claude answers from the brain with a link that opens the 3D procedure.

---

## 12. Build order and ownership

**Hackathon rules (hard constraints):** build using GBrain; no prebuilt projects or forks of existing projects; everything built during hackathon hours. Do NOT import existing Cadanima code (Studio, viewers, MCP servers). Open-source libraries and assets (MuJoCo, three.js, the Menagerie Go2 model) are fine. `sim/go2_fault_sim.py` was written during hackathon hours.

Use **Superset** to run parallel coding agents in separate worktrees: (1) robot and 3D, (2) phone capture, (3) backend and brain, (4) ops console. At the end, spend 5 minutes creating the **Superset page** presenting the project (required for their prize).

**Track A (Ali): robot + 3D + phone**
1. Control run: no-fault sim produces zero events.
2. `faults.py` with at least `knee_motor_weak`, `knee_motor_overheat`, `foot_pad_worn`, `hip_bolts_loose`.
3. `export_go2_gltf.py` -> `go2.glb` with named nodes.
4. `sim_server.py` streaming poses + telemetry + anomaly events.
5. Three.js viewer: pose streaming, picking, highlight, tip badges.
6. Tech view: procedures + capture.

**Track B (Syon, or a second agent): brain + data + ops**
1. Registries (`parts.json`, `fleet.json`).
2. Server skeleton + endpoints + WS hub.
3. Skillify agent (STT, extraction, hygiene) + GBrain adapter + Memorable adapter (+ local fallbacks).
4. Synthetic generator + loader.
5. Fleet intelligence: counters, mining, flags, approve.
6. Ops console panels, Ask, MCP.
7. `skillify-repair` public repo.

**Integration contract (agree first):**
```
POST /events/anomaly   {type, unit_id, part_id, signal, value, threshold, t_sim, fault_signature}
POST /capture          multipart {unit_id, procedure_id, step_id, part_id, incident_id?, audio | text}
GET  /brain?part_id=&unit_id=
GET  /flags            POST /flags/{id}/approve
GET  /procedures/{id}?leg=
POST /ask              {question}
WS   /ws               events: anomaly, unit_status (healthy|red|in_repair|fixed), brain_update, graph_update, flag_raised, procedure_updated
```

### Cut order if behind
1. Faults beyond the first two
2. MCP in the Claude app (keep the Ask box)
3. QM nightly digest
4. Live sim streaming (use recorded replays; keep the Inject menu wired to replays)

**Never cut:** fault -> robot goes red with what went wrong, 15-second fix note, brain note with provenance, Memorable trace, three-strike/pattern flag, approve -> 3D procedure update, second dog alert arriving with the fix.

---

## 13. Demo walkthrough (2:00)

**Setup:** laptop split screen (left: phone mirror, right: ops console). Synthetic history already loaded. Two live units ready: `go2-07` and `go2-12`, both lot B, both at hot sites.

**0:00 to 0:15, hook.** Ops console shows the fleet of 40 dogs.
> "Robots break in the field, and the fix lives in one tech's head. Typing a ticket in 100-degree heat is the last thing they want to do. Everyone here is building brains for agents. We built one for robots."

**0:15 to 0:35, the robot reports what went wrong and goes red.** Live robot panel: `go2-07` doing stand/crouch. Ask a judge to pick a fault, or pick `knee_motor_overheat`, front-right. The knee sags, the knee turns red, the dog's dot on the fleet grid goes red, and the alert reads: "Front-right knee actuator is losing torque under load."
> "No one filed anything. The robot told us what broke."

**0:35 to 0:55, the fix note.** Scan the QR code; the phone opens the knee procedure at step 4 with the red part already selected and the prompt "How did you fix it?" Tap record and speak (under 15 seconds):
> "Swapped the front right knee actuator, old one was lot B and scorching. Recalibrated, ran a stand cycle, holding fine."

Toasts run: saved as memory, added to the knowledge graph. The knee flashes green and the dog stands back up. The note lands in the Brain feed with provenance and **ADDITION** (the SOP never says to check the lot), and the new path animates into the knowledge graph.
> "The robot says what broke. The tech says how they fixed it. Fifteen seconds."

**0:55 to 1:20, the fleet learns.** Engineering tab: the pattern flag appears.
> "Across 500 incidents on 40 dogs, knee actuators from lot B fail four times more at hot sites. No single tech could see that. The fleet could."

Click **Approve**. The procedure step updates to v1.1 on the phone, with the tip pinned on the knee.

**1:20 to 1:45, the payoff.** Inject the same fault on `go2-12`. This time the alert arrives with: known issue, proven fix (from Memorable), and "Open procedure v1.1". Then in the Claude app: "Why does go2-12 keep losing its front-right knee?" and it answers from the brain.
> "Same failure, second robot. This time it showed up with the fix."

**1:45 to 2:00, close.**
> "GBrain is the memory, Memorable is the procedural knowledge graph, QM runs the fleet agent, and we built it in parallel on Superset. Own your robot's intelligence."

**Honesty line if asked:** "The robot is simulated in MuJoCo using Unitree's Go2 model, and the 90-day history is synthetic. The pipeline, capture, brain, traces, and flags are all live."

---

## 14. Sponsor usage (what to say and what is real)

**GBrain: the memory (required).**
- Every fix note is stored as a memory with provenance: what the robot reported, what the tech said, the steps, and who, when, and which dog.
- Notes are organized per part, per dog, and per site. Fleet patterns and procedure changes get written back into it too.
- The Ask box answers from it.
- Their challenge is "automate a tedious task," and maintenance logging is exactly that.

**Memorable: the procedural knowledge graph.**
- Every fix becomes a trace: fault -> part -> fix steps -> outcome, including failed fixes.
- When a new dog breaks, Memorable recalls the proven fix and attaches it to the alert. That's the "second dog arrives with the fix" moment.
- It also powers the knowledge graph view.
- Their challenge is "most interesting use case," and human repairs on robots is a strong one.

**QM: the fleet agent.**
- It hosts the agent that runs on each fix note: transcribe, extract the steps, check against the SOP, then write to GBrain and Memorable.
- Frame it as an extension: a QM agent for a robot fleet that receives robot alerts and pages the tech.
- If it's not wired up by 4:00, run the same code as a plain server task and don't claim it.

**Superset: how you build it.**
- Run parallel coding agents in separate worktrees: robot and 3D, phone capture, backend and brain, ops console.
- Spend 5 minutes at the end making the Superset page for their prize.

**Not used:** River, UFO. The SOP hygiene check runs on Claude.

---

## 15. Likely judge questions

- **"Why not a better form?"** Techs skip forms. Tap and talk takes 15 seconds; the robot's own telemetry fills in the rest.
- **"Who owns the data?"** Each fleet owns its brain as plain files on its own infrastructure. Cross-fleet learning would share only component-level patterns, opt-in.
- **"Is this real?"** Sim robot and synthetic history, live pipeline. Say it plainly.
- **"Does it work beyond robots?"** Same model for any machine: Cadanima already builds 3D procedures for packaging lines and biopharma equipment.

---

## 16. Definition of done

- [ ] No-fault sim run: zero alerts. Fault run: correct `part_id` alert.
- [ ] `go2.glb` loads; node names match; poses stream; tap selects parts.
- [ ] Anomaly turns the robot red with a correct `what_went_wrong`; it stays red until a fix note is saved; then green, and the sim clears the fault.
- [ ] Fix capture works from the phone (15 s auto-stop, voice and text fallback), with the red part pre-selected.
- [ ] The saved fix appears as a memory in GBrain and as a new path in the knowledge graph view.
- [ ] RepairRecord + hygiene label returned; note visible in Brain feed; trace sent to Memorable (or local fallback).
- [ ] Synthetic dataset generated with seed 7 and loaded; hidden lot-B pattern surfaces as a flag without being hard-coded.
- [ ] Approve updates the procedure to v1.1 on the phone live.
- [ ] Second injected fault shows the proven fix and the deep link.
- [ ] Ask box answers with sources; MCP works in the Claude app (or is cut).
- [ ] `skillify-repair` repo is public.
- [ ] Backup screen recording of the full 2-minute run exists.
- [ ] Superset page created.
- [ ] Rehearsed twice.
