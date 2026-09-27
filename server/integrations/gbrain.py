from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from server.models import HygieneResult, IntegrationReceipt, Provenance, RepairRecord


def _safe_segment(value: str) -> str:
    safe = "".join(ch for ch in value.lower() if ch.isalnum() or ch in {"-", ".", "_"})
    if not safe or safe in {".", ".."}:
        raise ValueError(f"Unsafe brain path segment: {value!r}")
    return safe


class GBrainToolError(RuntimeError):
    pass


class GBrainMCP:
    """Minimal MCP 2025-06-18 streamable-HTTP client for GBrain."""

    def __init__(self, url: str, token: str) -> None:
        self.url = url
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self.client = httpx.AsyncClient(timeout=30, follow_redirects=True)
        self._request_id = 0

    @staticmethod
    def _decode(response: httpx.Response) -> dict[str, Any]:
        response.raise_for_status()
        if "text/event-stream" in response.headers.get("content-type", ""):
            events = [
                json.loads(line[5:].strip())
                for line in response.text.splitlines()
                if line.startswith("data:")
            ]
            return events[-1] if events else {}
        return response.json() if response.content else {}

    async def __aenter__(self) -> "GBrainMCP":
        payload = await self._request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "machine-brain", "version": "0.1.0"},
            },
        )
        if not payload.get("result"):
            raise GBrainToolError("GBrain MCP initialization failed")
        await self.client.post(
            self.url,
            headers=self.headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if "Mcp-Session-Id" in self.headers:
            try:
                await self.client.delete(self.url, headers=self.headers)
            except httpx.HTTPError:
                pass
        await self.client.aclose()

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._request_id += 1
        response = await self.client.post(
            self.url,
            headers=self.headers,
            json={"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params},
        )
        session_id = response.headers.get("mcp-session-id")
        if session_id:
            self.headers["Mcp-Session-Id"] = session_id
        payload = self._decode(response)
        if payload.get("error"):
            raise GBrainToolError(str(payload["error"].get("message", "GBrain MCP error")))
        return payload

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        payload = await self._request("tools/call", {"name": name, "arguments": arguments})
        result = payload.get("result", {})
        text = "\n".join(
            block.get("text", "")
            for block in result.get("content", [])
            if block.get("type") == "text"
        ).strip()
        if result.get("isError"):
            raise GBrainToolError(text or f"GBrain tool {name} failed")
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"text": text}


class LocalBrain:
    """Plain-file GBrain mirror. Notes remain owned, readable, and portable."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._lock = asyncio.Lock()

    def paths_for(self, provenance: Provenance) -> list[Path]:
        return [
            self.root / "fleet" / "go2" / "parts" / f"{_safe_segment(provenance.part_id)}.md",
            self.root / "fleet" / "go2" / "units" / f"{_safe_segment(provenance.unit_id)}.md",
            self.root / "fleet" / "go2" / "sites" / f"{_safe_segment(provenance.site)}.md",
        ]

    @staticmethod
    def render(record: RepairRecord, hygiene: HygieneResult, provenance: Provenance) -> str:
        captured = provenance.captured_at.isoformat(timespec="minutes")
        transcript = provenance.transcript.replace('"', "'").replace("\n", " ")
        steps = " -> ".join(record.fix.steps) or "not captured"
        observations = ", ".join(f"{key}={value}" for key, value in record.observations.items()) or "none"
        return (
            f"\n<!-- incident:{provenance.incident_id} -->\n"
            f"## {captured} · {provenance.unit_id} · {provenance.site} · "
            f"{provenance.procedure_id} step {provenance.step_id}\n"
            f"- reported by robot: {record.what_went_wrong}\n"
            f"- [stated] fix note: \"{transcript}\"\n"
            f"- fix steps: {steps}\n"
            f"- parts used: {', '.join(record.fix.parts_used) or 'not stated'}\n"
            f"- tools: {', '.join(record.fix.tools) or 'not stated'}\n"
            f"- root cause (tech): {record.fix.root_cause_per_tech or 'not stated'}\n"
            f"- verification: {record.fix.verification or 'not stated'}\n"
            f"- tip: {record.fix.tip or 'none'}\n"
            f"- observations: {observations}\n"
            f"- hygiene: {hygiene.label.upper()} ({hygiene.reason})\n"
            f"- source: tech={provenance.tech}, incident={provenance.incident_id}, "
            f"audio={provenance.audio_path or 'none'}, synthetic={str(provenance.synthetic).lower()}\n"
        )

    async def append_repair(self, record: RepairRecord, hygiene: HygieneResult, provenance: Provenance) -> list[str]:
        note = self.render(record, hygiene, provenance)
        marker = f"<!-- incident:{provenance.incident_id} -->"
        written: list[str] = []
        async with self._lock:
            for path in self.paths_for(provenance):
                path.parent.mkdir(parents=True, exist_ok=True)
                current = path.read_text() if path.exists() else f"# {_safe_segment(path.stem)}\n"
                if marker not in current:
                    path.write_text(current.rstrip() + "\n" + note)
                written.append(str(path.relative_to(self.root)))
            provenance_path = self.root / "provenance" / f"{_safe_segment(provenance.incident_id)}.json"
            provenance_path.parent.mkdir(parents=True, exist_ok=True)
            provenance_path.write_text(provenance.model_dump_json(indent=2))
        return written

    async def read_part(self, part_id: str) -> str:
        path = self.root / "fleet" / "go2" / "parts" / f"{_safe_segment(part_id)}.md"
        return path.read_text() if path.exists() else ""

    async def query(self, part_id: str | None = None, unit_id: str | None = None) -> list[dict[str, str]]:
        candidates: list[Path] = []
        if part_id:
            candidates.append(self.root / "fleet" / "go2" / "parts" / f"{_safe_segment(part_id)}.md")
        if unit_id:
            candidates.append(self.root / "fleet" / "go2" / "units" / f"{_safe_segment(unit_id)}.md")
        if not candidates:
            candidates = list((self.root / "fleet" / "go2" / "parts").glob("*.md")) if self.root.exists() else []
        return [
            {"path": str(path.relative_to(self.root)), "content": path.read_text()}
            for path in candidates
            if path.exists()
        ]


class GBrainAdapter:
    """Writes repair pages through GBrain MCP and mirrors them locally."""

    def __init__(
        self,
        local: LocalBrain,
        base_url: str | None,
        api_key: str | None,
        use_local_fallback: bool = True,
    ) -> None:
        self.local = local
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        self.use_local_fallback = use_local_fallback
        self._remote_lock = asyncio.Lock()

    @staticmethod
    def _slug(path: str) -> str:
        return path.removesuffix(".md")

    @staticmethod
    def _new_page(slug: str) -> str:
        title = slug.rsplit("/", 1)[-1]
        return (
            "---\n"
            f"title: {title}\n"
            "source: machine-brain\n"
            "---\n\n"
            f"# {title}\n"
        )

    async def _append_remote(self, paths: list[str], note: str, incident_id: str) -> None:
        if not self.base_url or not self.api_key:
            raise RuntimeError("GBRAIN_MCP_URL and GBRAIN_MCP_TOKEN are required for remote writes")
        marker = f"<!-- incident:{incident_id} -->"
        async with self._remote_lock, GBrainMCP(self.base_url, self.api_key) as mcp:
            incident_slug = f"fleet/go2/incidents/{_safe_segment(incident_id)}"
            incident_content = self._new_page(incident_slug).rstrip() + "\n" + note
            await mcp.call("put_page", {"slug": incident_slug, "content": incident_content})
            for path in paths:
                slug = self._slug(path)
                try:
                    page = await mcp.call("get_page", {"slug": slug, "include_content": True})
                    content = str(page.get("content") or self._new_page(slug))
                except GBrainToolError as exc:
                    if "not_found" not in str(exc).lower() and "not found" not in str(exc).lower():
                        raise
                    content = self._new_page(slug)
                if marker not in content:
                    content = content.rstrip() + "\n" + note
                    await mcp.call("put_page", {"slug": slug, "content": content})
            for slug in [incident_slug, *(self._slug(path) for path in paths)]:
                page = await mcp.call("get_page", {"slug": slug, "include_content": True})
                if marker not in str(page.get("content", "")):
                    raise GBrainToolError(f"GBrain read-after-write verification failed for {slug}")

    async def append_repair(
        self, record: RepairRecord, hygiene: HygieneResult, provenance: Provenance
    ) -> tuple[list[str], IntegrationReceipt]:
        note = self.local.render(record, hygiene, provenance)
        paths = [str(path.relative_to(self.local.root)) for path in self.local.paths_for(provenance)]
        remote_error: Exception | None = None
        if self.base_url and self.api_key:
            for attempt in range(3):
                try:
                    await self._append_remote(paths, note, provenance.incident_id)
                    remote_error = None
                    break
                except Exception as exc:  # preserve capture when the sponsor API is unavailable
                    remote_error = exc
                    if attempt < 2:
                        await asyncio.sleep(0.25 * (2**attempt))
        receipt = IntegrationReceipt(
            provider="gbrain",
            status="stored" if self.base_url and self.api_key and remote_error is None else "degraded",
            procedure_id=f"fleet/go2/incidents/{_safe_segment(provenance.incident_id)}",
            detail=(f"remote write failed: {type(remote_error).__name__}" if remote_error else None),
        )
        if self.use_local_fallback:
            return await self.local.append_repair(record, hygiene, provenance), receipt
        if remote_error:
            raise remote_error
        if not self.base_url or not self.api_key:
            raise RuntimeError(
                "GBRAIN_MCP_URL and GBRAIN_MCP_TOKEN are required when USE_LOCAL_FALLBACKS=false"
            )
        return paths, receipt

    async def read_part(self, part_id: str) -> str:
        if self.base_url and self.api_key:
            try:
                async with GBrainMCP(self.base_url, self.api_key) as mcp:
                    page = await mcp.call(
                        "get_page",
                        {"slug": f"fleet/go2/parts/{_safe_segment(part_id)}", "include_content": True},
                    )
                    if page.get("content"):
                        return str(page["content"])
            except Exception:
                if not self.use_local_fallback:
                    raise
        return await self.local.read_part(part_id)

    async def query(self, part_id: str | None = None, unit_id: str | None = None) -> list[dict[str, str]]:
        if self.base_url and self.api_key and (part_id or unit_id):
            kind, value = ("parts", part_id) if part_id else ("units", unit_id)
            assert value is not None
            slug = f"fleet/go2/{kind}/{_safe_segment(value)}"
            try:
                async with GBrainMCP(self.base_url, self.api_key) as mcp:
                    page = await mcp.call("get_page", {"slug": slug, "include_content": True})
                if page.get("content"):
                    return [{"path": f"{slug}.md", "content": str(page["content"])}]
            except Exception:
                if not self.use_local_fallback:
                    raise
        return await self.local.query(part_id, unit_id)
