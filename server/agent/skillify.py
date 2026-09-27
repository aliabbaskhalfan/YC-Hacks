from __future__ import annotations

from server.integrations.gbrain import GBrainAdapter
from server.integrations.llm import ClaudeGateway
from server.integrations.memorable import MemorableAdapter
from server.integrations.stt import SpeechToText
from server.models import CaptureInput, IncidentContext, PipelineResult, Provenance
from server.procedures import ProcedureStore


class SkillifyAgent:
    """Transcribe -> extract -> hygiene -> durable memory writes."""

    def __init__(
        self,
        stt: SpeechToText,
        llm: ClaudeGateway,
        brain: GBrainAdapter,
        memorable: MemorableAdapter,
        procedures: ProcedureStore,
    ) -> None:
        self.stt = stt
        self.llm = llm
        self.brain = brain
        self.memorable = memorable
        self.procedures = procedures

    async def run(self, capture: CaptureInput, incident: IncidentContext) -> PipelineResult:
        self._validate_context(capture, incident)
        transcript = (capture.text or "").strip()
        if not transcript and capture.audio_path:
            transcript = (await self.stt.transcribe(capture.audio_path, capture.audio_content_type)).text
        if not transcript:
            raise ValueError("A non-empty text note or audio clip is required")

        record = await self.llm.extract(incident, transcript)
        sop_text = self.procedures.step_text(capture.procedure_id, capture.step_id)
        prior_notes = await self.brain.read_part(capture.part_id)
        hygiene = await self.llm.hygiene(record, sop_text, prior_notes)
        provenance = Provenance(
            incident_id=incident.incident_id,
            unit_id=incident.unit_id,
            site=incident.site,
            tech=capture.tech,
            procedure_id=capture.procedure_id,
            step_id=capture.step_id,
            part_id=capture.part_id,
            audio_path=capture.audio_reference or capture.audio_path,
            transcript=transcript,
        )
        brain_paths, brain_receipt = await self.brain.append_repair(record, hygiene, provenance)
        trace = self.memorable.make_trace(record, incident, hygiene, outcome=capture.outcome)
        trace_id, memory_receipt = await self.memorable.record(trace)
        return PipelineResult(
            record=record,
            hygiene=hygiene,
            transcript=transcript,
            brain_paths=brain_paths,
            trace_id=trace_id,
            receipts=[brain_receipt, memory_receipt],
        )

    @staticmethod
    def _validate_context(capture: CaptureInput, incident: IncidentContext) -> None:
        mismatches = []
        for field in ("incident_id", "unit_id", "part_id"):
            if getattr(capture, field) != getattr(incident, field):
                mismatches.append(field)
        if mismatches:
            raise ValueError(f"Capture does not match incident: {', '.join(mismatches)}")
