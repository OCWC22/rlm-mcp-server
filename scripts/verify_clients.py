#!/usr/bin/env python3
"""Health-check installed RLM MCP clients via stdio handshake."""

from __future__ import annotations

import argparse
import json
import os
import select
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import tomllib

EXPECTED_TOOL_COUNT = 14


@dataclass
class ClientSpec:
    label: str
    config_path: Path
    kind: str  # "json" | "toml"


@dataclass
class VerifyReport:
    client: str
    detected: bool
    config_path: str
    command: str | None
    tool_count: int | None
    has_rlm_exec: bool
    has_rlm_sub_query: bool
    status: str
    time_ms: int | None
    error: str | None = None


class JsonLineRpc:
    def __init__(self, proc: subprocess.Popen[bytes]):
        self.proc = proc
        self._buffer = b""
        self.non_json_lines: list[str] = []

    def send(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        assert self.proc.stdin is not None
        self.proc.stdin.write(body)
        self.proc.stdin.flush()

    def recv(self, timeout_s: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s

        while True:
            while b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    self.non_json_lines.append(text)
                    continue

            self._buffer += self._read_chunk(deadline)

    def _read_chunk(self, deadline: float) -> bytes:
        assert self.proc.stdout is not None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Timed out waiting for MCP server response")

        fd = self.proc.stdout.fileno()
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            raise TimeoutError("Timed out waiting for MCP server response")

        chunk = os.read(fd, 65536)
        if not chunk:
            raise EOFError("MCP server closed stdout")
        return chunk


def _build_client_specs() -> list[ClientSpec]:
    home = Path.home()
    return [
        ClientSpec(
            label="Claude Desktop",
            config_path=home / "Library/Application Support/Claude/claude_desktop_config.json",
            kind="json",
        ),
        ClientSpec(
            label="Claude Code",
            config_path=home / ".claude.json",
            kind="json",
        ),
        ClientSpec(
            label="Codex CLI",
            config_path=home / ".codex/config.toml",
            kind="toml",
        ),
        ClientSpec(
            label="Gemini CLI",
            config_path=home / ".gemini/settings.json",
            kind="json",
        ),
    ]


def _read_rlm_entry(spec: ClientSpec) -> tuple[str | None, list[str], dict[str, str]]:
    raw = spec.config_path.read_text(encoding="utf-8")

    if spec.kind == "json":
        data = json.loads(raw)
        servers = data.get("mcpServers") if isinstance(data.get("mcpServers"), dict) else data.get("mcp_servers")
        if not isinstance(servers, dict):
            return None, [], {}
    else:
        data = tomllib.loads(raw)
        servers = data.get("mcp_servers")
        if not isinstance(servers, dict):
            return None, [], {}

    entry = servers.get("rlm")
    if not isinstance(entry, dict):
        return None, [], {}

    command = entry.get("command") if isinstance(entry.get("command"), str) else None

    args = entry.get("args")
    if not isinstance(args, list):
        args = []
    args = [str(a) for a in args]

    env = entry.get("env")
    if not isinstance(env, dict):
        env = {}
    env = {str(k): str(v) for k, v in env.items()}

    return command, args, env


def _wait_for_response(rpc: JsonLineRpc, wanted_id: int, timeout_s: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Timed out waiting for response id={wanted_id}")
        msg = rpc.recv(remaining)
        if msg.get("id") == wanted_id:
            return msg


def _terminate(proc: subprocess.Popen[bytes]) -> str:
    stderr_text = ""
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:  # noqa: BLE001
        proc.kill()
        try:
            proc.wait(timeout=1)
        except Exception:  # noqa: BLE001
            pass

    if proc.stderr is not None:
        try:
            stderr_text = proc.stderr.read().decode("utf-8", errors="replace").strip()
        except Exception:  # noqa: BLE001
            stderr_text = ""
    return stderr_text


def _verify_one(command: str, args: list[str], env: dict[str, str]) -> tuple[int, bool, bool, int, str | None]:
    started = time.monotonic()
    merged_env = os.environ.copy()
    merged_env.update(env)

    proc = subprocess.Popen(
        [command, *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=merged_env,
    )

    rpc = JsonLineRpc(proc)

    error: str | None = None
    tool_names: list[str] = []
    try:
        rpc.send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "rlm-verify", "version": "1.0"},
                },
            }
        )
        init_resp = _wait_for_response(rpc, wanted_id=1, timeout_s=15.0)
        if "error" in init_resp:
            raise RuntimeError(f"initialize error: {init_resp['error']}")

        rpc.send(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }
        )

        rpc.send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            }
        )
        tools_resp = _wait_for_response(rpc, wanted_id=2, timeout_s=15.0)
        if "error" in tools_resp:
            raise RuntimeError(f"tools/list error: {tools_resp['error']}")

        tools = tools_resp.get("result", {}).get("tools", [])
        if not isinstance(tools, list):
            raise RuntimeError("tools/list result missing tools array")

        tool_names = [t.get("name") for t in tools if isinstance(t, dict) and isinstance(t.get("name"), str)]

        if rpc.non_json_lines:
            # Non-JSON stdout should not happen for stdio transport.
            preview = "; ".join(rpc.non_json_lines[:2])
            raise RuntimeError(f"non-JSON stdout lines observed: {preview}")

    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    finally:
        stderr_text = _terminate(proc)
        if error and stderr_text:
            error = f"{error}; stderr={stderr_text}"

    elapsed_ms = int((time.monotonic() - started) * 1000)
    names = set(tool_names)
    return len(tool_names), ("rlm_exec" in names), ("rlm_sub_query" in names), elapsed_ms, error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output.")
    args = parser.parse_args()

    reports: list[VerifyReport] = []

    for spec in _build_client_specs():
        detected = spec.config_path.exists()
        if not detected:
            reports.append(
                VerifyReport(
                    client=spec.label,
                    detected=False,
                    config_path=str(spec.config_path),
                    command=None,
                    tool_count=None,
                    has_rlm_exec=False,
                    has_rlm_sub_query=False,
                    status="skip",
                    time_ms=None,
                    error=None,
                )
            )
            continue

        try:
            command, cmd_args, env = _read_rlm_entry(spec)
            if not command:
                reports.append(
                    VerifyReport(
                        client=spec.label,
                        detected=True,
                        config_path=str(spec.config_path),
                        command=None,
                        tool_count=None,
                        has_rlm_exec=False,
                        has_rlm_sub_query=False,
                        status="fail",
                        time_ms=None,
                        error="No rlm command found in config",
                    )
                )
                continue

            tool_count, has_exec, has_sub, elapsed_ms, error = _verify_one(command, cmd_args, env)
            ok = (
                error is None
                and tool_count == EXPECTED_TOOL_COUNT
                and has_exec
                and has_sub
            )
            reports.append(
                VerifyReport(
                    client=spec.label,
                    detected=True,
                    config_path=str(spec.config_path),
                    command=command,
                    tool_count=tool_count,
                    has_rlm_exec=has_exec,
                    has_rlm_sub_query=has_sub,
                    status="pass" if ok else "fail",
                    time_ms=elapsed_ms,
                    error=error,
                )
            )
        except Exception as exc:  # noqa: BLE001
            reports.append(
                VerifyReport(
                    client=spec.label,
                    detected=True,
                    config_path=str(spec.config_path),
                    command=None,
                    tool_count=None,
                    has_rlm_exec=False,
                    has_rlm_sub_query=False,
                    status="fail",
                    time_ms=None,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    detected_reports = [r for r in reports if r.detected]
    overall_pass = all(r.status == "pass" for r in detected_reports)

    payload = {
        "expected_tool_count": EXPECTED_TOOL_COUNT,
        "clients": [asdict(r) for r in reports],
        "overall_status": "pass" if overall_pass else "fail",
    }

    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for report in reports:
            if not report.detected:
                print(f"- {report.client}: skip (not detected)")
                continue
            print(
                f"- {report.client}: {report.status}"
                f" tool_count={report.tool_count}"
                f" has_rlm_exec={report.has_rlm_exec}"
                f" has_rlm_sub_query={report.has_rlm_sub_query}"
                f" time_ms={report.time_ms}"
                f" command={report.command}"
            )
            if report.error:
                print(f"  error: {report.error}")

        print(f"overall: {'PASS' if overall_pass else 'FAIL'}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
