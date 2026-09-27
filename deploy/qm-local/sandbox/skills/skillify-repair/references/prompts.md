# Prompt contracts

## Extraction

Tell the model to return JSON only, preserve stated action order, and never add
steps, tools, parts, causes, measurements, or outcomes. Supply robot context and
the transcript in visibly separate blocks. Require the `RepairRecord` fields in
`contracts.md`. Instruct it to copy `what_went_wrong` from robot context exactly,
attribute technician causes, and list unclear or absent information in `missing`.

Use temperature zero and schema validation. Reject malformed output rather than
quietly inventing defaults for action fields.

## Hygiene

Supply the validated repair record, current SOP step, and relevant existing part
notes. Require JSON containing only `label` and `reason`. Define labels as:

- `duplicate`: actionable knowledge is already covered.
- `contradiction`: an action actually conflicts with the SOP.
- `addition`: useful detail is new but does not conflict.

Instruct the model not to promote a technician's causal guess to fact. Truncate
retrieved notes by relevance or recency before truncating the current record.
