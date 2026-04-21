"""Minimal stdio MCP client for evaluation runs."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _coerce_tool_result(result: types.CallToolResult) -> Any:
    if result.isError:
        text_parts = [getattr(part, "text", "") for part in result.content]
        raise RuntimeError("tool error: " + "\n".join(p for p in text_parts if p))

    if result.structuredContent is not None:
        structured = result.structuredContent
        if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
            return structured["result"]
        return structured

    text_parts = [getattr(part, "text", "") for part in result.content]
    text = "\n".join(p for p in text_parts if p).strip()
    if not text:
        return ""

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


@dataclass
class MCPToolClient:
    """Small helper to call RLM MCP tools through stdio subprocesses."""

    command: str = field(default_factory=lambda: sys.executable)
    args: list[str] = field(default_factory=lambda: [str(_repo_root() / "rlm_mcp.py")])
    cwd: str = field(default_factory=lambda: str(_repo_root()))
    timeout_seconds: float = 45.0
    env: dict[str, str] | None = None

    _stdio_cm: Any = field(init=False, default=None)
    _session_cm: Any = field(init=False, default=None)
    _session: ClientSession | None = field(init=False, default=None)

    async def __aenter__(self):
        merged_env = dict(os.environ)
        merged_env.setdefault("RLM_TRACE_DISABLE", "1")
        merged_env.setdefault("RLM_STATE_DIR", str(Path(os.environ.get("TMPDIR", "/tmp")) / "rlm-mcp-eval-state"))
        if self.env:
            merged_env.update(self.env)

        params = StdioServerParameters(
            command=self.command,
            args=list(self.args),
            cwd=self.cwd,
            env=merged_env,
        )
        self._stdio_cm = stdio_client(params)
        read_stream, write_stream = await self._stdio_cm.__aenter__()

        self._session_cm = ClientSession(read_stream, write_stream)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        await self._session.send_notification(types.InitializedNotification())
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._session_cm is not None:
            await self._session_cm.__aexit__(exc_type, exc, tb)
        if self._stdio_cm is not None:
            await self._stdio_cm.__aexit__(exc_type, exc, tb)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        if self._session is None:
            raise RuntimeError("MCPToolClient not connected")
        with anyio.fail_after(self.timeout_seconds):
            result = await self._session.call_tool(name, arguments or {})
        return _coerce_tool_result(result)
