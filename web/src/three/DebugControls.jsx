import { useState } from "react";

// Every part_id from BUILD_SPEC.md Section 4.2, grouped the same way the
// spec lists them. This panel exists so the 3D pipeline (rig, highlighting,
// the red/repair/fixed state machine) can be built and demoed before the sim
// track's live WS server and the backend's real alert flow exist — it fakes
// exactly the inputs those will eventually provide.
const PART_GROUPS = {
  Motors: ["hip.motor", "thigh.motor", "calf.motor"].flatMap((seg) =>
    ["fl", "fr", "rl", "rr"].map((leg) => `${leg}.${seg}`)
  ),
  Links: ["thigh.link", "calf.link"].flatMap((seg) =>
    ["fl", "fr", "rl", "rr"].map((leg) => `${leg}.${seg}`)
  ),
  Feet: ["fl", "fr", "rl", "rr"].map((leg) => `${leg}.foot.pad`),
  "Hip mounts": ["fl", "fr", "rl", "rr"].map((leg) => `${leg}.hip.mount_bolts`),
  Body: [
    "base.battery",
    "base.imu",
    "base.shell",
    ...["fl", "fr", "rl", "rr"].map((leg) => `${leg}.leg.harness`),
  ],
};
const ALL_PARTS = Object.values(PART_GROUPS).flat();

const STATUS_DOT = {
  healthy: "#4aa8ff",
  red: "#ff3b3b",
  in_repair: "#d99a2b",
  fixed: "#2bd97a",
};

export default function DebugControls({ status, partId, onInject, onOpenForRepair, onMarkFixed, onClear }) {
  const [selected, setSelected] = useState(ALL_PARTS[0]);

  return (
    <div className="debug-panel">
      <div className="debug-row">
        <span className="status-dot" style={{ background: STATUS_DOT[status] }} />
        <span>{status}</span>
        {partId && <span className="debug-dim">({partId})</span>}
      </div>
      <select value={selected} onChange={(e) => setSelected(e.target.value)}>
        {Object.entries(PART_GROUPS).map(([group, ids]) => (
          <optgroup key={group} label={group}>
            {ids.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      <div className="debug-row">
        <button onClick={() => onInject(selected)}>Inject alert</button>
        <button onClick={onOpenForRepair} disabled={status !== "red"}>
          Open for repair
        </button>
        <button onClick={onMarkFixed} disabled={status === "healthy"}>
          Mark fixed
        </button>
        <button onClick={onClear}>Clear</button>
      </div>
    </div>
  );
}
