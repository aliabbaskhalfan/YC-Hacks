from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    repo_root: Path
    aws_bearer_token_bedrock: str | None
    aws_region: str
    bedrock_model_id: str
    bedrock_speech_model_id: str
    anthropic_api_key: str | None
    anthropic_model: str
    deepgram_api_key: str | None
    gbrain_mcp_url: str | None
    gbrain_mcp_token: str | None
    gbrain_api_key: str | None
    memorable_api_key: str | None
    memorable_api_url: str
    memorable_environment_id: str | None
    memorable_enabled: bool
    memorable_consent: str
    use_local_fallbacks: bool

    @property
    def brain_dir(self) -> Path:
        return self.repo_root / "data" / "brain"

    @property
    def clips_dir(self) -> Path:
        return self.repo_root / "data" / "clips"

    @property
    def traces_path(self) -> Path:
        return self.repo_root / "data" / "memory" / "traces.jsonl"

    @property
    def incidents_path(self) -> Path:
        return self.repo_root / "data" / "runtime" / "incidents.json"


def get_settings(repo_root: Path | None = None) -> Settings:
    root = repo_root or Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env", override=False)
    return Settings(
        repo_root=root,
        aws_bearer_token_bedrock=os.getenv("AWS_BEARER_TOKEN_BEDROCK") or None,
        aws_region=os.getenv("AWS_REGION", "us-east-1"),
        bedrock_model_id=os.getenv(
            "BEDROCK_MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0"
        ),
        bedrock_speech_model_id=os.getenv("BEDROCK_SPEECH_MODEL_ID", "amazon.nova-2-sonic-v1:0"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        deepgram_api_key=os.getenv("DEEPGRAM_API_KEY") or None,
        gbrain_mcp_url=os.getenv("GBRAIN_MCP_URL") or None,
        gbrain_mcp_token=os.getenv("GBRAIN_MCP_TOKEN") or None,
        gbrain_api_key=os.getenv("GBRAIN_API_KEY") or None,
        memorable_api_key=os.getenv("MEMORABLE_API_KEY") or None,
        memorable_api_url=os.getenv(
            "MEMORABLE_API_URL", "https://memorable-extraction-api.memorable.workers.dev"
        ).rstrip("/"),
        memorable_environment_id=os.getenv("MEMORABLE_ENVIRONMENT_ID") or None,
        memorable_enabled=_bool_env("MEMORABLE", False),
        memorable_consent=os.getenv("MEMORABLE_CONSENT", "deny").strip().lower(),
        use_local_fallbacks=_bool_env("USE_LOCAL_FALLBACKS", True),
    )
