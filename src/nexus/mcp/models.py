from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class MCPError(RuntimeError):
    pass


class MCPConfigurationError(MCPError):
    pass


class MCPPermissionError(MCPError):
    pass


class MCPTransportError(MCPError):
    pass


class MCPToolError(MCPError):
    pass


@dataclass(frozen=True)
class MCPToolSchema:
    name: str
    title: str | None
    description: str | None
    input_schema: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MCPCallResult:
    tool: str
    text: list[str] = field(default_factory=list)
    structured_data: Any = None
    content_metadata: list[dict[str, Any]] = field(default_factory=list)
    is_error: bool = False
    attempt_count: int = 1
    executed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
