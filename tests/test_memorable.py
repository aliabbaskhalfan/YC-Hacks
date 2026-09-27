from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from server.integrations.memorable import LocalTraceStore, MemorableAdapter
from server.models import HygieneResult, IncidentContext, RepairFix, RepairRecord


class StubMemorable(MemorableAdapter):
    def __init__(self, path: Path) -> None:
        super().__init__(
            local=LocalTraceStore(path),
            api_url="https://example.invalid",
            api_key="test-key",
            environment_id="env-test",
            enabled=True,
            consent="read-write",
            use_local_fallback=True,
        )
        self.requests: list[tuple[str, dict[str, Any]]] = []

    async def _post(self, path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        self.requests.append((path, payload))
        if path == "/v1/extract":
            return {
                "request_id": "request-1",
                "storage": {
                    "status": "stored",
                    "environment_id": "env-test",
                    "procedure_id": payload["session_id"],
                    "version": "version-1",
                },
            }
        return {
            "results": [
                {
                    "slug": "procedure-1",
                    "version": "version-1",
                    "similarity": 0.91,
                    "procedure": {
                        "payload": {
                            "steps": [
                                {"action": "diagnose", "outcome": "success"},
                                {"action": "replace", "command": "replace the actuator"},
                                {"action": "verify", "command": "run the stand cycle"},
                                {"action": "repair_outcome_reported", "outcome": "success"},
                            ]
                        }
                    },
                }
            ]
        }


class MemorableSharedEnvironmentTest(unittest.IsolatedAsyncioTestCase):
    async def test_capture_validates_receipt_and_omits_private_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = StubMemorable(Path(directory) / "traces.jsonl")
            incident = IncidentContext(
                incident_id="PRIVATE-INCIDENT-SENTINEL",
                unit_id="PRIVATE-UNIT-SENTINEL",
                site="PRIVATE-SITE-SENTINEL",
                part_id="fr.calf.motor",
                signal="joint_tracking_error",
                what_went_wrong="tracking error",
            )
            record = RepairRecord(
                incident_id=incident.incident_id,
                unit_id=incident.unit_id,
                part_id=incident.part_id,
                what_went_wrong=incident.what_went_wrong,
                fix=RepairFix(
                    steps=["replace the actuator", "run the stand cycle"],
                    verification="stand cycle passed",
                ),
                confidence=0.9,
            )
            trace = adapter.make_trace(
                record,
                incident,
                HygieneResult(label="addition", reason="new field detail"),
            )

            trace_id, receipt = await adapter.record(trace)

            self.assertEqual("repair:PRIVATE-INCIDENT-SENTINEL", trace_id)
            self.assertEqual("stored", receipt.status)
            payload_text = json.dumps(adapter.requests[0][1])
            self.assertNotIn("PRIVATE-INCIDENT-SENTINEL", payload_text)
            self.assertNotIn("PRIVATE-UNIT-SENTINEL", payload_text)
            self.assertNotIn("PRIVATE-SITE-SENTINEL", payload_text)
            self.assertEqual("env-test", adapter.requests[0][1]["environment_id"])
            self.assertNotIn("result", adapter.requests[0][1]["tool_calls"][0])
            self.assertNotIn("result", adapter.requests[0][1]["tool_calls"][1])
            self.assertEqual(
                {"ok": True}, adapter.requests[0][1]["tool_calls"][-1]["result"]
            )

    async def test_shared_recall_returns_procedure_and_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = StubMemorable(Path(directory) / "traces.jsonl")
            recalled = await adapter.recall("fr.calf.motor", "joint_tracking_error")

            self.assertTrue(recalled.found)
            self.assertEqual("shared", recalled.source)
            self.assertEqual("procedure-1", recalled.procedure_id)
            self.assertEqual("version-1", recalled.version)
            self.assertEqual(["replace the actuator", "run the stand cycle"], recalled.steps)

    async def test_non_admitted_trace_is_reported_as_refused(self) -> None:
        class RefusingMemorable(StubMemorable):
            async def _post(
                self, path: str, payload: dict[str, Any], timeout: float
            ) -> dict[str, Any]:
                return {
                    "request_id": "request-refused",
                    "draft": {"steps": []},
                    "judge": {"admitted": False, "reason": "no_postcondition"},
                }

        with tempfile.TemporaryDirectory() as directory:
            adapter = RefusingMemorable(Path(directory) / "traces.jsonl")
            incident = IncidentContext(
                incident_id="incident-refused",
                unit_id="go2-refused",
                part_id="fr.calf.motor",
                signal="joint_tracking_error",
                what_went_wrong="tracking error",
            )
            record = RepairRecord(
                incident_id=incident.incident_id,
                unit_id=incident.unit_id,
                part_id=incident.part_id,
                what_went_wrong=incident.what_went_wrong,
                fix=RepairFix(steps=["inspect the actuator"]),
                confidence=0.8,
            )
            trace = adapter.make_trace(
                record,
                incident,
                HygieneResult(label="addition", reason="new detail"),
            )

            _, receipt = await adapter.record(trace)

            self.assertEqual("refused", receipt.status)
            self.assertEqual("no_postcondition", receipt.detail)

    async def test_admitted_draft_without_shared_receipt_is_extracted_only(self) -> None:
        class DraftOnlyMemorable(StubMemorable):
            async def _post(
                self, path: str, payload: dict[str, Any], timeout: float
            ) -> dict[str, Any]:
                return {
                    "request_id": "request-draft",
                    "draft": {
                        "session_id": payload["session_id"],
                        "schema_version": "1.1.0",
                        "steps": [{"seq": 1, "action": "verify"}],
                    },
                    "judge": {"admitted": True},
                }

        with tempfile.TemporaryDirectory() as directory:
            adapter = DraftOnlyMemorable(Path(directory) / "traces.jsonl")
            incident = IncidentContext(
                incident_id="incident-draft",
                unit_id="go2-draft",
                part_id="fr.calf.motor",
                signal="joint_tracking_error",
                what_went_wrong="tracking error",
            )
            record = RepairRecord(
                incident_id=incident.incident_id,
                unit_id=incident.unit_id,
                part_id=incident.part_id,
                what_went_wrong=incident.what_went_wrong,
                fix=RepairFix(steps=["run the stand cycle"]),
                confidence=0.8,
            )
            trace = adapter.make_trace(
                record,
                incident,
                HygieneResult(label="addition", reason="new detail"),
            )

            _, receipt = await adapter.record(trace)

            self.assertEqual("extracted", receipt.status)
            self.assertEqual("1.1.0", receipt.version)
            self.assertIn("stored locally", receipt.detail or "")
