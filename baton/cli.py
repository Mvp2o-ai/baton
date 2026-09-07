from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from baton import __version__
from baton.bus import send_request
from baton.catalog import SUPPORTED_HARNESSES, get_model
from baton.clis import discover, enable_found, set_bin, set_enabled
from baton.config import load_config, save_config
from baton.discover import list_sessions, session_to_dict
from baton.doctor import collect_doctor, dumps_report, format_doctor
from baton.panes import list_panes
from baton.sidecar import default_pane_id, set_model, sidecar_loop
from baton.supervisor import attach
from baton.txcript_hop import find_txcript


def _emit(args: argparse.Namespace, payload, text: str) -> int:
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(text)
    return 0


def _print_clis(cfg) -> str:
    lines = [
        "CLI homes  (enable anytime — not a one-time setup)",
        "",
        f"{'#':<4}{'on':<5}{'harness':<14}{'binary':<16}path",
    ]
    for i, harness in enumerate(SUPPORTED_HARNESSES, start=1):
        rec = cfg.clis[harness]
        mark = "x" if rec.enabled else " "
        binary = rec.names[0]
        path = rec.bin or "(not found)"
        lines.append(f"{i:<4}[{mark}]  {harness:<14}{binary:<16}{path}")
    tx = find_txcript(cfg.txcript_bin)
    lines.append("")
    lines.append(f"txcript: {tx or '(not found — needed for cross-harness hops)'}")
    return "\n".join(lines)


def cmd_clis(args: argparse.Namespace) -> int:
    cfg = load_config()
    cfg.clis = discover(cfg.clis)
    interactive = bool(args.interactive) or (
        sys.stdin.isatty() and args.action is None and not args.no_interactive and not args.json
    )
    if args.action in {None, "list"} and not interactive:
        save_config(cfg)
        payload = {
            "clis": {
                h: {"enabled": r.enabled, "bin": r.bin, "found": r.found}
                for h, r in cfg.clis.items()
            },
            "txcript": find_txcript(cfg.txcript_bin),
        }
        return _emit(args, payload, _print_clis(cfg))
    if args.action in {None, "list"} and interactive:
        return _interactive_clis(cfg)
    if args.action == "enable":
        if not args.harness:
            print("baton clis enable <harness>", file=sys.stderr)
            return 2
        set_enabled(cfg.clis, args.harness, True)
        save_config(cfg)
        print(f"enabled {args.harness} ({cfg.clis[args.harness].bin})")
        return 0
    if args.action == "disable":
        if not args.harness:
            print("baton clis disable <harness>", file=sys.stderr)
            return 2
        set_enabled(cfg.clis, args.harness, False)
        save_config(cfg)
        print(f"disabled {args.harness}")
        return 0
    if args.action == "set":
        if not args.harness or not args.bin:
            print("baton clis set <harness> --bin /path", file=sys.stderr)
            return 2
        set_bin(cfg.clis, args.harness, args.bin)
        save_config(cfg)
        print(f"set {args.harness} -> {cfg.clis[args.harness].bin} (enabled)")
        return 0
    if args.action == "refresh":
        cfg.clis = discover(cfg.clis)
        save_config(cfg)
        return _emit(
            args,
            {"clis": {h: {"enabled": r.enabled, "bin": r.bin} for h, r in cfg.clis.items()}},
            _print_clis(cfg),
        )
    print(f"unknown clis action {args.action}", file=sys.stderr)
    return 2


def _interactive_clis(cfg) -> int:
    while True:
        print(_print_clis(cfg))
        print()
        print("toggle 1-3,  a = enable all found,  q = save and quit")
        try:
            line = input("clis> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            save_config(cfg)
            return 0
        if not line:
            continue
        if line in {"q", "quit"}:
            save_config(cfg)
            return 0
        if line == "a":
            for harness in SUPPORTED_HARNESSES:
                rec = cfg.clis[harness]
                if rec.found:
                    rec.enabled = True
            continue
        if line.isdigit():
            idx = int(line) - 1
            if 0 <= idx < len(SUPPORTED_HARNESSES):
                harness = SUPPORTED_HARNESSES[idx]
                rec = cfg.clis[harness]
                if rec.enabled:
                    rec.enabled = False
                else:
                    try:
                        set_enabled(cfg.clis, harness, True)
                    except RuntimeError as exc:
                        print(f"error: {exc}", file=sys.stderr)
            continue
        print("unknown command", file=sys.stderr)


def cmd_models(args: argparse.Namespace) -> int:
    cfg = load_config()
    rows = [
        {"id": m.id, "harness": m.harness, "provider_model": m.provider_model, "label": m.label}
        for m in cfg.models
    ]
    text = "\n".join(
        [f"{'id':<12}{'harness':<14}provider model"]
        + [f"{m.id:<12}{m.harness:<14}{m.provider_model}" for m in cfg.models]
    )
    return _emit(args, {"models": rows}, text)


def cmd_status(args: argparse.Namespace) -> int:
    panes = list_panes()
    payload = [p.to_dict() for p in panes]
    if not panes:
        return _emit(args, {"panes": []}, "no attached panes")
    text = "\n".join(
        f"{p.pane_id}  thread={p.thread_id}  {p.model_id} @ {p.harness}  "
        f"session={p.session_id or '-'}  {'idle' if p.idle else 'live'}  {p.cwd}"
        for p in panes
    )
    return _emit(args, {"panes": payload}, text)


def cmd_model(args: argparse.Namespace) -> int:
    try:
        resp = set_model(args.model, args.pane, args.range)
        pane = resp.get("pane_id") or args.pane or default_pane_id()
        print(f"queued {args.model} → pane {pane}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1


def cmd_attach(args: argparse.Namespace) -> int:
    return attach(
        cwd=Path(args.cwd).resolve() if args.cwd else None,
        thread_id=args.thread,
        model_id=args.model,
        session_id=args.session,
    )


def cmd_sidecar(_args: argparse.Namespace) -> int:
    return sidecar_loop()


def cmd_doctor(args: argparse.Namespace) -> int:
    report = collect_doctor(cwd=Path(args.cwd).resolve() if args.cwd else None)
    if args.json:
        print(dumps_report(report))
    else:
        print(format_doctor(report))
    return 0 if report["ok"] else 1


def cmd_sessions(args: argparse.Namespace) -> int:
    cfg = load_config()
    cwd = Path(args.cwd).resolve() if args.cwd else Path.cwd()
    harnesses = [args.harness] if args.harness else list(SUPPORTED_HARNESSES)
    rows = []
    for harness in harnesses:
        if harness not in cfg.clis and harness not in SUPPORTED_HARNESSES:
            print(f"unknown harness {harness}", file=sys.stderr)
            return 2
        for item in list_sessions(harness, cwd):
            rows.append(session_to_dict(item))
    if args.json:
        print(json.dumps({"cwd": str(cwd), "sessions": rows}, indent=2))
        return 0
    if not rows:
        print("no sessions found for this directory")
        return 0
    print(f"{'harness':<14}{'session_id':<40}path")
    for row in rows:
        print(f"{row['harness']:<14}{row['session_id']:<40}{row['path']}")
    return 0


def cmd_detach(args: argparse.Namespace) -> int:
    try:
        pid = args.pane or default_pane_id()
        resp = send_request(pid, {"op": "detach"})
        if not resp.get("ok"):
            print(f"error: {resp.get('error')}", file=sys.stderr)
            return 1
        print(f"detached pane {pid}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1


def cmd_init(args: argparse.Namespace) -> int:
    cfg = load_config()
    cfg.clis = enable_found(cfg.clis)
    save_config(cfg)
    from baton.paths import config_path

    print(f"wrote {config_path()}")
    print(_print_clis(cfg))
    if not args.skip_interactive and sys.stdin.isatty() and not getattr(args, "json", False):
        return _interactive_clis(cfg)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baton",
        description="Sidecar model switcher for Claude Code, Codex, and Cursor CLI.",
    )
    parser.add_argument("--version", action="version", version=f"baton {__version__}")
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="cmd", required=True)

    clis = sub.add_parser(
        "clis",
        parents=[json_parent],
        help="Discover and enable installed CLI homes (anytime)",
    )
    clis.add_argument(
        "action",
        nargs="?",
        choices=["list", "enable", "disable", "set", "refresh"],
        default=None,
    )
    clis.add_argument("harness", nargs="?", help="claude_code | codex | cursor")
    clis.add_argument("--bin", dest="bin", help="explicit binary path (with set)")
    clis.add_argument("-i", "--interactive", action="store_true")
    clis.add_argument("--no-interactive", action="store_true")
    clis.set_defaults(func=cmd_clis)

    models = sub.add_parser("models", parents=[json_parent], help="Show the shared model catalog")
    models.set_defaults(func=cmd_models)

    status = sub.add_parser("status", parents=[json_parent], help="List attached terminal panes")
    status.set_defaults(func=cmd_status)

    model = sub.add_parser("model", help="Tell an attached pane to switch models")
    model.add_argument("model")
    model.add_argument("--pane")
    model.add_argument(
        "--range",
        dest="range",
        help="txcript message range to continue, e.g. 5- or 12",
    )
    model.set_defaults(func=cmd_model)

    att = sub.add_parser("attach", help="Take over this terminal and spawn the home CLI")
    att.add_argument("--cwd")
    att.add_argument("--thread")
    att.add_argument("--model", help="starting catalog id (default: first model)")
    att.add_argument("--session", help="existing native session id to resume")
    att.set_defaults(func=cmd_attach)

    side = sub.add_parser("sidecar", help="Interactive picker that drives attached panes")
    side.set_defaults(func=cmd_sidecar)

    doctor = sub.add_parser(
        "doctor",
        parents=[json_parent],
        help="Check CLIs, txcript, and session directories",
    )
    doctor.add_argument("--cwd")
    doctor.set_defaults(func=cmd_doctor)

    sessions = sub.add_parser(
        "sessions",
        parents=[json_parent],
        help="List native sessions on disk for this directory",
    )
    sessions.add_argument("--cwd")
    sessions.add_argument("--harness", choices=list(SUPPORTED_HARNESSES))
    sessions.set_defaults(func=cmd_sessions)

    detach = sub.add_parser("detach", help="Ask an attached pane supervisor to exit")
    detach.add_argument("--pane")
    detach.set_defaults(func=cmd_detach)

    init = sub.add_parser(
        "init",
        parents=[json_parent],
        help="Write config and register detected CLIs",
    )
    init.add_argument("--skip-interactive", action="store_true")
    init.set_defaults(func=cmd_init)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (KeyError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
