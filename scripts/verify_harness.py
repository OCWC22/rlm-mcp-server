#!/usr/bin/env python3
"""Verify per-client RLM harness artifacts are deployed.

Checks each detected clients expected artifact locations and reports
pass/fail per client. Exits 0 on full pass, non-zero on any failure.

Usage:
    python3 scripts/verify_harness.py
    python3 scripts/verify_harness.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

MARKER = "BEGIN rlm-harness"


@dataclass
class Check:
    client: str
    detected: bool
    items: list[dict] = field(default_factory=list)
    passed: bool = True


def _check_file(label: str, path: Path, must_exist: bool = True, must_contain: str | None = None) -> dict:
    exists = path.exists()
    ok = exists == must_exist
    extra: dict = {}
    if ok and must_contain and exists:
        contains = must_contain in path.read_text(encoding="utf-8", errors="replace")
        extra["contains_marker"] = contains
        ok = ok and contains
    return {"label": label, "path": str(path), "exists": exists, "pass": ok, **extra}


def verify_claude_code() -> Check:
    c = Check(client="claude-code", detected=Path.home().joinpath(".claude").is_dir())
    if not c.detected:
        return c
    home = Path.home()
    c.items.append(_check_file("rlm-analyst agent", home / ".claude/agents/rlm-analyst.md"))
    c.items.append(_check_file("rlm-load command", home / ".claude/commands/rlm-load.md"))
    c.items.append(_check_file("CLAUDE.md has marker", home / ".claude/CLAUDE.md", must_contain=MARKER))
    c.passed = all(i["pass"] for i in c.items)
    return c


def verify_codex() -> Check:
    c = Check(client="codex", detected=Path.home().joinpath(".codex").is_dir())
    if not c.detected:
        return c
    home = Path.home()
    c.items.append(_check_file("AGENTS.md has marker", home / ".codex/AGENTS.md", must_contain=MARKER))
    c.items.append(_check_file("skills/rlm dir", home / ".codex/skills/rlm"))
    c.items.append(_check_file("rlm SKILL.md", home / ".codex/skills/rlm/SKILL.md"))

    # v0.7.0: frontmatter must use lowercase name:/description: keys (case-sensitive name: field expected by Codex)
    skill_path = home / ".codex/skills/rlm/SKILL.md"
    if skill_path.exists():
        txt = skill_path.read_text(errors="replace")
        first_300 = txt[:300]
        lc_ok = ("name: " in first_300) and ("description: " in first_300)
        uc_bad = ("Name: " in first_300) or ("Description: " in first_300)
        c.items.append({
            "label": "SKILL.md frontmatter lowercase",
            "path": str(skill_path),
            "exists": True,
            "pass": lc_ok and not uc_bad,
        })
    c.passed = all(i["pass"] for i in c.items)
    return c


def verify_gemini() -> Check:
    c = Check(client="gemini", detected=Path.home().joinpath(".gemini").is_dir())
    if not c.detected:
        return c
    home = Path.home()
    # Either the extension install OR the fallback GEMINI.md merge should pass
    ext = home / ".gemini/extensions/rlm"
    gmd = home / ".gemini/GEMINI.md"
    ext_ok = (ext / "gemini-extension.json").exists()
    gmd_ok = gmd.exists() and MARKER in gmd.read_text(encoding="utf-8", errors="replace")
    c.items.append({"label": "extension dir", "path": str(ext), "exists": ext.exists(), "pass": ext_ok})
    c.items.append({"label": "GEMINI.md marker (fallback)", "path": str(gmd), "exists": gmd.exists(), "pass": gmd_ok})
    c.passed = ext_ok or gmd_ok
    return c


def verify_claude_desktop() -> Check:
    cfg = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    c = Check(client="claude-desktop", detected=cfg.exists())
    c.items.append({"label": "manual-only", "path": str(cfg), "exists": cfg.exists(), "pass": cfg.exists()})
    c.passed = cfg.exists()
    return c


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    checks = [verify_claude_code(), verify_codex(), verify_gemini(), verify_claude_desktop()]
    if args.json:
        print(json.dumps({"clients": [asdict(c) for c in checks], "overall_pass": all(c.passed for c in checks if c.detected)}, indent=2))
    else:
        for c in checks:
            mark = "PASS" if c.passed else "FAIL" if c.detected else "SKIP"
            print(f"- {c.client}: {mark} (detected={c.detected})")
            for i in c.items:
                sub = "ok" if i.get("pass") else "fail"
                label = i["label"]
                pth = i["path"]
                print(f"    {sub:<4} {label:<32} {pth}")
        overall = all(c.passed for c in checks if c.detected)
        print("overall:", "PASS" if overall else "FAIL")
    return 0 if all(c.passed for c in checks if c.detected) else 1


if __name__ == "__main__":
    sys.exit(main())
