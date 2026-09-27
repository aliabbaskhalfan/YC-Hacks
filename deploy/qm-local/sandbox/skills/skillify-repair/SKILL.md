---
name: skillify-repair
description: Turn a field technician's repair transcript plus machine incident context into a grounded repair record, SOP hygiene decision, provenance note, and procedural-memory trace. Use when capturing or importing completed equipment repairs; do not use it to diagnose an incident without a technician repair statement.
---

# Skillify Repair

Convert a short technician statement into durable machine knowledge without
blurring robot telemetry, technician claims, and agent inference.

## Required inputs

- The transcript exactly as captured.
- Incident, unit, and part IDs.
- The robot's telemetry-derived `what_went_wrong` statement.
- Site, technician, timestamp, procedure, and step provenance when available.
- The current SOP step and existing notes for the affected part.

Read [references/contracts.md](references/contracts.md) for the record, hygiene,
note, and trace schemas. Read [references/prompts.md](references/prompts.md) when
implementing an LLM extractor or hygiene classifier. Consult
[references/example.md](references/example.md) when checking a new integration
or explaining the expected output.

## Workflow

1. Extract the repair actions in the technician's original order. Do not add
   implied safety, calibration, inspection, tool, or verification steps.
2. Copy `what_went_wrong` only from robot context. Treat a technician's cause as
   `root_cause_per_tech`, never as established fact.
3. Put absent or ambiguous material in `missing`. Keep a low confidence when the
   note does not support a reliable action sequence.
4. Compare the result with the current SOP and existing part notes:
   - `duplicate`: the same actionable knowledge already exists.
   - `contradiction`: the captured action actually conflicts with the SOP.
   - `addition`: it contributes useful detail not already covered.
5. Append one idempotent note keyed by incident ID to the part, unit, and site
   memory views. Preserve the verbatim transcript and all provenance.
6. Emit one trace mapping fault signal -> part -> stated steps -> outcome. Include
   failed outcomes; they are knowledge, not records to discard.

Never silently mark a repair successful. Use the supplied outcome or record it
as unknown/missing until verification is available.
