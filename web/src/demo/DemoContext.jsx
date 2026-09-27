import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef } from "react";
import { LIVE_UNIT, PIPELINE, RECALL_UNIT, RECORD, REPLAYS, UNITS, WORK_ORDERS } from "./fixtures.js";
import { submitFixNote } from "./api.js";

export const BEATS = [
  { id: "fleet", label: "The problem", at: "0:00" },
  { id: "breaks", label: "It breaks", at: "0:20" },
  { id: "fix", label: "Fix note", at: "0:40" },
  { id: "memory", label: "Procedure + memory", at: "1:00" },
  { id: "recall", label: "Second dog", at: "1:20" },
  { id: "close", label: "Why it matters", at: "1:40" },
];

const healthy = Object.fromEntries(UNITS.map((u) => [u.unit_id, "healthy"]));

let playCounter = 0;
const play = (replay) => ({ replay, playKey: ++playCounter });

// Every beat is a full snapshot, so the presenter can jump to any beat from any state.
function snapshot(beat) {
  const s = {
    beat,
    units: { ...healthy },
    robot: play(REPLAYS.walk),
    workOrders: {},
    techUnit: null,
    fix: { phase: "idle", stage: -1, transcript: null },
    record: null,
  };
  if (beat === 1) s.robot = play(REPLAYS.tripFall);
  if (beat === 2) {
    s.units[LIVE_UNIT] = "red";
    s.robot = play(REPLAYS.fallen);
    s.workOrders[LIVE_UNIT] = "open";
    s.techUnit = LIVE_UNIT;
  }
  if (beat >= 3) {
    s.robot = play(REPLAYS.standUp);
    s.workOrders[LIVE_UNIT] = "closed";
    s.techUnit = LIVE_UNIT;
    s.fix = { phase: "done", stage: PIPELINE.length, transcript: RECORD.fix.transcript };
    s.record = RECORD;
  }
  if (beat >= 4) {
    s.units[RECALL_UNIT] = beat === 4 ? "red" : "in_repair";
    s.robot = play(REPLAYS.fallen);
    s.workOrders[RECALL_UNIT] = "open";
    s.techUnit = RECALL_UNIT;
  }
  return s;
}

function reducer(state, action) {
  switch (action.type) {
    case "beat": {
      const next = snapshot(action.beat);
      // Auto-advancing after a live fix note keeps what the tech actually said.
      return action.keep ? { ...next, record: state.record ?? next.record, fix: state.fix } : next;
    }
    case "impact":
      return {
        ...state,
        units: { ...state.units, [LIVE_UNIT]: "red" },
        workOrders: { ...state.workOrders, [LIVE_UNIT]: "open" },
        techUnit: LIVE_UNIT,
      };
    case "unit":
      return { ...state, units: { ...state.units, [action.unit]: action.status } };
    case "fix":
      return { ...state, fix: { ...state.fix, ...action.fix } };
    case "fixed":
      return {
        ...state,
        units: { ...state.units, [LIVE_UNIT]: "fixed" },
        workOrders: { ...state.workOrders, [LIVE_UNIT]: "closed" },
        robot: play(REPLAYS.standUp),
        record: action.record,
      };
    default:
      return state;
  }
}

const DemoContext = createContext(null);

export function DemoProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, 0, snapshot);
  const timers = useRef([]);
  const later = (ms, fn) => timers.current.push(setTimeout(fn, ms));
  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };

  const goBeat = useCallback((beat) => {
    clearTimers();
    dispatch({ type: "beat", beat: Math.max(0, Math.min(BEATS.length - 1, beat)) });
  }, []);

  const onReplayEvent = useCallback((ev) => {
    if (ev.type === "impact") dispatch({ type: "impact" });
  }, []);

  const startRepair = useCallback((unit) => dispatch({ type: "unit", unit, status: "in_repair" }), []);

  // The tech closed the work order with a fix note: run QM's pipeline, then the dog goes green.
  const submitFix = useCallback(async ({ audio, text } = {}) => {
    clearTimers();
    dispatch({ type: "fix", fix: { phase: "processing", stage: 0, transcript: null } });
    const result = submitFixNote({ workOrder: WORK_ORDERS[LIVE_UNIT], audio, text });
    let at = 0;
    PIPELINE.forEach((stage, i) => {
      at += stage.ms;
      later(at, () => dispatch({ type: "fix", fix: { stage: i + 1 } }));
    });
    const { transcript, record } = await result;
    dispatch({ type: "fix", fix: { transcript } });
    later(at + 150, () => {
      dispatch({ type: "fix", fix: { phase: "done" } });
      dispatch({ type: "fixed", record });
    });
    later(at + 2400, () => dispatch({ type: "unit", unit: LIVE_UNIT, status: "healthy" }));
    later(at + 3600, () => dispatch({ type: "beat", beat: 3, keep: true }));
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.closest?.("input, textarea, [contenteditable]") || e.metaKey || e.ctrlKey) return;
      if (/^[1-6]$/.test(e.key)) goBeat(Number(e.key) - 1);
      else if (e.key === "ArrowRight") goBeat(state.beat + 1);
      else if (e.key === "ArrowLeft") goBeat(state.beat - 1);
      else if (e.key.toLowerCase() === "f" && state.beat === 2 && state.fix.phase === "idle") submitFix();
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goBeat, submitFix, state.beat, state.fix.phase]);

  useEffect(() => clearTimers, []);

  const value = useMemo(
    () => ({ ...state, goBeat, onReplayEvent, startRepair, submitFix }),
    [state, goBeat, onReplayEvent, startRepair, submitFix],
  );
  return <DemoContext.Provider value={value}>{children}</DemoContext.Provider>;
}

export function useDemo() {
  const ctx = useContext(DemoContext);
  if (!ctx) throw new Error("useDemo must be used inside <DemoProvider>");
  return ctx;
}
