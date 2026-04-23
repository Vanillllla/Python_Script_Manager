from __future__ import annotations

from typing import Any

from pysm.domain.messages import MessageSpec


class PysmError(Exception):
    def __init__(
        self,
        code: str,
        message_key: str,
        params: dict[str, Any] | None = None,
        status_code: int = 400,
    ) -> None:
        super().__init__(message_key)
        self.code = code
        self.message = MessageSpec(message_key, params or {})
        self.status_code = status_code

    def __str__(self) -> str:
        return f"{self.code}: {self.message.key}"
