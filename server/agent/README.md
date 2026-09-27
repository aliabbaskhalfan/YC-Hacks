# Skillify agent

The working pipeline is `SkillifyAgent.run`:

1. use submitted text or transcribe audio with Amazon Nova 2 Sonic;
2. extract a grounded `RepairRecord` with Claude Haiku on Bedrock
   (deterministic local fallback);
3. label the record `addition`, `contradiction`, or `duplicate` against the SOP
   and existing part notes;
4. append part/unit/site brain notes with provenance;
5. record a Memorable-compatible trace for future incident recall.

Run the backend with `./.superset/run.sh`, then use the OpenAPI UI at
`http://localhost:$API_PORT/docs`. Text captures work without credentials. Live
extraction uses `AWS_BEARER_TOKEN_BEDROCK`. Nova Sonic audio requires standard
AWS SigV4 credentials because Bedrock bearer keys do not authorize
bidirectional streams. `DEEPGRAM_API_KEY` and `ANTHROPIC_API_KEY` are optional
legacy fallbacks.
