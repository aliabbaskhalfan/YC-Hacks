from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from server.models import (
    HygieneResult,
    IncidentContext,
    IntegrationReceipt,
    MemoryTrace,
    RecallResult,
    RepairRecord,
)


def _tool_for_step(step: str) -> str:
    lowered = step.lower()
    for needle, tool in (
        ("inspect", "inspect"),
        ("check", "inspect"),
        ("replace", "replace"),
        ("swap", "replace"),
        ("calibr", "calibrate"),
        ("tight", "retorque"),
        ("test", "verify"),
        ("run", "verify"),
        ("power", "power_control"),
    ):
        if needle in lowered:
            return tool
    return "repair_step"


_SECRET_PATTERNS = (
    re.compile(r"\b(?:mk|gbu)_[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bbedrock-api-key-[A-Za-z0-9._~+/=-]{12,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S+"),
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
)


def _scrub(value: str, limit: int = 4000) -> str:
    clean = value.replace("\x00", " ").replace("\r", " ").replace("\n", " ")
    for pattern in _SECRET_PATTERNS:
        clean = pattern.sub("[REDACTED]", clean)
    clean = re.sub(r"/Users/[^/\s]+", "~", clean)
    clean = re.sub(r"/home/[^/\s]+", "~", clean)
    return " ".join(clean.split())[:limit]


class LocalTraceStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.receipts_path = path.with_name(f"{path.stem}.receipts.jsonl")
        self._lock = asyncio.Lock()

    def _read(self) -> list[MemoryTrace]:
        if not self.path.exists():
            return []
        traces = []
        for line in self.path.read_text().splitlines():
            if line.strip():
                traces.append(MemoryTrace.model_validate_json(line))
        return traces

    async def append(self, trace: MemoryTrace) -> str:
        async with self._lock:
            existing = self._read()
            if any(item.trace_id == trace.trace_id for item in existing):
                return trace.trace_id
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as stream:
                stream.write(trace.model_dump_json() + "\n")
        return trace.trace_id

    async def append_receipt(self, trace_id: str, receipt: IntegrationReceipt) -> None:
        async with self._lock:
            self.receipts_path.parent.mkdir(parents=True, exist_ok=True)
            rows = []
            if self.receipts_path.exists():
                rows = [json.loads(line) for line in self.receipts_path.read_text().splitlines() if line]
            row = {"trace_id": trace_id, **receipt.model_dump(exclude_none=True)}
            rows = [item for item in rows if item.get("trace_id") != trace_id]
            rows.append(row)
            self.receipts_path.write_text("".join(json.dumps(item) + "\n" for item in rows))

    async def recall(self, part_id: str, signal: str | None = None) -> RecallResult:
        candidates = [trace for trace in self._read() if trace.metadata.get("part_id") == part_id]
        if signal:
            exact = [trace for trace in candidates if trace.metadata.get("signal") == signal]
            candidates = exact or candidates
        if not candidates:
            return RecallResult(part_id=part_id, signal=signal)

        paths: Counter[tuple[str, ...]] = Counter()
        failures: Counter[tuple[str, ...]] = Counter()
        incidents: dict[tuple[str, ...], list[str]] = {}
        for trace in candidates:
            path = tuple(
                step["args"].get("description", step["tool"])
                for step in trace.steps
                if step["tool"] != "diagnose"
            )
            (paths if trace.outcome == "success" else failures)[path] += 1
            incidents.setdefault(path, []).append(str(trace.metadata.get("incident_id", "unknown")))
        all_paths = set(paths) | set(failures)
        best = max(all_paths, key=lambda path: (paths[path] - failures[path], paths[path], -failures[path]))
        success_count, failure_count = paths[best], failures[best]
        return RecallResult(
            found=success_count > 0,
            part_id=part_id,
            signal=signal,
            steps=list(best),
            successes=success_count,
            failures=failure_count,
            incident_ids=incidents[best],
            confidence=round(success_count / max(1, success_count + failure_count), 3),
            source="local",
        )

    async def graph(self) -> dict[str, list[dict[str, Any]]]:
        nodes: dict[str, dict[str, Any]] = {}
        edges: Counter[tuple[str, str, str]] = Counter()
        for trace in self._read():
            part = str(trace.metadata.get("part_id", "unknown"))
            signal = str(trace.metadata.get("signal", "unknown"))
            chain = [f"fault:{signal}", f"part:{part}"]
            chain.extend(
                f"step:{step['args'].get('description', step['tool'])}"
                for step in trace.steps
                if step["tool"] != "diagnose"
            )
            chain.append(f"outcome:{trace.outcome}")
            for node_id in chain:
                kind, label = node_id.split(":", 1)
                nodes[node_id] = {"id": node_id, "kind": kind, "label": label}
            for source, target in zip(chain, chain[1:]):
                edges[(source, target, trace.outcome)] += 1
        return {
            "nodes": list(nodes.values()),
            "edges": [
                {"source": source, "target": target, "outcome": outcome, "weight": weight}
                for (source, target, outcome), weight in edges.items()
            ],
        }


class MemorableAdapter:
    """Shared-environment capture/recall with a private local fallback."""

    def __init__(
        self,
        local: LocalTraceStore,
        api_url: str,
        api_key: str | None,
        environment_id: str | None = None,
        enabled: bool = False,
        consent: str = "deny",
        use_local_fallback: bool = True,
    ) -> None:
        self.local = local
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.environment_id = environment_id
        self.enabled = enabled
        self.consent = consent
        self.use_local_fallback = use_local_fallback

    @property
    def can_recall_remote(self) -> bool:
        return bool(
            self.enabled
            and self.consent in {"read-only", "read-write"}
            and self.api_key
            and self.environment_id
        )

    @property
    def can_capture_remote(self) -> bool:
        return bool(self.can_recall_remote and self.consent == "read-write")

    @staticmethod
    def make_trace(
        record: RepairRecord,
        incident: IncidentContext,
        hygiene: HygieneResult,
        outcome: str = "success",
    ) -> MemoryTrace:
        steps = [
            {"tool": "diagnose", "args": {"signal": incident.signal, "part": record.part_id}},
            *[
                {"tool": _tool_for_step(step), "args": {"part": record.part_id, "description": step}}
                for step in record.fix.steps
            ],
        ]
        return MemoryTrace(
            trace_id=f"repair:{record.incident_id}",
            task=f"Go2 anomaly: {record.part_id} {incident.signal} at {incident.site}",
            steps=steps,
            outcome="failure" if outcome == "failure" else "success",
            metadata={
                "unit_id": record.unit_id,
                "site": incident.site,
                "incident_id": record.incident_id,
                "part_id": record.part_id,
                "signal": incident.signal,
                "hygiene": hygiene.label,
                "verification": record.fix.verification or "not stated",
            },
        )

    def _remote_payload(self, trace: MemoryTrace) -> dict[str, Any]:
        part = _scrub(str(trace.metadata.get("part_id", "unknown")), 120)
        signal = _scrub(str(trace.metadata.get("signal", "unknown")), 120)
        tool_calls: list[dict[str, Any]] = [
            {
                "name": "diagnose",
                "input": {"query": _scrub(f"signal={signal}; part={part}", 400)},
            }
        ]
        repair_steps = [step for step in trace.steps if step["tool"] != "diagnose"]
        for index, step in enumerate(repair_steps):
            if step["tool"] == "diagnose":
                continue
            description = _scrub(str(step.get("args", {}).get("description", step["tool"])))
            call: dict[str, Any] = {
                "name": _scrub(str(step["tool"]), 60),
                "input": {"command": description},
            }
            # The caller explicitly supplies the completed repair outcome. Attach it only
            # to the final observed repair/verification action; never invent outcomes for
            # intermediate steps.
            if index == len(repair_steps) - 1:
                call["result"] = {"ok": trace.outcome == "success"}
            tool_calls.append(call)
        opaque_id = hashlib.sha256(
            f"{self.environment_id}:{trace.trace_id}".encode("utf-8")
        ).hexdigest()[:32]
        return {
            "session_id": f"machine-brain-{opaque_id}",
            "workflow_id": f"machine-brain-{opaque_id}",
            "environment_id": self.environment_id,
            "task_description": _scrub(
                f"project=machine-brain; repair part={part} after signal={signal}; "
                f"reported_outcome={trace.outcome}",
                200,
            ),
            "harness": "machine-brain",
            "skip_embedding": False,
            "tool_calls": tool_calls,
        }

    async def _post(self, path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        assert self.api_key
        last_error: Exception | None = None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        async with httpx.AsyncClient(timeout=None) as client:
            for attempt in range(3):
                try:
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        raise TimeoutError("Memorable request deadline exceeded")
                    response = await client.post(
                        f"{self.api_url}{path}",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                        timeout=remaining,
                    )
                    response.raise_for_status()
                    body = response.json()
                    if not isinstance(body, dict):
                        raise RuntimeError("Memorable returned a non-object response")
                    return body
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    status = exc.response.status_code
                    if status != 429 and status < 500:
                        break
                except (httpx.HTTPError, ValueError, RuntimeError, TimeoutError) as exc:
                    last_error = exc
                if attempt < 2:
                    delay = min(0.25 * (2**attempt), max(0.0, deadline - loop.time()))
                    if delay:
                        await asyncio.sleep(delay)
        raise RuntimeError(f"Memorable request failed: {type(last_error).__name__}")

    async def record(self, trace: MemoryTrace) -> tuple[str, IntegrationReceipt]:
        if self.use_local_fallback:
            await self.local.append(trace)

        if not self.can_capture_remote:
            status = "disabled" if not self.enabled or self.consent != "read-write" else "degraded"
            receipt = IntegrationReceipt(
                provider="memorable",
                status=status,
                environment_id=self.environment_id,
                detail="shared capture is disabled or incompletely configured",
            )
            if self.use_local_fallback:
                await self.local.append_receipt(trace.trace_id, receipt)
            return trace.trace_id, receipt

        try:
            body = await self._post("/v1/extract", self._remote_payload(trace), timeout=120)
            judge = body.get("judge") or {}
            if body.get("refused") or judge.get("admitted") is False:
                receipt = IntegrationReceipt(
                    provider="memorable",
                    status="refused",
                    environment_id=self.environment_id,
                    request_id=body.get("request_id"),
                    detail=_scrub(
                        str(body.get("refused") or judge.get("reason") or "not admitted"),
                        200,
                    ),
                )
            else:
                storage = body.get("storage") or {}
                if not storage and isinstance(body.get("draft"), dict):
                    draft = body["draft"]
                    if not draft.get("steps"):
                        raise RuntimeError("Memorable returned an empty procedure draft")
                    receipt = IntegrationReceipt(
                        provider="memorable",
                        status="extracted",
                        environment_id=self.environment_id,
                        procedure_id=str(draft.get("session_id") or trace.trace_id),
                        version=str(draft.get("schema_version") or "draft"),
                        request_id=body.get("request_id"),
                        detail=(
                            "procedure extracted remotely and trace stored locally; "
                            "shared storage receipt was not returned"
                        ),
                    )
                elif (
                    storage.get("status") != "stored"
                    or storage.get("environment_id") != self.environment_id
                    or not storage.get("procedure_id")
                    or not storage.get("version")
                ):
                    raise RuntimeError("Memorable did not return a complete stored receipt")
                else:
                    receipt = IntegrationReceipt(
                        provider="memorable",
                        status="stored",
                        environment_id=storage["environment_id"],
                        procedure_id=storage["procedure_id"],
                        version=storage["version"],
                        request_id=body.get("request_id"),
                    )
        except Exception as exc:
            receipt = IntegrationReceipt(
                provider="memorable",
                status="degraded",
                environment_id=self.environment_id,
                detail=f"shared capture failed: {type(exc).__name__}",
            )
            if not self.use_local_fallback:
                raise

        if self.use_local_fallback:
            await self.local.append_receipt(trace.trace_id, receipt)
        return trace.trace_id, receipt

    async def _remote_recall(self, part_id: str, signal: str | None) -> RecallResult:
        query = _scrub(f"project=machine-brain repair part={part_id} signal={signal or 'unknown'}", 500)
        body = await self._post(
            "/v1/recall",
            {"query": query, "environment_id": self.environment_id},
            timeout=15,
        )
        results = body.get("results") or []
        if not results:
            return RecallResult(part_id=part_id, signal=signal)
        top = results[0]
        procedure = top.get("procedure") or {}
        payload = procedure.get("payload") or {}
        procedure_steps = payload.get("steps") or []
        steps = []
        successes = 0
        failures = 0
        for step in procedure_steps:
            action = str(step.get("action", ""))
            if action == "diagnose":
                continue
            if step.get("outcome") == "success":
                successes += 1
            elif step.get("outcome") == "failure":
                failures += 1
            if action == "repair_outcome_reported":
                continue
            value = step.get("command") or action
            if value:
                steps.append(str(value))
        similarity = top.get("similarity")
        confidence = float(similarity) if isinstance(similarity, (int, float)) else 0.0
        return RecallResult(
            found=bool(steps and successes > 0),
            part_id=part_id,
            signal=signal,
            steps=steps,
            successes=successes,
            failures=failures,
            confidence=max(0.0, min(1.0, confidence)),
            source="shared",
            procedure_id=str(top.get("slug")) if top.get("slug") else None,
            version=str(top.get("version")) if top.get("version") else None,
        )

    async def recall(self, part_id: str, signal: str | None = None) -> RecallResult:
        if self.can_recall_remote:
            try:
                remote = await self._remote_recall(part_id, signal)
                if remote.found:
                    return remote
            except Exception:
                pass
        if self.use_local_fallback:
            return await self.local.recall(part_id, signal)
        return RecallResult(part_id=part_id, signal=signal)

    async def graph(self) -> dict[str, list[dict[str, Any]]]:
        # The shared API exposes ranked recall rather than corpus-wide graph export.
        # The private local trace corpus remains the graph source.
        return await self.local.graph()
