#!/usr/bin/env python3
"""End-to-end verifier for RLM MCP wiring across CLI clients."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomllib

REQUIRED_TRACE_TOOLS = {"rlm_init", "rlm_grep", "rlm_exec"}
API_KEY_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "VERTEX_API_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
    "TOGETHER_API_KEY",
)


@dataclass
class ClientSpec:
    key: str
    label: str
    cli_name: str
    config_path: Path
    kind: str  # "json" | "toml"


@dataclass
class VerifyReport:
    client: str
    detected_cli: bool
    detected_config: bool
    rlm_registered: bool
    cache_writable: bool
    node_version: str | None
    session_id: str | None
    trace_file: str | None
    tools_seen: list[str]
    command: list[str] | None
    status: str
    error: str | None


def _build_client_specs() -> list[ClientSpec]:
    home = Path.home()
    return [
        ClientSpec(
            key="claude",
            label="Claude Code",
            cli_name="claude",
            config_path=home / ".claude.json",
            kind="json",
        ),
        ClientSpec(
            key="codex",
            label="Codex CLI",
            cli_name="codex",
            config_path=home / ".codex/config.toml",
            kind="toml",
        ),
        ClientSpec(
            key="gemini",
            label="Gemini CLI",
            cli_name="gemini",
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


def _state_dir_from_env(env: dict[str, str]) -> Path:
    raw = env.get("RLM_STATE_DIR") or env.get("RLM_DATA_DIR")
    if raw and raw.strip():
        return Path(raw).expanduser()
    return Path.home() / ".cache" / "rlm-mcp"


def _trace_dir_from_env(env: dict[str, str], state_dir: Path) -> Path:
    raw = env.get("RLM_TRACE_DIR")
    if raw and raw.strip():
        return Path(raw).expanduser()
    return state_dir / "traces"


def _assert_writable(path: Path) -> tuple[bool, str | None]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".verify-write-{int(time.time() * 1000)}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def _node_major_version() -> tuple[int | None, str]:
    node_path = shutil.which("node")
    if node_path is None:
        return None, "node-not-found"

    proc = subprocess.run([node_path, "--version"], capture_output=True, text=True, check=False)
    raw = (proc.stdout or proc.stderr or "").strip()
    match = re.search(r"v?(\d+)", raw)
    if not match:
        return None, raw or "unknown"
    return int(match.group(1)), raw


def _active_api_keys() -> list[str]:
    active: list[str] = []
    for key in API_KEY_VARS:
        value = os.environ.get(key)
        if value and value.strip():
            active.append(key)
    return active


def _build_command(spec: ClientSpec, prompt: str) -> list[str]:
    if spec.key == "claude":
        return ["claude", "-p", "--permission-mode", "bypassPermissions", prompt]
    if spec.key == "codex":
        return ["codex", "exec", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox", prompt]
    if spec.key == "gemini":
        return ["gemini", "-p", "--approval-mode", "yolo", "--allowed-mcp-server-names", "rlm", prompt]
    raise RuntimeError(f"Unsupported client: {spec.key}")


def _build_prompt(input_path: Path, session_id: str) -> str:
    return (
        "Use the rlm MCP tools for this task. "
        f"Call rlm_init(path=\"{input_path}\", session_id=\"{session_id}\"), "
        f"then call rlm_grep(pattern=\"ALPHA\", session_id=\"{session_id}\"), "
        "then call rlm_exec with code that counts ALPHA matches using grep and prints the count "
        f"(same session_id=\"{session_id}\"). "
        'Reply with: done.'
    )


def _wait_for_trace_file(trace_dir: Path, session_id: str, timeout_s: int) -> Path | None:
    deadline = time.monotonic() + timeout_s
    pattern = f"{session_id}-*.jsonl"
    while time.monotonic() < deadline:
        matches = sorted(trace_dir.glob(pattern))
        if matches:
            return matches[-1]
        time.sleep(0.25)
    return None


def _parse_trace_tools(path: Path) -> tuple[set[str], str | None]:
    tools: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            tool = row.get("tool")
            if isinstance(tool, str):
                tools.add(tool)
    except Exception as exc:  # noqa: BLE001
        return tools, f"{type(exc).__name__}: {exc}"
    return tools, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--client",
        action="append",
        choices=["claude", "codex", "gemini"],
        help="Limit verification to one or more clients.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run preflight checks only.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output.")
    parser.add_argument("--timeout", type=int, default=180, help="Per-client command timeout (seconds).")
    parser.add_argument(
        "--trace-wait",
        type=int,
        default=20,
        help="Max seconds to wait for trace file flush after command exit.",
    )
    args = parser.parse_args()

    selected = set(args.client) if args.client else {"claude", "codex", "gemini"}
    active_keys = _active_api_keys()

    reports: list[VerifyReport] = []

    for spec in _build_client_specs():
        if spec.key not in selected:
            continue

        detected_cli = shutil.which(spec.cli_name) is not None
        detected_config = spec.config_path.exists()
        report = VerifyReport(
            client=spec.label,
            detected_cli=detected_cli,
            detected_config=detected_config,
            rlm_registered=False,
            cache_writable=False,
            node_version=None,
            session_id=None,
            trace_file=None,
            tools_seen=[],
            command=None,
            status="skip",
            error=None,
        )

        if not detected_cli:
            report.error = f"CLI not found on PATH: {spec.cli_name}"
            reports.append(report)
            continue

        if not detected_config:
            report.error = f"Config not found: {spec.config_path}"
            reports.append(report)
            continue

        if active_keys:
            report.status = "fail"
            report.error = f"API key env vars must be unset for this check: {', '.join(active_keys)}"
            reports.append(report)
            continue

        try:
            command, cmd_args, env = _read_rlm_entry(spec)
        except Exception as exc:  # noqa: BLE001
            report.status = "fail"
            report.error = f"Failed reading config: {type(exc).__name__}: {exc}"
            reports.append(report)
            continue

        if not command:
            report.status = "fail"
            report.error = "No `rlm` MCP entry found in client config"
            reports.append(report)
            continue

        report.rlm_registered = True
        state_dir = _state_dir_from_env(env)
        writable, writable_error = _assert_writable(state_dir)
        report.cache_writable = writable
        if not writable:
            report.status = "fail"
            report.error = f"Cache dir not writable ({state_dir}): {writable_error}"
            reports.append(report)
            continue

        if spec.key == "gemini":
            major, node_version = _node_major_version()
            report.node_version = node_version
            if major is None:
                report.status = "fail"
                report.error = f"Unable to detect Node.js version for Gemini: {node_version}"
                reports.append(report)
                continue
            if major < 20:
                report.status = "fail"
                report.error = f"Gemini requires Node >= 20; found {node_version}"
                reports.append(report)
                continue

        if args.dry_run:
            report.status = "pass"
            reports.append(report)
            continue

        session_id = f"verify-e2e-{spec.key}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        report.session_id = session_id

        fixture_path = Path("/tmp") / f"{session_id}.txt"
        fixture_path.write_text("ALPHA one\nbeta two\nALPHA three\n", encoding="utf-8")

        prompt = _build_prompt(fixture_path, session_id)
        cli_command = _build_command(spec, prompt)
        report.command = [*cli_command]

        env_for_cli = os.environ.copy()
        env_for_cli.update(env)

        try:
            proc = subprocess.run(
                cli_command,
                capture_output=True,
                text=True,
                timeout=args.timeout,
                env=env_for_cli,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            report.status = "fail"
            report.error = f"Client invocation failed: {type(exc).__name__}: {exc}"
            reports.append(report)
            continue
        finally:
            try:
                fixture_path.unlink()
            except Exception:
                pass

        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()
            tail = tail[-400:] if tail else "<no stderr/stdout>"
            report.status = "fail"
            report.error = f"Client exited with code {proc.returncode}: {tail}"
            reports.append(report)
            continue

        trace_dir = _trace_dir_from_env(env, state_dir)
        trace_file = _wait_for_trace_file(trace_dir, session_id, timeout_s=args.trace_wait)
        if trace_file is None:
            report.status = "fail"
            report.error = f"No trace JSONL found for session {session_id} in {trace_dir}"
            reports.append(report)
            continue

        report.trace_file = str(trace_file)
        tools, parse_error = _parse_trace_tools(trace_file)
        report.tools_seen = sorted(tools)
        if parse_error:
            report.status = "fail"
            report.error = f"Could not parse trace file {trace_file}: {parse_error}"
            reports.append(report)
            continue

        missing = sorted(REQUIRED_TRACE_TOOLS - tools)
        if missing:
            report.status = "fail"
            report.error = f"Trace missing required tools: {', '.join(missing)}"
            reports.append(report)
            continue

        report.status = "pass"
        reports.append(report)

    overall_pass = all(r.status in {"pass", "skip"} for r in reports)
    payload = {
        "required_trace_tools": sorted(REQUIRED_TRACE_TOOLS),
        "dry_run": args.dry_run,
        "clients": [asdict(r) for r in reports],
        "overall_status": "pass" if overall_pass else "fail",
    }

    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for report in reports:
            print(
                f"- {report.client}: {report.status}"
                f" cli={report.detected_cli}"
                f" config={report.detected_config}"
                f" registered={report.rlm_registered}"
                f" cache_writable={report.cache_writable}"
                f" node={report.node_version}"
                f" session_id={report.session_id}"
                f" trace={report.trace_file}"
            )
            if report.tools_seen:
                print(f"  tools_seen: {', '.join(report.tools_seen)}")
            if report.error:
                print(f"  error: {report.error}")
        print(f"overall: {'PASS' if overall_pass else 'FAIL'}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
