from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from baton.clis import discover
from baton.config import load_config
from baton.dirs import describe_all
from baton.skill_bridge import describe_skill_roots
from baton.style import brass, cyan, dim, err, heading, ok
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
    skills = []
    for item in describe_skill_roots():
        path = Path(item["path"])
        skills.append(
            {
                **item,
                "exists": path.is_dir(),
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
        "skill_roots": skills,
        "problems": problems,
    }


def format_doctor(report: dict) -> str:
    stream = sys.stdout
    tx = report["txcript"] or "(missing)"
    lines = [
        heading("baton doctor", stream=stream),
        f"{dim('python', stream=stream)}     {report['python']}",
        f"{dim('platform', stream=stream)}   {report['platform']}",
        f"{dim('cwd', stream=stream)}        {report['cwd']}",
        f"{dim('txcript', stream=stream)}    {tx if report['txcript'] else err(tx, stream=stream)}",
        "",
        heading("CLI homes", stream=stream),
    ]
    for row in report["clis"]:
        mark = "on " if row["enabled"] else "off"
        path = row["bin"] or "not found"
        body = f"  [{mark}] {row['harness']:<14} {path}"
        lines.append(brass(body, stream=stream) if row["enabled"] else dim(body, stream=stream))
    lines.append("")
    lines.append(heading("Session directories (for this cwd)", stream=stream))
    for row in report["directories"]:
        flag = "yes" if row["sessions_exist"] else "no"
        harness = cyan(f"{row['harness']:<14}", stream=stream)
        lines.append(f"  {harness} exists={flag:<3} {row['sessions']}")
        lines.append(dim(f"                 {row['notes']}", stream=stream))
    lines.append("")
    lines.append(heading("User skill roots", stream=stream))
    for row in report.get("skill_roots") or []:
        flag = "yes" if row.get("exists") else "no"
        harness = cyan(f"{row['harness']:<14}", stream=stream)
        lines.append(f"  {harness} exists={flag:<3} {row['path']}")
        lines.append(dim(f"                 {row['notes']}", stream=stream))
    if report["problems"]:
        lines.append("")
        lines.append(err("problems:", stream=stream))
        for problem in report["problems"]:
            lines.append(err(f"  - {problem}", stream=stream))
    else:
        lines.append("")
        lines.append(ok("ok", stream=stream))
    return "\n".join(lines)


def dumps_report(report: dict) -> str:
    return json.dumps(report, indent=2)
