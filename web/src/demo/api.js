// One function per backend call. Fixture data answers unless VITE_LIVE=1; a failed live call
// falls back to the fixture so the stage flow never blocks.
import { RECORD, TRANSCRIPT } from "./fixtures.js";

const LIVE = import.meta.env.VITE_LIVE === "1";
const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function post(path, body, ms = 12000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    const res = await fetch(`${API}${path}`, { method: "POST", body, signal: ctrl.signal });
    if (!res.ok) throw new Error(`${path} ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

// POST /capture (BUILD_SPEC Section 12): closes the incident with the tech's fix note.
export async function submitFixNote({ workOrder, audio, text }) {
  if (LIVE) {
    try {
      const form = new FormData();
      form.set("incident_id", workOrder.incident_id);
      form.set("unit_id", workOrder.unit_id);
      form.set("part_id", workOrder.part_id);
      form.set("procedure_id", "replace-thigh-cover");
      if (audio) form.set("audio", audio, `${workOrder.incident_id}.webm`);
      if (text) form.set("text", text);
      const res = await post("/capture", form);
      return { transcript: res.record?.fix?.transcript ?? text ?? "", record: res.record ?? res, live: true };
    } catch (err) {
      console.warn("submitFixNote: live call failed, using fixture", err);
    }
  }
  const transcript = text?.trim() || TRANSCRIPT;
  return { transcript, record: { ...RECORD, fix: { ...RECORD.fix, transcript } }, live: false };
}
