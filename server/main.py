from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from server.agent.skillify import SkillifyAgent
from server.config import Settings, get_settings
from server.incidents import IncidentStore
from server.integrations.gbrain import GBrainAdapter, LocalBrain
from server.integrations.llm import ModelGateway
from server.integrations.memorable import LocalTraceStore, MemorableAdapter
from server.integrations.stt import SpeechToText, has_standard_aws_credentials
from server.models import CaptureInput
from server.procedures import ProcedureStore

MAX_AUDIO_BYTES = 25 * 1024 * 1024
SUPPORTED_AUDIO_SUFFIXES = {".m4a", ".mp3", ".mp4", ".ogg", ".wav", ".webm"}


class AnomalyEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str = "anomaly"
    incident_id: str | None = None
    unit_id: str
    part_id: str
    site: str = "unknown"
    signal: str
    value: float | None = None
    value_rad: float | None = None
    threshold: float | None = None
    threshold_rad: float | None = None
    t_sim: float | None = None
    what_went_wrong: str | None = None
    fault_signature: dict[str, Any] = Field(default_factory=dict)


class EventHub:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, socket: WebSocket) -> None:
        await socket.accept()
        async with self._lock:
            self.connections.add(socket)

    async def disconnect(self, socket: WebSocket) -> None:
        async with self._lock:
            self.connections.discard(socket)

    async def publish(self, event: dict[str, Any]) -> None:
        stale = []
        for socket in tuple(self.connections):
            try:
                await socket.send_json(event)
            except Exception:
                stale.append(socket)
        for socket in stale:
            await self.disconnect(socket)


class Services:
    def __init__(self, settings: Settings) -> None:
        self.aws_voice_credentials_present = has_standard_aws_credentials()
        local_brain = LocalBrain(settings.brain_dir)
        self.brain = GBrainAdapter(
            local=local_brain,
            base_url=settings.gbrain_mcp_url,
            api_key=settings.gbrain_mcp_token or settings.gbrain_api_key,
            use_local_fallback=settings.use_local_fallbacks,
        )
        local_traces = LocalTraceStore(settings.traces_path)
        self.memorable = MemorableAdapter(
            local=local_traces,
            api_url=settings.memorable_api_url,
            api_key=settings.memorable_api_key,
            environment_id=settings.memorable_environment_id,
            enabled=settings.memorable_enabled,
            consent=settings.memorable_consent,
            use_local_fallback=settings.use_local_fallbacks,
        )
        self.incidents = IncidentStore(settings.incidents_path)
        self.procedures = ProcedureStore(settings.repo_root / "server" / "procedures")
        self.agent = SkillifyAgent(
            stt=SpeechToText(
                settings.deepgram_api_key,
                bedrock_enabled=self.aws_voice_credentials_present,
                aws_region=settings.aws_region,
                bedrock_model_id=settings.bedrock_speech_model_id,
            ),
            llm=ModelGateway(
                settings.anthropic_api_key,
                settings.anthropic_model,
                bedrock_api_key=settings.aws_bearer_token_bedrock,
                bedrock_model_id=settings.bedrock_model_id,
                aws_region=settings.aws_region,
            ),
            brain=self.brain,
            memorable=self.memorable,
            procedures=self.procedures,
        )
        self.events = EventHub()
        self.settings = settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Machine Brain", version="0.1.0")
    services = Services(settings or get_settings())
    app.state.services = services

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "local_fallbacks": services.settings.use_local_fallbacks,
            "anthropic_configured": bool(services.settings.anthropic_api_key),
            "bedrock_configured": bool(services.settings.aws_bearer_token_bedrock),
            "nova_sonic_credentials_present": services.aws_voice_credentials_present,
            "deepgram_configured": bool(services.settings.deepgram_api_key),
            "gbrain_configured": bool(
                services.settings.gbrain_mcp_url and services.settings.gbrain_mcp_token
            ),
            "memorable_configured": bool(
                services.settings.memorable_api_key
                and services.settings.memorable_environment_id
                and services.settings.memorable_enabled
                and services.settings.memorable_consent == "read-write"
            ),
        }

    @app.post("/events/anomaly")
    async def anomaly(event: AnomalyEvent) -> dict[str, Any]:
        recall = await services.memorable.recall(event.part_id, event.signal)
        context = await services.incidents.upsert_anomaly(
            event.model_dump(exclude_none=True),
            recall.model_dump() if recall.found else None,
        )
        payload = {"type": "anomaly", **context.model_dump(mode="json")}
        await services.events.publish(payload)
        await services.events.publish(
            {"type": "unit_status", "unit_id": context.unit_id, "status": "red", "incident_id": context.incident_id}
        )
        return context.model_dump(mode="json")

    @app.post("/capture")
    async def capture(
        unit_id: str = Form(...),
        procedure_id: str = Form(...),
        step_id: int = Form(...),
        part_id: str = Form(...),
        incident_id: str | None = Form(None),
        tech: str = Form("unknown"),
        outcome: str = Form("success"),
        text: str | None = Form(None),
        audio: UploadFile | None = File(None),
    ) -> dict[str, Any]:
        if outcome not in {"success", "failure"}:
            raise HTTPException(status_code=422, detail="outcome must be success or failure")
        incident = await services.incidents.get(incident_id) if incident_id else None
        if not incident:
            incident = await services.incidents.find_open(unit_id, part_id)
        if not incident:
            raise HTTPException(status_code=404, detail="No matching open robot incident")

        audio_path: str | None = None
        if audio:
            safe_incident = "".join(ch for ch in incident.incident_id if ch.isalnum() or ch in {"-", "_"})
            suffix = Path(audio.filename or "capture.webm").suffix.lower() or ".webm"
            if suffix not in SUPPORTED_AUDIO_SUFFIXES:
                raise HTTPException(status_code=415, detail="Unsupported audio file type")
            audio_bytes = await audio.read(MAX_AUDIO_BYTES + 1)
            if len(audio_bytes) > MAX_AUDIO_BYTES:
                raise HTTPException(status_code=413, detail="Audio clip exceeds 25 MiB")
            destination = services.settings.clips_dir / f"{safe_incident}{suffix}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(audio_bytes)
            audio_path = str(destination.relative_to(services.settings.repo_root))

        await services.incidents.set_status(incident.incident_id, "in_repair")
        await services.events.publish(
            {"type": "unit_status", "unit_id": unit_id, "status": "in_repair", "incident_id": incident.incident_id}
        )
        try:
            result = await services.agent.run(
                CaptureInput(
                    incident_id=incident.incident_id,
                    unit_id=unit_id,
                    procedure_id=procedure_id,
                    step_id=step_id,
                    part_id=part_id,
                    tech=tech,
                    outcome=outcome,
                    text=text,
                    audio_path=str(services.settings.repo_root / audio_path) if audio_path else None,
                    audio_reference=f"/{audio_path}" if audio_path else None,
                    audio_content_type=audio.content_type if audio else None,
                ),
                incident,
            )
        except Exception as exc:
            await services.incidents.set_status(incident.incident_id, "red")
            status_code = 422 if isinstance(exc, (ValueError, RuntimeError)) else 502
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

        final_status = "fixed" if outcome == "success" else "red"
        await services.incidents.set_status(incident.incident_id, final_status)
        response = result.model_dump(mode="json")
        await services.events.publish({"type": "brain_update", **response})
        await services.events.publish({"type": "graph_update", "trace_id": result.trace_id})
        await services.events.publish(
            {"type": "unit_status", "unit_id": unit_id, "status": final_status, "incident_id": incident.incident_id}
        )
        return response

    @app.get("/brain")
    async def brain(part_id: str | None = None, unit_id: str | None = None) -> dict[str, Any]:
        return {"notes": await services.brain.query(part_id=part_id, unit_id=unit_id)}

    @app.get("/memory/recall")
    async def recall(part_id: str, signal: str | None = None) -> dict[str, Any]:
        return (await services.memorable.recall(part_id, signal)).model_dump()

    @app.get("/memory/graph")
    async def graph() -> dict[str, Any]:
        return await services.memorable.graph()

    @app.get("/procedures/{procedure_id}")
    async def procedure(procedure_id: str) -> dict[str, Any]:
        try:
            return services.procedures.get(procedure_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Procedure not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.websocket("/ws")
    async def websocket(socket: WebSocket) -> None:
        await services.events.connect(socket)
        try:
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            await services.events.disconnect(socket)

    return app


app = create_app()
