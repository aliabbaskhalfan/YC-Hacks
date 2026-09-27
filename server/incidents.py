from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from server.models import IncidentContext


class IncidentStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    async def upsert_anomaly(self, payload: dict[str, Any], known_fix: dict[str, Any] | None) -> IncidentContext:
        incident_id = payload.get("incident_id") or f"inc-live-{uuid4().hex[:8]}"
        context = IncidentContext(
            incident_id=incident_id,
            unit_id=payload["unit_id"],
            part_id=payload["part_id"],
            site=payload.get("site", "unknown"),
            signal=payload.get("signal", "unknown"),
            what_went_wrong=payload.get("what_went_wrong") or _describe_anomaly(payload),
            fault_signature=payload.get("fault_signature", {}),
            known_fix=known_fix,
        )
        async with self._lock:
            incidents = self._read()
            incidents[incident_id] = context.model_dump(mode="json")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(incidents, indent=2))
        return context

    async def get(self, incident_id: str) -> IncidentContext | None:
        item = self._read().get(incident_id)
        return IncidentContext.model_validate(item) if item else None

    async def find_open(self, unit_id: str, part_id: str) -> IncidentContext | None:
        candidates = [
            IncidentContext.model_validate(item)
            for item in self._read().values()
            if item.get("unit_id") == unit_id and item.get("part_id") == part_id and item.get("status") != "fixed"
        ]
        return candidates[-1] if candidates else None

    async def set_status(self, incident_id: str, status: str) -> IncidentContext:
        async with self._lock:
            incidents = self._read()
            if incident_id not in incidents:
                raise KeyError(incident_id)
            incidents[incident_id]["status"] = status
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(incidents, indent=2))
            return IncidentContext.model_validate(incidents[incident_id])


def _describe_anomaly(payload: dict[str, Any]) -> str:
    part = payload.get("part_id", "A component")
    signal = payload.get("signal", "anomaly")
    value = payload.get("value", payload.get("value_rad"))
    threshold = payload.get("threshold", payload.get("threshold_rad"))
    reading = f" ({value} observed; threshold {threshold})" if value is not None and threshold is not None else ""
    return f"{part} reported {signal}{reading}."
