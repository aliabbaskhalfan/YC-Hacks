# Brain integrations

- GBrain notes are written through its authenticated MCP endpoint, then mirrored
  as plain Markdown under `data/brain/fleet/go2/`. Repairs are indexed by part,
  unit, and site; machine-readable provenance lives under
  `data/brain/provenance/`.
- Each completed repair is sent to Memorable's extraction API as a minimized,
  scrubbed tool trace. A response is only called `stored` when it includes a
  complete shared-environment receipt (`environment_id`, `procedure_id`, and
  `version`). The public API currently returns an admitted procedure draft but
  no shared-storage receipt, so that stage is reported as `extracted` and the
  trace is retained idempotently in `data/memory/traces.jsonl`.
- New anomalies attempt shared Memorable recall first and fail softly to the
  local trace store. Local recall ranks matching successful and failed repair
  paths by part and signal; the graph endpoint is also generated locally
  because the hosted API does not expose a corpus-wide graph.
- Claude Haiku 4.5 on Bedrock performs extraction and hygiene checks when
  `AWS_BEARER_TOKEN_BEDROCK` is set.
- Amazon Nova 2 Sonic is the preferred audio path. Its bidirectional API does
  not accept Bedrock bearer API keys, so it additionally requires valid
  standard AWS SigV4 credentials (profile, environment credentials, or an
  attached runtime role). Deepgram remains an optional legacy fallback.

GBrain's MCP envelope and page tools are isolated in `gbrain.py`; every remote
write gets a read-after-write marker check. Memorable's HTTP contract, consent
gate, kill switch, redaction and receipt validation are isolated in
`memorable.py`. With `USE_LOCAL_FALLBACKS=true`, captures remain inspectable if
an optional remote service is unavailable.

The local Quartermaster deployment now lives under `deploy/qm-local`, backed by
the reviewed patched source in `deploy/qm-source-0.1.12`. Its core image pins
Memorable 0.5.31-shared-env.1, preserves QM's factual notebook, performs
supplemental pre-model recall, and enables capture consent only for the actual
authenticated `personal:hackathon` scope. The FastAPI adapter remains the path
that writes Skillify notes to GBrain and sends completed repair traces directly
to the shared environment.
