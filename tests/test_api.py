from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server.config import Settings
from server.main import create_app


class ApiFlowTest(unittest.TestCase):
    def test_anomaly_capture_and_recall_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            procedure_dir = root / "server" / "procedures"
            procedure_dir.mkdir(parents=True)
            (procedure_dir / "replace-knee-motor.json").write_text(
                '{"procedure_id":"replace-knee-motor","steps":[{"step_id":4,"text":"Remove and replace the actuator."}]}'
            )
            settings = Settings(
                repo_root=root,
                aws_bearer_token_bedrock=None,
                aws_region="us-east-1",
                bedrock_model_id="unused",
                bedrock_speech_model_id="unused",
                anthropic_api_key=None,
                anthropic_model="unused",
                deepgram_api_key=None,
                gbrain_mcp_url=None,
                gbrain_mcp_token=None,
                gbrain_api_key=None,
                memorable_api_key=None,
                memorable_api_url="https://example.invalid",
                memorable_environment_id=None,
                memorable_enabled=False,
                memorable_consent="deny",
                use_local_fallbacks=True,
            )
            with TestClient(create_app(settings)) as client:
                anomaly = client.post(
                    "/events/anomaly",
                    json={
                        "incident_id": "inc-api-1",
                        "unit_id": "go2-07",
                        "site": "phoenix-solar",
                        "part_id": "fr.calf.motor",
                        "signal": "joint_tracking_error",
                        "what_went_wrong": "Front-right knee actuator lost torque.",
                    },
                )
                self.assertEqual(200, anomaly.status_code)
                self.assertIsNone(anomaly.json()["known_fix"])

                capture = client.post(
                    "/capture",
                    data={
                        "incident_id": "inc-api-1",
                        "unit_id": "go2-07",
                        "procedure_id": "replace-knee-motor",
                        "step_id": "4",
                        "part_id": "fr.calf.motor",
                        "tech": "Ali",
                        "text": "Replaced the knee actuator. Ran the stand cycle and it passed.",
                    },
                )
                self.assertEqual(200, capture.status_code, capture.text)
                self.assertEqual("repair:inc-api-1", capture.json()["trace_id"])

                recall = client.get(
                    "/memory/recall",
                    params={"part_id": "fr.calf.motor", "signal": "joint_tracking_error"},
                )
                self.assertTrue(recall.json()["found"])
                self.assertEqual(1, recall.json()["successes"])

                learned = client.post(
                    "/events/anomaly",
                    json={
                        "incident_id": "inc-api-2",
                        "unit_id": "go2-12",
                        "site": "houston-port",
                        "part_id": "fr.calf.motor",
                        "signal": "joint_tracking_error",
                        "what_went_wrong": "Front-right knee actuator lost torque.",
                    },
                )
                self.assertTrue(learned.json()["known_fix"]["found"])
                self.assertEqual(1, learned.json()["known_fix"]["successes"])

    def test_capture_rejects_unsupported_audio_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            procedure_dir = root / "server" / "procedures"
            procedure_dir.mkdir(parents=True)
            (procedure_dir / "replace-knee-motor.json").write_text(
                '{"procedure_id":"replace-knee-motor","steps":[{"step_id":4,"text":"Replace it."}]}'
            )
            settings = Settings(
                repo_root=root,
                aws_bearer_token_bedrock=None,
                aws_region="us-east-1",
                bedrock_model_id="unused",
                bedrock_speech_model_id="unused",
                anthropic_api_key=None,
                anthropic_model="unused",
                deepgram_api_key=None,
                gbrain_mcp_url=None,
                gbrain_mcp_token=None,
                gbrain_api_key=None,
                memorable_api_key=None,
                memorable_api_url="https://example.invalid",
                memorable_environment_id=None,
                memorable_enabled=False,
                memorable_consent="deny",
                use_local_fallbacks=True,
            )
            with TestClient(create_app(settings)) as client:
                client.post(
                    "/events/anomaly",
                    json={
                        "incident_id": "inc-upload-1",
                        "unit_id": "go2-upload",
                        "part_id": "fr.calf.motor",
                        "signal": "tracking_error",
                        "what_went_wrong": "Tracking error.",
                    },
                )
                response = client.post(
                    "/capture",
                    data={
                        "incident_id": "inc-upload-1",
                        "unit_id": "go2-upload",
                        "procedure_id": "replace-knee-motor",
                        "step_id": "4",
                        "part_id": "fr.calf.motor",
                    },
                    files={"audio": ("capture.exe", b"not audio", "application/octet-stream")},
                )

                self.assertEqual(415, response.status_code)
                self.assertFalse((root / "data" / "clips").exists())

    def test_failed_repair_is_negative_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            procedure_dir = root / "server" / "procedures"
            procedure_dir.mkdir(parents=True)
            (procedure_dir / "retorque-hip-mount.json").write_text(
                '{"procedure_id":"retorque-hip-mount","steps":[{"step_id":2,"text":"Retorque the mount."}]}'
            )
            settings = Settings(
                repo_root=root,
                aws_bearer_token_bedrock=None,
                aws_region="us-east-1",
                bedrock_model_id="unused",
                bedrock_speech_model_id="unused",
                anthropic_api_key=None,
                anthropic_model="unused",
                deepgram_api_key=None,
                gbrain_mcp_url=None,
                gbrain_mcp_token=None,
                gbrain_api_key=None,
                memorable_api_key=None,
                memorable_api_url="https://example.invalid",
                memorable_environment_id=None,
                memorable_enabled=False,
                memorable_consent="deny",
                use_local_fallbacks=True,
            )
            with TestClient(create_app(settings)) as client:
                client.post(
                    "/events/anomaly",
                    json={
                        "incident_id": "inc-failed-1", "unit_id": "go2-09", "part_id": "fr.hip.mount_bolts",
                        "signal": "hip_error_oscillation", "what_went_wrong": "Hip mount oscillation detected."
                    },
                )
                capture = client.post(
                    "/capture",
                    data={
                        "incident_id": "inc-failed-1", "unit_id": "go2-09",
                        "procedure_id": "retorque-hip-mount", "step_id": "2",
                        "part_id": "fr.hip.mount_bolts", "outcome": "failure",
                        "text": "Retightened the hip bolts but the fault came back."
                    },
                )
                self.assertEqual(200, capture.status_code, capture.text)
                recall = client.get("/memory/recall", params={"part_id": "fr.hip.mount_bolts"}).json()
                self.assertFalse(recall["found"])
                self.assertEqual(1, recall["failures"])
