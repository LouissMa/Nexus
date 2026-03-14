from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_STATE = {
    "memories": [],
    "goals": [],
}


@dataclass
class JsonStore:
    path: Path

    @classmethod
    def from_env(cls) -> "JsonStore":
        root = Path(os.environ.get("NEXUS_HOME", ".nexus"))
        return cls(root / "state.json")

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return json.loads(json.dumps(DEFAULT_STATE))

        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        state = json.loads(json.dumps(DEFAULT_STATE))
        state.update(data)
        return state

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
