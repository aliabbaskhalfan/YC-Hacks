# Contracts

## Repair record

```json
{
  "incident_id": "inc-0512",
  "unit_id": "go2-07",
  "part_id": "fr.calf.motor",
  "what_went_wrong": "Telemetry-derived statement copied exactly.",
  "fix": {
    "steps": ["ordered, stated actions only"],
    "parts_used": [],
    "tools": [],
    "root_cause_per_tech": null,
    "verification": null,
    "tip": null
  },
  "observations": {},
  "confidence": 0.0,
  "missing": []
}
```

`observations` contains structured facts explicitly stated by the technician,
such as `supplier_lot`. Confidence is extraction confidence, not confidence that
the technician's diagnosis is correct.

## Hygiene

```json
{"label":"addition","reason":"One sentence tied to the SOP or prior notes."}
```

## Brain note

The note must distinguish `reported by robot` from `[stated] fix note`, include
the ordered steps and hygiene decision, and end with technician, incident, audio,
and synthetic provenance. Include an incident marker so retries are idempotent.

The caller supplies repair outcome. A failed repair is still written, emits a
failure trace, and must not close the incident or mark the machine healthy.

## Procedural trace

```json
{
  "task": "Go2 anomaly: fr.calf.motor joint_tracking_error at phoenix-solar",
  "steps": [
    {"tool":"diagnose","args":{"signal":"joint_tracking_error","part":"fr.calf.motor"}},
    {"tool":"replace","args":{"part":"fr.calf.motor","description":"swapped the knee actuator"}}
  ],
  "outcome": "success",
  "metadata": {
    "incident_id":"inc-0512",
    "unit_id":"go2-07",
    "site":"phoenix-solar",
    "part_id":"fr.calf.motor"
  }
}
```
