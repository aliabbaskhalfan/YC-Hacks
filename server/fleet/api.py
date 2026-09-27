"""Fleet intelligence endpoints (BUILD_SPEC.md Section 12's integration contract).

A self-contained router rather than routes added to main.py, so wiring it up
is one line in whoever owns the app:

    from server.fleet.api import router as fleet_router
    app.include_router(fleet_router)

It reads `app.state.services` when present — to broadcast `procedure_updated`
over the existing hub and write the changelog through the existing GBrain
adapter — and still serves flags without it, so the Engineering tab can be
built before the rest is wired.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from server.fleet.approve import approve_flag
from server.fleet.intel import FlagStore, build_flags, counters, load_rows, mine_patterns
from server.fleet.registry import Registry

REPO_ROOT = Path(__file__).resolve().parents[2]

router = APIRouter(tags=["fleet"])


class AssignRequest(BaseModel):
    assignee: str


def _repo_root(request: Request) -> Path:
    services = getattr(request.app.state, "services", None)
    return services.settings.repo_root if services else REPO_ROOT


def _flag_store(request: Request) -> FlagStore:
    return FlagStore(_repo_root(request) / "data" / "runtime" / "flags.json")


def _fresh_flags(request: Request) -> list[dict[str, Any]]:
    """Re-mine, then re-apply stored status so approvals survive a re-mine."""
    root = _repo_root(request)
    registry = Registry.load(root / "data" / "registry")
    rows = load_rows(
        registry,
        root / "data" / "synthetic" / "incidents.jsonl",
        root / "data" / "runtime" / "incidents.json",
    )
    store = _flag_store(request)
    flags = store.merge(build_flags(rows, registry))
    store.save(flags)
    return [flag.to_dict() for flag in flags]


@router.get("/flags")
async def list_flags(request: Request, status: str | None = None, kind: str | None = None) -> dict[str, Any]:
    flags = _fresh_flags(request)
    if status:
        flags = [flag for flag in flags if flag["status"] == status]
    if kind:
        flags = [flag for flag in flags if flag["kind"] == kind]
    return {"flags": flags}


@router.post("/flags/{flag_id}/approve")
async def approve(flag_id: str, request: Request) -> dict[str, Any]:
    _fresh_flags(request)  # make sure the flag exists before approving it
    services = getattr(request.app.state, "services", None)
    root = _repo_root(request)
    try:
        event = await approve_flag(
            flag_id,
            flags=_flag_store(request),
            procedures_dir=root / "server" / "procedures",
            brain=services.brain if services else None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"No such flag: {flag_id}") from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if services:
        # Every open tech viewer re-renders the step (Section 9.4).
        await services.events.publish(event)
    return event


@router.post("/flags/{flag_id}/dismiss")
async def dismiss(flag_id: str, request: Request) -> dict[str, Any]:
    try:
        return _flag_store(request).set_status(flag_id, "dismissed")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"No such flag: {flag_id}") from exc


@router.post("/flags/{flag_id}/assign")
async def assign(flag_id: str, body: AssignRequest, request: Request) -> dict[str, Any]:
    store = _flag_store(request)
    try:
        flag = store.set_status(flag_id, "assigned")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"No such flag: {flag_id}") from exc
    return {**flag, "assignee": body.assignee}


@router.get("/fleet/counters")
async def fleet_counters(request: Request) -> dict[str, Any]:
    root = _repo_root(request)
    registry = Registry.load(root / "data" / "registry")
    rows = load_rows(
        registry,
        root / "data" / "synthetic" / "incidents.jsonl",
        root / "data" / "runtime" / "incidents.json",
    )
    return {
        dimension: {key: metrics.__dict__ for key, metrics in buckets.items()}
        for dimension, buckets in counters(rows).items()
    }


@router.get("/fleet/patterns")
async def fleet_patterns(request: Request) -> dict[str, Any]:
    root = _repo_root(request)
    registry = Registry.load(root / "data" / "registry")
    rows = load_rows(registry, root / "data" / "synthetic" / "incidents.jsonl")
    return {"patterns": [cell.__dict__ for cell in mine_patterns(rows, registry)]}
