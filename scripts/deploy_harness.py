#!/usr/bin/env python3
"""Deploy per-client RLM harness artifacts.

Reads client-harness/ in the repo and deploys artifacts to each detected
clients global path with timestamped backups and idempotent marker-based
merges.

Usage:
    python3 scripts/deploy_harness.py                # deploy to all detected clients
    python3 scripts/deploy_harness.py --dry-run      # preview, no writes
    python3 scripts/deploy_harness.py --json-report  # machine-readable output
    python3 scripts/deploy_harness.py --clients claude-code,gemini  # subset

Safe to re-run: each pass is idempotent. Snippets use BEGIN/END sentinels.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "client-harness"
MARKER_BEGIN = "<!-- BEGIN rlm-harness v0.5.0 -->"
MARKER_END = "<!-- END rlm-harness v0.5.0 -->"


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    bak = path.with_name(path.name + f".bak-{_stamp()}")
    shutil.copy2(path, bak)
    return bak


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _marker_merge(target: Path, snippet_file: Path, dry_run: bool) -> dict:
    """Append snippet between sentinels if not already present. Idempotent."""
    snippet = snippet_file.read_text(encoding="utf-8").strip() + "\n"
    existing = _read(target)
    if MARKER_BEGIN in existing and MARKER_END in existing:
        return {"action": "skip", "reason": "marker-present", "file": str(target)}
    if not snippet.startswith(MARKER_BEGIN):
        snippet = MARKER_BEGIN + "\n" + snippet + MARKER_END + "\n"
    new = existing.rstrip() + "\n\n" + snippet if existing else snippet
    if dry_run:
        return {"action": "would-merge", "file": str(target), "bytes_added": len(new) - len(existing)}
    target.parent.mkdir(parents=True, exist_ok=True)
    bak = _backup(target)
    target.write_text(new, encoding="utf-8")
    return {"action": "merged", "file": str(target), "backup": str(bak) if bak else None}


def _copy_tree(src: Path, dst: Path, dry_run: bool) -> dict:
    if not src.exists():
        return {"action": "skip", "reason": "src-missing", "src": str(src)}
    if dst.exists():
        return {"action": "skip", "reason": "dst-exists", "dst": str(dst)}
    if dry_run:
        return {"action": "would-copy", "src": str(src), "dst": str(dst)}
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    return {"action": "copied", "src": str(src), "dst": str(dst)}


@dataclass
class ClientResult:
    client: str
    detected: bool
    actions: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def deploy_claude_code(dry_run: bool) -> ClientResult:
    r = ClientResult(client="claude-code", detected=Path.home().joinpath(".claude").is_dir())
    if not r.detected:
        r.notes.append("~/.claude not found")
        return r
    src = HARNESS / "claude-code"
    home = Path.home()
    r.actions.append(_copy_tree(src / "agents/rlm-analyst.md", home / ".claude/agents/rlm-analyst.md", dry_run))
    r.actions.append(_copy_tree(src / "commands/rlm-load.md", home / ".claude/commands/rlm-load.md", dry_run))
    r.actions.append(_marker_merge(home / ".claude/CLAUDE.md", src / "memory/rlm-snippet.md", dry_run))
    return r


def deploy_codex(dry_run: bool) -> ClientResult:
    r = ClientResult(client="codex", detected=Path.home().joinpath(".codex").is_dir())
    if not r.detected:
        r.notes.append("~/.codex not found")
        return r
    src = HARNESS / "codex"
    home = Path.home()
    r.actions.append(_marker_merge(home / ".codex/AGENTS.md", src / "agents-md-snippet.md", dry_run))
    r.actions.append(_copy_tree(src / "skills/rlm", home / ".codex/skills/rlm", dry_run))
    return r


def deploy_gemini(dry_run: bool) -> ClientResult:
    r = ClientResult(client="gemini", detected=Path.home().joinpath(".gemini").is_dir())
    if not r.detected:
        r.notes.append("~/.gemini not found")
        return r
    src = HARNESS / "gemini"
    home = Path.home()
    # Try `gemini extensions install` first; fall back to file copy + marker-merge
    ext_src = src / "extension"
    ext_dst = home / ".gemini/extensions/rlm"
    gemini_cli = shutil.which("gemini")
    extension_ok = False
    if gemini_cli and not ext_dst.exists():
        if dry_run:
            r.actions.append({"action": "would-run", "cmd": f"gemini extensions install {ext_src}"})
            extension_ok = True
        else:
            try:
                proc = subprocess.run(
                    [gemini_cli, "extensions", "install", str(ext_src)],
                    capture_output=True, text=True, timeout=60,
                )
                if proc.returncode == 0:
                    r.actions.append({"action": "gemini-extensions-install", "rc": 0})
                    extension_ok = True
                else:
                    r.notes.append(f"gemini extensions install failed rc={proc.returncode}: {proc.stderr[:200]}")
            except Exception as e:
                r.notes.append(f"gemini extensions install exception: {e}")
    if not extension_ok:
        # Fallback: copy the extension dir + marker-merge the standalone GEMINI.md snippet
        r.actions.append(_copy_tree(ext_src, ext_dst, dry_run))
        r.actions.append(_marker_merge(home / ".gemini/GEMINI.md", src / "memory/gemini-snippet.md", dry_run))
    return r


def deploy_claude_desktop(dry_run: bool) -> ClientResult:
    desk_cfg = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    r = ClientResult(client="claude-desktop", detected=desk_cfg.exists())
    r.notes.append("manual: open app → Configure → Servers; see client-harness/claude-desktop/README.md")
    return r


DEPLOYERS = {
    "claude-code": deploy_claude_code,
    "codex": deploy_codex,
    "gemini": deploy_gemini,
    "claude-desktop": deploy_claude_desktop,
}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json-report", action="store_true")
    p.add_argument("--clients", help="Comma-separated subset of clients")
    args = p.parse_args()
    keys = args.clients.split(",") if args.clients else list(DEPLOYERS.keys())
    unknown = [k for k in keys if k not in DEPLOYERS]
    if unknown:
        print(f"unknown clients: {unknown}", file=sys.stderr)
        return 2
    results = [DEPLOYERS[k](args.dry_run) for k in keys]
    if args.json_report:
        print(json.dumps({"dry_run": args.dry_run, "clients": [asdict(r) for r in results]}, indent=2))
    else:
        mode = "dry-run" if args.dry_run else "live"
        print(f"Harness deploy — {mode}")
        for r in results:
            mark = "✓" if r.detected else "-"
            print(f"  {mark} {r.client}: {len(r.actions)} actions, detected={r.detected}")
            for a in r.actions:
                act = a.get("action", "?")
                target = a.get("file") or a.get("dst") or a.get("cmd") or a
                print(f"      {act:<15} {target}")
            for n in r.notes:
                print(f"      note: {n}")
    any_changed = any(
        a.get("action") in ("merged", "copied", "gemini-extensions-install", "would-merge", "would-copy", "would-run")
        for r in results for a in r.actions
    )
    print("overall:", "CHANGED" if any_changed else "NO-CHANGES")
    return 0


if __name__ == "__main__":
    sys.exit(main())
