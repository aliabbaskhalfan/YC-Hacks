from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ProcedureStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def get(self, procedure_id: str) -> dict[str, Any]:
        safe = "".join(ch for ch in procedure_id if ch.isalnum() or ch in {"-", "_"})
        if safe != procedure_id:
            raise ValueError("Invalid procedure id")
        path = self.root / f"{safe}.json"
        if not path.exists():
            raise KeyError(procedure_id)
        return json.loads(path.read_text())

    def step_text(self, procedure_id: str, step_id: int) -> str:
        try:
            procedure = self.get(procedure_id)
        except KeyError:
            return ""
        step = next((step for step in procedure.get("steps", []) if step.get("step_id") == step_id), None)
        return step.get("text", "") if step else ""
