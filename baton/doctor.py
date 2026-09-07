from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from baton.clis import discover
from baton.config import load_config
from baton.dirs import describe_all
from baton.txcript_hop import find_txcript


def collect_doctor(*, cwd: Path | None = None) -> dict:
    cfg = load_config()
    cfg.clis = discover(cfg.clis)
    work = (cwd or Path.cwd()).resolve()
    txcript = find_txcript(cfg.txcript_bin)
    clis = []
    for harness, rec in cfg.clis.items():
        clis.append(
            {
                "harness": harness,
                "enabled": rec.enabled,
                "found": rec.found,
                "bin": rec.bin,
                "names": list(rec.names),
            }
        )
    dirs = []
    for item in describe_all(work):
        dirs.append(
            {
                "harness": item.harness,
                "home": str(item.config_or_home),
                "home_exists": item.config_or_home.exists(),
                "sessions": str(item.sessions),
                "sessions_exist": item.sessions.exists(),
                "notes": item.notes,
            }
        )
    problems: list[str] = []
    if sys.version_info < (3, 11):
        problems.append(f"Python {sys.version.split()[0]} is older than 3.11")
    if not txcript:
        problems.append("txcript not on PATH (required for cross-harness hops)")
    enabled = [row for row in clis if row["enabled"]]
    if not enabled:
        problems.append("no CLI homes enabled — run `baton clis`")
    if sys.platform == "win32":
        problems.append("attach uses Unix sockets; Windows is unsupported (use WSL or macOS/Linux)")
    return {
        "ok": not problems,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "cwd": str(work),
        "txcript": txcript,
        "which_python": shutil.which("python3") or shutil.which("python"),
        "clis": clis,
        "directories": dirs,
        "problems": problems,
    }


def format_doctor(report: dict) -> str:
    lines = [
        f"python     {report['python']}",
        f"platform   {report['platform']}",
        f"cwd        {report['cwd']}",
        f"txcript    {report['txcript'] or '(missing)'}",
        "",
        "CLI homes:",
    ]
    for row in report["clis"]:
        mark = "on " if row["enabled"] else "off"
        path = row["bin"] or "not found"
        lines.append(f"  [{mark}] {row['harness']:<14} {path}")
    lines.append("")
    lines.append("Session directories (for this cwd):")
    for row in report["directories"]:
        flag = "yes" if row["sessions_exist"] else "no"
        lines.append(f"  {row['harness']:<14} exists={flag:<3} {row['sessions']}")
        lines.append(f"                 {row['notes']}")
    if report["problems"]:
        lines.append("")
        lines.append("problems:")
        for problem in report["problems"]:
            lines.append(f"  - {problem}")
    else:
        lines.append("")
        lines.append("ok")
    return "\n".join(lines)


def dumps_report(report: dict) -> str:
    return json.dumps(report, indent=2)
