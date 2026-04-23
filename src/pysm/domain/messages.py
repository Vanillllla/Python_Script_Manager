from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MessageSpec:
    key: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_storage(self) -> str:
        return json.dumps({"key": self.key, "params": self.params}, ensure_ascii=True, sort_keys=True)

    @classmethod
    def from_storage(cls, value: str | None) -> "MessageSpec | None":
        if not value:
            return None
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return cls(key="errors.runtime.legacy", params={"message": value})
        if not isinstance(payload, dict) or "key" not in payload:
            return cls(key="errors.runtime.legacy", params={"message": value})
        raw_params = payload.get("params") or {}
        params = raw_params if isinstance(raw_params, dict) else {}
        return cls(key=str(payload["key"]), params=params)
