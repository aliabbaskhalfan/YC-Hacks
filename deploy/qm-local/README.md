# Local Skillify QM

The local hackathon stack runs QM 0.1.12 on Colima with Postgres, the web UI,
the local Docker sandbox, and the reviewed Memorable patches. Open
<http://localhost:8082> and sign in as `hackathon`.

On a fresh clone, bootstrap the pinned QM source and verified patches once:

```sh
./deploy/qm-local/bootstrap.sh
```

```sh
./deploy/qm-local/qm-local.sh status
./deploy/qm-local/qm-local.sh logs core
./deploy/qm-local/qm-local.sh up
./deploy/qm-local/qm-local.sh down
```

The QM harness is deliberately `mock` because this QM release accepts direct
Anthropic, OpenAI, or OpenRouter credentials, not a Bedrock bearer token. The
Machine Brain FastAPI backend continues to use Bedrock Claude Haiku for the
Skillify extraction and hygiene stages.

Memorable is installed inside the core image and bound to the authenticated
`personal:hackathon` scope. Its local consent and factual notebook share QM's
Postgres database; shared procedures use the configured YC Hacks environment.
The Skillify application writes per-part/per-unit notes to GBrain separately.
