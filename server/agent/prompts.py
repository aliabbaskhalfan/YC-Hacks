EXTRACTION_SYSTEM = """You extract a repair record from a short field-tech note.
Return JSON only. Preserve the technician's step order. Never add a step, tool,
part, cause, measurement, or result that the technician did not state. Put
important absent or unclear fields in missing. what_went_wrong is supplied by
robot telemetry and must be copied exactly, never inferred from the note.
Treat root_cause_per_tech as an attributed observation, not established fact."""

HYGIENE_SYSTEM = """Compare a field repair with the current SOP step and prior
notes. Return JSON only with label addition, contradiction, or duplicate and a
one-sentence reason. Use contradiction only for an actual conflict with the SOP;
new detail is an addition. Do not promote a technician's guess to fact."""


def extraction_user(context: dict, transcript: str) -> str:
    return f"""Context:
{context}

Technician transcript:
{transcript}

Required JSON keys: fix.steps, fix.parts_used, fix.tools,
fix.root_cause_per_tech, fix.verification, fix.tip, observations, confidence,
missing.

Use exactly this shape and these value types:
{{
  "fix": {{
    "steps": ["string"],
    "parts_used": ["string"],
    "tools": ["string"],
    "root_cause_per_tech": "string or null",
    "verification": "string or null",
    "tip": "string or null"
  }},
  "observations": {{"key": "value"}},
  "confidence": 0.0,
  "missing": ["field.path"]
}}
confidence must be a JSON number from 0 through 1, never a word. observations
must be a JSON object, never a list. Use an empty object when none were stated."""


def hygiene_user(record_json: str, sop_text: str, prior_notes: str) -> str:
    return f"""Repair record:
{record_json}

Current SOP step:
{sop_text or '[missing]'}

Prior notes for this part:
{prior_notes or '[none]'}"""
