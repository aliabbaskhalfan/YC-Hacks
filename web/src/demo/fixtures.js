// Scripted data for every demo beat (Fleetbrain 2-minute script). Each value here is the
// stage fallback for a live call in api.js. Numbers from the sim are labeled "sim value" in the UI.
import fleet from "@data/registry/fleet.json";

export const DEMO_DATE = "2026-09-27";

// The demo tells the go2-02 story in a data center; sf-lab's units play that site on screen.
export const SITE_LABELS = { "sf-lab": "data-center-1" };
export const siteLabel = (site) => SITE_LABELS[site] ?? site;

export const SITES = [...fleet.sites]
  .sort((a, b) => (a.site_id === "sf-lab" ? -1 : b.site_id === "sf-lab" ? 1 : 0))
  .map((s) => ({ ...s, label: siteLabel(s.site_id) }));

export const UNITS = fleet.units.map((u) => ({ unit_id: u.unit_id, site: u.site }));

export const LIVE_UNIT = "go2-02";
export const RECALL_UNIT = "go2-17";
export const COVER_PART = "fr.thigh.cover";
export const COVER_NODE = "FR_hip"; // registry mesh_nodes for fr.thigh.cover

export const REPLAYS = {
  walk: "/replays/go2_walk_loop.json",
  tripFall: "/replays/go2-02_trip_fall.json",
  standUp: "/replays/go2-02_stand_up.json",
  fallen: "/replays/go2_fallen_right.json",
  standing: "/replays/go2_standing.json",
};

export const WHAT_WENT_WRONG = "Hard impact, front-right. Thigh cover likely cracked.";

export const WORK_ORDERS = {
  [LIVE_UNIT]: {
    work_order_id: "wo-0927-01",
    incident_id: "inc-live-01",
    unit_id: LIVE_UNIT,
    site: "data-center-1",
    title: "go2-02, fall, front-right thigh cover potential crack detected",
    cause: "Tripped on a toolbox left in the aisle",
    part_id: COVER_PART,
    opened_at: "16:21",
  },
  [RECALL_UNIT]: {
    work_order_id: "wo-0927-02",
    incident_id: "inc-live-02",
    unit_id: RECALL_UNIT,
    site: "pittsburgh-plant",
    title: "go2-17, fall, front-right thigh cover potential crack detected",
    cause: "Slipped on a wet floor at a construction site",
    part_id: COVER_PART,
    opened_at: "16:24",
  },
};

// The scripted voice note: whatever the tech records, this is the transcript the demo uses.
export const TRANSCRIPT =
  "Hard fall on the right side. I swapped the thigh cover. Seated the lip first, cross pattern, torqued to exactly 1 newton-meter. Any looser than that it rattles, any tighter it cracks easily again.";

// QM's pipeline on the fix note; durations are how long each toast holds in fixture mode.
export const PIPELINE = [
  { id: "transcribe", label: "Transcribing voice note", ms: 1300 },
  { id: "extract", label: "Extracting fix steps", ms: 1400 },
  { id: "sop", label: "Checking against SOP", ms: 1200 },
  { id: "gbrain", label: "Saved to GBrain as a memory", ms: 700 },
  { id: "memorable", label: "Added to the knowledge graph", ms: 700 },
];

export const RECORD = {
  incident_id: "inc-live-01",
  work_order_id: "wo-0927-01",
  unit_id: LIVE_UNIT,
  site: "data-center-1",
  environment: "data center aisle, night inspection round",
  timestamp: "2026-09-27T16:21:00-07:00",
  reported_by_robot: {
    event: "hard_impact",
    cause: "tripped on toolbox in aisle",
    side: "right",
    impact_force_n: 577.1,
    part_id: COVER_PART,
    what_went_wrong: WHAT_WENT_WRONG,
  },
  fix: {
    tech: "tech-01",
    voice_note_audio: "/clips/inc-live-01.webm",
    transcript: TRANSCRIPT,
    action: "replace",
    part_replaced: COVER_PART,
    steps: [
      "remove 4 M3 screws",
      "remove cracked thigh cover",
      "seat the lip in the groove first",
      "install screws in a cross pattern",
      "torque to 1.0 N·m",
    ],
    torque_nm: 1.0,
    failure_modes: { too_loose: "cover rattles", too_tight: "cover cracks easily again" },
    verification: "robot stood back up, no alerts",
    outcome: "success",
  },
  sop_check: {
    result: "addition",
    reason: "SOP does not specify seating the lip first or the torque limit",
  },
  provenance: { source: "field voice note", work_order: "wo-0927-01", synthetic: false },
  knowledge_graph_path: ["hard_impact", COVER_PART, "replace_cover_lip_first_cross_1nm", "success"],
};

// Steps the tech's view and the recall card show; torque and screw counts are sim values.
export const PROCEDURE = {
  procedure_id: "replace-thigh-cover",
  title: "Replace front-right thigh cover",
  source: "From 1 field report · go2-02",
  important: "1 N·m torque",
  // Mirrors server/procedures/replace-thigh-cover.json (what the 4D procedure viewer plays).
  steps: [
    { title: "Remove the 4 M3 cover screws", detail: "Back out the four M3 cover screws with a 2.5 mm hex driver and lift the cover off." },
    { title: "Inspect the motor housing", detail: "If the housing is cracked, stop: that is a motor swap, not a cover swap." },
    { title: "Fit the new cover", detail: "The inner lip drops into the groove before any screw goes in, or it seats crooked." },
    { title: "Torque in a cross pattern to 1.0 N·m", detail: "1 → 3 → 2 → 4, one pass. Looser rattles; tighter cracks the bosses (sim value)." },
  ],
};

// Knowledge graph: fault -> part -> fix -> outcome. Existing paths come from the fleet's history;
// NEW_PATH is the one the live fix note adds.
export const GRAPH_COLUMNS = ["Fault", "Part", "Fix", "Outcome"];
export const GRAPH_NODES = [
  { id: "joint_tracking_error", label: "joint tracking error", col: 0 },
  { id: "foot_slip", label: "foot slip", col: 0 },
  { id: "hip_oscillation", label: "hip oscillation", col: 0 },
  { id: "hard_impact", label: "hard impact", col: 0 },
  { id: "fr.calf.motor", label: "fr.calf.motor", col: 1 },
  { id: "fl.foot.pad", label: "fl.foot.pad", col: 1 },
  { id: "rr.hip.mount_bolts", label: "rr.hip.mount_bolts", col: 1 },
  { id: COVER_PART, label: COVER_PART, col: 1 },
  { id: "replace_knee_actuator", label: "replace knee actuator", col: 2 },
  { id: "replace_foot_pad", label: "replace foot pad", col: 2 },
  { id: "retighten_bolts", label: "retighten bolts", col: 2 },
  { id: "retighten_threadlocker", label: "retighten + threadlocker", col: 2 },
  { id: "replace_cover_lip_first_cross_1nm", label: "lip first · cross · 1 N·m", col: 2 },
  { id: "success", label: "success", col: 3 },
  { id: "failure", label: "recurred", col: 3 },
];
export const GRAPH_EDGES = [
  ["joint_tracking_error", "fr.calf.motor", 23],
  ["fr.calf.motor", "replace_knee_actuator", 23],
  ["replace_knee_actuator", "success", 21],
  ["replace_knee_actuator", "failure", 2],
  ["foot_slip", "fl.foot.pad", 14],
  ["fl.foot.pad", "replace_foot_pad", 14],
  ["replace_foot_pad", "success", 14],
  ["hip_oscillation", "rr.hip.mount_bolts", 11],
  ["rr.hip.mount_bolts", "retighten_bolts", 6],
  ["retighten_bolts", "failure", 6],
  ["rr.hip.mount_bolts", "retighten_threadlocker", 5],
  ["retighten_threadlocker", "success", 5],
];
export const NEW_PATH = RECORD.knowledge_graph_path;

export const CLOSEOUT = {
  crackedCovers: [
    { site: "data-center-1", unit: LIVE_UNIT, how: "tripped on a toolbox", fix: "first report" },
    { site: "pittsburgh-plant", unit: RECALL_UNIT, how: "slipped on a wet floor", fix: "proven fix attached" },
  ],
};
