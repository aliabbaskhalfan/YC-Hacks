from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from server.agent.skillify import SkillifyAgent
from server.integrations.gbrain import GBrainAdapter, LocalBrain
from server.integrations.llm import ClaudeGateway
from server.integrations.memorable import LocalTraceStore, MemorableAdapter
from server.integrations.stt import SpeechToText
from server.models import CaptureInput, IncidentContext
from server.procedures import ProcedureStore


class SkillifyAgentTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        procedure_root = self.root / "procedures"
        procedure_root.mkdir()
        (procedure_root / "replace-knee-motor.json").write_text(
            '{"steps":[{"step_id":4,"text":"Remove the actuator, install the replacement, and reconnect it."}]}'
        )
        brain = GBrainAdapter(LocalBrain(self.root / "brain"), None, None, True)
        memorable = MemorableAdapter(
            LocalTraceStore(self.root / "traces.jsonl"),
            "https://example.invalid",
            None,
            use_local_fallback=True,
        )
        self.agent = SkillifyAgent(
            SpeechToText(None),
            ClaudeGateway(None, "unused"),
            brain,
            memorable,
            ProcedureStore(procedure_root),
        )
        self.brain = brain
        self.memorable = memorable

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_capture_writes_provenance_and_is_recalled(self) -> None:
        incident = IncidentContext(
            incident_id="inc-live-01",
            unit_id="go2-07",
            site="phoenix-solar",
            part_id="fr.calf.motor",
            signal="joint_tracking_error",
            what_went_wrong="Front-right knee actuator is losing torque under load.",
        )
        capture = CaptureInput(
            incident_id=incident.incident_id,
            unit_id=incident.unit_id,
            procedure_id="replace-knee-motor",
            step_id=4,
            part_id=incident.part_id,
            tech="Ali",
            text=(
                "Swapped the front right knee actuator, old one was lot B and scorching. "
                "Recalibrated, ran a stand cycle, holding fine."
            ),
        )

        result = await self.agent.run(capture, incident)

        self.assertEqual("B", result.record.observations["supplier_lot"])
        self.assertEqual("addition", result.hygiene.label)
        self.assertGreaterEqual(len(result.record.fix.steps), 3)
        self.assertEqual(3, len(result.brain_paths))
        self.assertEqual(["degraded", "disabled"], [item.status for item in result.receipts])
        for relative in result.brain_paths:
            note = (self.root / "brain" / relative).read_text()
            self.assertIn("incident:inc-live-01", note)
            self.assertIn("synthetic=false", note)

        recall = await self.memorable.recall("fr.calf.motor", "joint_tracking_error")
        self.assertTrue(recall.found)
        self.assertEqual(1, recall.successes)
        self.assertIn("inc-live-01", recall.incident_ids)

        # A retry must not duplicate the note or procedural trace.
        await self.agent.run(capture, incident)
        part_note = await self.brain.read_part("fr.calf.motor")
        self.assertEqual(1, part_note.count("incident:inc-live-01"))
        recall = await self.memorable.recall("fr.calf.motor", "joint_tracking_error")
        self.assertEqual(1, recall.successes)

    async def test_context_mismatch_is_rejected(self) -> None:
        incident = IncidentContext(
            incident_id="inc-1",
            unit_id="go2-01",
            part_id="fr.calf.motor",
            signal="error",
            what_went_wrong="Motor error.",
        )
        capture = CaptureInput(
            incident_id="inc-1",
            unit_id="go2-02",
            procedure_id="replace-knee-motor",
            step_id=4,
            part_id="fr.calf.motor",
            text="Replaced it.",
        )
        with self.assertRaisesRegex(ValueError, "unit_id"):
            await self.agent.run(capture, incident)
