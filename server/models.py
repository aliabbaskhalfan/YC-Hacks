from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RepairFix(BaseModel):
    steps: list[str] = Field(default_factory=list)
    parts_used: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    root_cause_per_tech: str | None = None
    verification: str | None = None
    tip: str | None = None


class RepairRecord(BaseModel):
    incident_id: str
    unit_id: str
    part_id: str
    what_went_wrong: str
    fix: RepairFix
    observations: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    missing: list[str] = Field(default_factory=list)


class HygieneResult(BaseModel):
    label: Literal["addition", "contradiction", "duplicate"]
    reason: str


class Provenance(BaseModel):
    incident_id: str
    unit_id: str
    site: str = "unknown"
    tech: str = "unknown"
    procedure_id: str
    step_id: int
    part_id: str
    audio_path: str | None = None
    transcript: str
    synthetic: bool = False
    captured_at: datetime = Field(default_factory=utc_now)


class IncidentContext(BaseModel):
    incident_id: str
    unit_id: str
    part_id: str
    site: str = "unknown"
    signal: str = "unknown"
    what_went_wrong: str
    fault_signature: dict[str, Any] = Field(default_factory=dict)
    status: Literal["red", "in_repair", "fixed"] = "red"
    known_fix: dict[str, Any] | None = None


class CaptureInput(BaseModel):
    incident_id: str
    unit_id: str
    procedure_id: str
    step_id: int
    part_id: str
    tech: str = "unknown"
    outcome: Literal["success", "failure"] = "success"
    text: str | None = None
    audio_path: str | None = None
    audio_reference: str | None = None
    audio_content_type: str | None = None


class PipelineResult(BaseModel):
    record: RepairRecord
    hygiene: HygieneResult
    transcript: str
    brain_paths: list[str]
    trace_id: str
    receipts: list["IntegrationReceipt"] = Field(default_factory=list)


class IntegrationReceipt(BaseModel):
    provider: Literal["gbrain", "memorable"]
    status: Literal["stored", "extracted", "degraded", "disabled", "refused"]
    environment_id: str | None = None
    procedure_id: str | None = None
    version: str | None = None
    request_id: str | None = None
    detail: str | None = None


class RecallResult(BaseModel):
    found: bool = False
    part_id: str
    signal: str | None = None
    steps: list[str] = Field(default_factory=list)
    successes: int = 0
    failures: int = 0
    incident_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    source: Literal["local", "shared", "none"] = "none"
    procedure_id: str | None = None
    version: str | None = None


class MemoryTrace(BaseModel):
    trace_id: str
    task: str
    steps: list[dict[str, Any]]
    outcome: Literal["success", "failure"]
    metadata: dict[str, Any]
    created_at: datetime = Field(default_factory=utc_now)
