from __future__ import annotations

import json
import re
import asyncio
from typing import Any

import httpx

from server.agent.prompts import EXTRACTION_SYSTEM, HYGIENE_SYSTEM, extraction_user, hygiene_user
from server.models import HygieneResult, IncidentContext, RepairFix, RepairRecord


class ModelGateway:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        bedrock_api_key: str | None = None,
        bedrock_model_id: str = "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        aws_region: str = "us-east-1",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.bedrock_api_key = bedrock_api_key
        self.bedrock_model_id = bedrock_model_id
        self.aws_region = aws_region

    async def _json_message(self, system: str, user: str) -> dict[str, Any]:
        if self.bedrock_api_key:
            text = await asyncio.to_thread(self._bedrock_message, system, user)
            return self._parse_json(text)
        if not self.api_key:
            raise RuntimeError("AWS_BEARER_TOKEN_BEDROCK or ANTHROPIC_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 1400,
                    "temperature": 0,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            response.raise_for_status()
            text = "".join(
                block.get("text", "")
                for block in response.json().get("content", [])
                if block.get("type") == "text"
            )
        return self._parse_json(text)

    def _bedrock_message(self, system: str, user: str) -> str:
        import boto3

        client = boto3.client("bedrock-runtime", region_name=self.aws_region)
        response = client.converse(
            modelId=self.bedrock_model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": 1400, "temperature": 0},
        )
        return "".join(
            block.get("text", "")
            for block in response.get("output", {}).get("message", {}).get("content", [])
            if "text" in block
        )

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError("Model response did not contain a JSON object")
        return json.loads(match.group(0))

    async def extract(self, incident: IncidentContext, transcript: str) -> RepairRecord:
        if self.bedrock_api_key or self.api_key:
            context = {
                "incident_id": incident.incident_id,
                "unit_id": incident.unit_id,
                "part_id": incident.part_id,
                "what_went_wrong": incident.what_went_wrong,
            }
            payload = await self._json_message(EXTRACTION_SYSTEM, extraction_user(context, transcript))
            observations = payload.get("observations")
            if isinstance(observations, list):
                payload["observations"] = {"notes": observations}
            elif not isinstance(observations, dict):
                payload["observations"] = {}
            confidence = payload.get("confidence")
            if isinstance(confidence, str):
                labels = {"low": 0.35, "medium": 0.6, "moderate": 0.6, "high": 0.85}
                payload["confidence"] = labels.get(confidence.strip().lower(), 0.5)
            elif not isinstance(confidence, (int, float)):
                payload["confidence"] = 0.5
            else:
                payload["confidence"] = max(0.0, min(1.0, float(confidence)))
            payload.setdefault("missing", [])
            payload.update(context)
            return RepairRecord.model_validate(payload)
        return self._fallback_extract(incident, transcript)

    async def hygiene(self, record: RepairRecord, sop_text: str, prior_notes: str) -> HygieneResult:
        if self.bedrock_api_key or self.api_key:
            payload = await self._json_message(
                HYGIENE_SYSTEM,
                hygiene_user(record.model_dump_json(), sop_text, prior_notes[-6000:]),
            )
            return HygieneResult.model_validate(payload)
        return self._fallback_hygiene(record, sop_text, prior_notes)

    @staticmethod
    def _fallback_extract(incident: IncidentContext, transcript: str) -> RepairRecord:
        clean = " ".join(transcript.strip().split())
        clauses = [c.strip(" ,") for c in re.split(r"[.;]|\bthen\b", clean, flags=re.I) if c.strip(" ,")]
        action_words = (
            "power", "swap", "replace", "remove", "install", "reconnect", "disconnect",
            "recalibr", "calibr", "run", "ran", "verify", "test", "tighten", "retorque",
            "clean", "inspect", "check", "apply", "reset",
        )
        steps: list[str] = []
        for clause in clauses:
            subclauses = [
                s.strip(" ,")
                for s in re.split(
                    r",\s*(?=(?:powered|swapped|replaced|removed|installed|reconnected|disconnected|"
                    r"recalibrated|calibrated|ran|verified|tested|tightened|retorqued|cleaned|"
                    r"inspected|checked|applied|reset)\b)",
                    clause,
                    flags=re.I,
                )
            ]
            for subclause in subclauses:
                lowered = subclause.lower()
                if any(re.search(rf"\b{word}\w*", lowered) for word in action_words):
                    steps.append(subclause)

        lot_match = re.search(r"\blot\s+([a-z0-9-]+)\b", clean, flags=re.I)
        observations: dict[str, Any] = {}
        if lot_match:
            observations["supplier_lot"] = lot_match.group(1).upper()

        part_terms = [
            term for term in ("knee actuator", "actuator", "foot pad", "encoder", "harness", "battery")
            if term in clean.lower()
        ]
        tool_terms = [term for term in ("torque wrench", "socket", "multimeter", "threadlocker") if term in clean.lower()]
        verification = next(
            (c for c in clauses if re.search(r"\b(verified|tested|ran|holding|no error|working|passed)\b", c, re.I)),
            None,
        )
        root_cause = next(
            (c for c in clauses if re.search(r"\b(old|because|caused|worn|loose|hot|scorching|damaged|failed)\b", c, re.I)),
            None,
        )
        tip = "check the supplier lot label before installing a replacement" if lot_match else None
        missing = []
        if not steps:
            missing.append("fix.steps")
        if not verification:
            missing.append("fix.verification")
        confidence = min(0.92, 0.48 + 0.08 * len(steps) + (0.08 if verification else 0) + (0.05 if observations else 0))
        return RepairRecord(
            incident_id=incident.incident_id,
            unit_id=incident.unit_id,
            part_id=incident.part_id,
            what_went_wrong=incident.what_went_wrong,
            fix=RepairFix(
                steps=steps,
                parts_used=list(dict.fromkeys(part_terms)),
                tools=tool_terms,
                root_cause_per_tech=root_cause,
                verification=verification,
                tip=tip,
            ),
            observations=observations,
            confidence=confidence,
            missing=missing,
        )

    @staticmethod
    def _fallback_hygiene(record: RepairRecord, sop_text: str, prior_notes: str) -> HygieneResult:
        repair_text = " ".join(record.fix.steps + ([record.fix.tip] if record.fix.tip else [])).lower()
        sop = sop_text.lower()
        if re.search(r"\b(skip|bypass|did not|didn't|without)\b", repair_text):
            return HygieneResult(label="contradiction", reason="The repair describes bypassing or omitting an SOP action.")
        repair_tokens = set(re.findall(r"[a-z0-9]+", repair_text)) - {"the", "a", "to", "and", "with"}
        sop_tokens = set(re.findall(r"[a-z0-9]+", sop))
        overlap = len(repair_tokens & sop_tokens) / max(1, len(repair_tokens))
        if repair_text and (repair_text in prior_notes.lower() or overlap >= 0.82):
            return HygieneResult(label="duplicate", reason="The captured repair is already covered by the SOP or an existing part note.")
        return HygieneResult(label="addition", reason="The capture adds field detail that is not present in the current SOP step.")


# Backwards-compatible import while callers migrate to the provider-neutral name.
ClaudeGateway = ModelGateway
