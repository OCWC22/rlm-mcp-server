#!/usr/bin/env python3
"""Idempotent installer for RLM MCP wiring across local clients."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomllib

REQUIRED_ENV = {
    "RLM_DATA_DIR": "~/.cache/rlm-mcp",
    "OLLAMA_URL": "http://localhost:11434",
}


@dataclass
class ClientSpec:
    key: str
    label: str
    config_path: Path
    kind: str  # "json" | "toml"


@dataclass
class ClientReport:
    client: str
    detected: bool
    changed: bool
    backup_path: str | None
    final_command_path: str | None
    config_path: str
    error: str | None = None


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _json_servers_key(data: dict[str, Any]) -> str:
    if isinstance(data.get("mcpServers"), dict):
        return "mcpServers"
    if isinstance(data.get("mcp_servers"), dict):
        return "mcp_servers"
    data["mcpServers"] = {}
    return "mcpServers"


def _apply_json_install(
    data: dict[str, Any], launcher: str, force: bool
) -> tuple[dict[str, Any], bool, str | None]:
    changed = False
    servers_key = _json_servers_key(data)
    servers = data[servers_key]

    for key in list(servers.keys()):
        if isinstance(key, str) and key.startswith("rlm") and key != "rlm":
            del servers[key]
            changed = True

    existing_entry = servers.get("rlm")
    if force or not isinstance(existing_entry, dict):
        entry: dict[str, Any] = {}
        if not force and existing_entry is not None and not isinstance(existing_entry, dict):
            changed = True
    else:
        entry = dict(existing_entry)

    if entry.get("command") != launcher:
        entry["command"] = launcher
        changed = True

    existing_env = entry.get("env")
    env = dict(existing_env) if (not force and isinstance(existing_env, dict)) else {}
    for key, value in REQUIRED_ENV.items():
        if env.get(key) != value:
            env[key] = value
            changed = True
    entry["env"] = env

    if servers.get("rlm") != entry:
        servers["rlm"] = entry
        changed = True

    final_command = entry.get("command") if isinstance(entry, dict) else None
    return data, changed, final_command


_TABLE_RE = re.compile(r"(?m)^\[([^\n\]]+)\]\s*$")


def _split_toml_path(path: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    in_quotes = False
    escape = False
    for ch in path:
        if in_quotes:
            if escape:
                buf.append(ch)
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_quotes = False
                continue
            buf.append(ch)
            continue

        if ch == '"':
            in_quotes = True
            continue
        if ch == ".":
            seg = "".join(buf).strip()
            if seg:
                parts.append(seg)
            buf = []
            continue
        buf.append(ch)

    seg = "".join(buf).strip()
    if seg:
        parts.append(seg)
    return parts


def _is_rlm_family_table(header_body: str) -> bool:
    segs = _split_toml_path(header_body.strip())
    if len(segs) < 2:
        return False
    root = segs[0].strip().strip('"').strip("'")
    key = segs[1].strip().strip('"').strip("'")
    return root in {"mcp_servers", "mcpServers"} and key.startswith("rlm")


def _remove_matching_tables(text: str) -> tuple[str, int]:
    matches = list(_TABLE_RE.finditer(text))
    if not matches:
        return text, 0

    out: list[str] = []
    removed = 0
    cursor = 0

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

        if cursor < start:
            out.append(text[cursor:start])

        block = text[start:end]
        if _is_rlm_family_table(match.group(1)):
            removed += 1
        else:
            out.append(block)
        cursor = end

    if cursor < len(text):
        out.append(text[cursor:])

    return "".join(out), removed


def _canonical_codex_block(launcher: str) -> str:
    return (
        "[mcp_servers.rlm]\n"
        f'command = "{launcher}"\n\n'
        "[mcp_servers.rlm.env]\n"
        f'RLM_DATA_DIR = "{REQUIRED_ENV["RLM_DATA_DIR"]}"\n'
        f'OLLAMA_URL = "{REQUIRED_ENV["OLLAMA_URL"]}"\n'
    )


def _apply_codex_install(
    text: str, launcher: str, force: bool
) -> tuple[str, bool, str | None]:
    data = tomllib.loads(text)
    mcp_servers = data.get("mcp_servers")
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}

    family_keys = sorted(
        key for key in mcp_servers.keys() if isinstance(key, str) and key.startswith("rlm")
    )
    entry = mcp_servers.get("rlm") if isinstance(mcp_servers.get("rlm"), dict) else {}
    env = entry.get("env") if isinstance(entry.get("env"), dict) else {}

    changed = False
    if family_keys != ["rlm"]:
        changed = True

    if entry.get("command") != launcher:
        changed = True

    for k, v in REQUIRED_ENV.items():
        if env.get(k) != v:
            changed = True

    if force:
        canonical = {"command": launcher, "env": dict(REQUIRED_ENV)}
        if entry != canonical:
            changed = True

    if re.search(r'(?m)^\[mcp_servers\."rlm"(?:\.env)?\]\s*$', text):
        changed = True

    if not changed:
        return text, False, entry.get("command")

    stripped, _ = _remove_matching_tables(text)
    base = stripped.rstrip()
    block = _canonical_codex_block(launcher).rstrip()
    if base:
        new_text = f"{base}\n\n{block}\n"
    else:
        new_text = f"{block}\n"

    return new_text, new_text != text, launcher


def _build_client_specs() -> list[ClientSpec]:
    home = Path.home()
    return [
        ClientSpec(
            key="claude_desktop",
            label="Claude Desktop",
            config_path=home / "Library/Application Support/Claude/claude_desktop_config.json",
            kind="json",
        ),
        ClientSpec(
            key="claude_code",
            label="Claude Code",
            config_path=home / ".claude.json",
            kind="json",
        ),
        ClientSpec(
            key="codex_cli",
            label="Codex CLI",
            config_path=home / ".codex/config.toml",
            kind="toml",
        ),
        ClientSpec(
            key="gemini_cli",
            label="Gemini CLI",
            config_path=home / ".gemini/settings.json",
            kind="json",
        ),
    ]


def _node_major_version() -> tuple[int | None, str]:
    node_path = shutil.which("node")
    if node_path is None:
        return None, "node-not-found"

    proc = subprocess.run(
        [node_path, "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    raw = (proc.stdout or proc.stderr or "").strip()
    match = re.search(r"v?(\d+)", raw)
    if not match:
        return None, raw or "unknown"
    return int(match.group(1)), raw


def _gemini_node_warning() -> str | None:
    if shutil.which("gemini") is None:
        return None

    major, raw = _node_major_version()
    if major is None:
        return f"[warn] Gemini CLI detected but unable to verify Node.js version ({raw}); Gemini requires Node >=20."
    if major < 20:
        return f"[warn] Gemini CLI detected but Node.js {raw} < v20; upgrade to Node >=20 for reliable MCP runs."
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing rlm entries instead of preserving extra fields.",
    )
    parser.add_argument(
        "--json-report",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    launcher = str((repo_root / "run_server.sh").resolve())

    reports: list[ClientReport] = []
    pending_writes: dict[str, str] = {}
    detected_paths: list[Path] = []
    had_error = False
    node_warning = _gemini_node_warning()

    for spec in _build_client_specs():
        detected = spec.config_path.exists()
        report = ClientReport(
            client=spec.label,
            detected=detected,
            changed=False,
            backup_path=None,
            final_command_path=None,
            config_path=str(spec.config_path),
            error=None,
        )

        if not detected:
            reports.append(report)
            continue

        detected_paths.append(spec.config_path)
        try:
            original = spec.config_path.read_text(encoding="utf-8")
            if spec.kind == "json":
                data = json.loads(original)
                updated, changed, final_command = _apply_json_install(
                    data=data,
                    launcher=launcher,
                    force=args.force,
                )
                new_text = json.dumps(updated, indent=2, ensure_ascii=False) + "\n"
            elif spec.kind == "toml":
                new_text, changed, final_command = _apply_codex_install(
                    text=original,
                    launcher=launcher,
                    force=args.force,
                )
            else:
                raise RuntimeError(f"Unsupported config kind: {spec.kind}")

            report.changed = bool(changed)
            report.final_command_path = final_command
            if changed:
                pending_writes[spec.label] = new_text

        except Exception as exc:  # noqa: BLE001
            report.error = f"{type(exc).__name__}: {exc}"
            had_error = True

        reports.append(report)

    backup_dir: Path | None = None
    if not args.dry_run and pending_writes and not had_error:
        backup_dir = repo_root / f"config-backups-{_utc_stamp()}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        for spec in _build_client_specs():
            if not spec.config_path.exists():
                continue
            backup_name = f"{spec.key}{spec.config_path.suffix}"
            backup_path = backup_dir / backup_name
            shutil.copy2(spec.config_path, backup_path)
            for report in reports:
                if report.client == spec.label and report.detected:
                    report.backup_path = str(backup_path)

        for spec in _build_client_specs():
            if spec.label not in pending_writes:
                continue
            spec.config_path.write_text(pending_writes[spec.label], encoding="utf-8")

    elif not args.dry_run and pending_writes and had_error:
        # Don't partially write if parsing failed for any detected client.
        pass

    output = {
        "repo_root": str(repo_root),
        "launcher": launcher,
        "dry_run": args.dry_run,
        "force": args.force,
        "backup_dir": str(backup_dir) if backup_dir else None,
        "clients": [asdict(report) for report in reports],
        "warnings": [node_warning] if node_warning else [],
    }

    if args.json_report:
        json.dump(output, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"RLM launcher: {launcher}")
        if args.dry_run:
            print("Mode: dry-run (no files written)")
        elif backup_dir:
            print(f"Backup dir: {backup_dir}")

        if node_warning:
            print(node_warning)

        for report in reports:
            status = "detected" if report.detected else "not detected"
            suffix = ""
            if report.error:
                suffix = f" error={report.error}"
            else:
                suffix = (
                    f" changed={report.changed}"
                    f" final_command={report.final_command_path}"
                    f" backup={report.backup_path}"
                )
            print(f"- {report.client}: {status}{suffix}")

        changed_count = sum(1 for r in reports if r.detected and r.changed)
        if args.dry_run:
            if changed_count:
                print(f"Dry run: {changed_count} client config(s) would change.")
            else:
                print("Dry run: no changes.")
        elif had_error:
            print("Install failed: at least one client config could not be parsed.")
        elif changed_count:
            print(f"Applied changes to {changed_count} client config(s).")
        else:
            print("No changes needed.")

    if had_error:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
