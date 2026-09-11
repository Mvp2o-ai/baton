from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from baton import __version__
from baton.bus import send_request
from baton.catalog import HOME_COMMANDS, SUPPORTED_HARNESSES
from baton.clis import discover, enable_found, set_bin, set_enabled
from baton.config import load_config, save_config
from baton.discover import list_sessions, session_to_dict
from baton.doctor import collect_doctor, dumps_report, format_doctor
from baton.panes import list_panes, panes_for_cwd, remove_pane
from baton.picker import format_catalog
from baton.provider_models import collect_catalog
from baton.sidecar import default_pane_id, set_loop, set_model
from baton.style import brass, cyan, dim, err, heading, log, magenta, ok, print_logo
from baton.supervisor import attach
from baton.txcript_hop import find_txcript
from baton.txcript_parse import session_id_from_argv

_PASSTHROUGH_CMDS = frozenset({None, "attach", "init", *HOME_COMMANDS})


def _emit(args: argparse.Namespace, payload, text: str) -> int:
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(text)
    return 0


def _print_clis(cfg) -> str:
    stream = sys.stdout
    lines = [
        heading("CLI homes", stream=stream),
        "",
        dim(f"{'#':<4}{'on':<5}{'harness':<14}{'binary':<16}path", stream=stream),
    ]
    for i, harness in enumerate(SUPPORTED_HARNESSES, start=1):
        rec = cfg.clis[harness]
        mark = "x" if rec.enabled else " "
        binary = rec.names[0]
        path = rec.bin or "(not found)"
        row = f"{i:<4}[{mark}]  {harness:<14}{binary:<16}{path}"
        if rec.enabled:
            lines.append(brass(row, stream=stream))
        else:
            lines.append(dim(row, stream=stream))
    tx = find_txcript(cfg.txcript_bin)
    lines.append("")
    if tx:
        lines.append(f"{cyan('txcript', stream=stream)}  {tx}")
    else:
        lines.append(err("txcript  (not found — needed for cross-harness hops)", stream=stream))
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
            print(err("baton clis enable <harness>", stream=sys.stderr), file=sys.stderr)
            return 2
        set_enabled(cfg.clis, args.harness, True)
        save_config(cfg)
        print(ok(f"enabled {args.harness} ({cfg.clis[args.harness].bin})"))
        return 0
    if args.action == "disable":
        if not args.harness:
            print(err("baton clis disable <harness>", stream=sys.stderr), file=sys.stderr)
            return 2
        set_enabled(cfg.clis, args.harness, False)
        save_config(cfg)
        print(dim(f"disabled {args.harness}"))
        return 0
    if args.action == "set":
        if not args.harness or not args.bin:
            print(err("baton clis set <harness> --bin /path", stream=sys.stderr), file=sys.stderr)
            return 2
        set_bin(cfg.clis, args.harness, args.bin)
        save_config(cfg)
        print(ok(f"set {args.harness} -> {cfg.clis[args.harness].bin} (enabled)"))
        return 0
    if args.action == "refresh":
        cfg.clis = discover(cfg.clis)
        save_config(cfg)
        return _emit(
            args,
            {"clis": {h: {"enabled": r.enabled, "bin": r.bin} for h, r in cfg.clis.items()}},
            _print_clis(cfg),
        )
    print(err(f"unknown clis action {args.action}", stream=sys.stderr), file=sys.stderr)
    return 2


def _interactive_clis(cfg) -> int:
    while True:
        print(_print_clis(cfg))
        print()
        print(dim("1-3 toggle   a enable all found   q or enter to finish"))
        try:
            line = input(magenta("clis> ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            save_config(cfg)
            return 0
        if not line or line in {"q", "quit"}:
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
                        print(err(f"error: {exc}", stream=sys.stderr), file=sys.stderr)
            continue
        print(err("unknown — 1-3 toggle, a enable all, q finish", stream=sys.stderr), file=sys.stderr)


def cmd_models(args: argparse.Namespace) -> int:
    cfg = load_config()
    models, errors = collect_catalog(cfg.clis)
    rows = [
        {"id": m.key, "harness": m.harness, "provider_model": m.provider_model, "label": m.label}
        for m in models
    ]
    payload = {"models": rows, "errors": errors}
    text = format_catalog(models, errors=errors)
    if not text:
        text = "no models"
    return _emit(args, payload, text)


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
        print(ok(f"queued {args.model} → pane {pane}"))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(err(f"error: {exc}", stream=sys.stderr), file=sys.stderr)
        return 1


def _ensure_ready(*, verbose: bool = False) -> tuple:
    cfg = load_config()
    cfg.clis = enable_found(cfg.clis)
    save_config(cfg)
    try:
        from baton.slash_install import install as install_slash

        installed = install_slash()
    except OSError as exc:
        installed = []
        if verbose:
            print(err(f"slash commands: {exc}", stream=sys.stderr), file=sys.stderr)
    return cfg, installed


def _already_attached(workdir: Path):
    return panes_for_cwd(workdir)


def cmd_set(_args: argparse.Namespace) -> int:
    return set_loop()


def cmd_hook(args: argparse.Namespace) -> int:
    from baton.hook import main as hook_main

    argv = ["--reply", args.reply]
    return hook_main(argv)


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
            print(err(f"unknown harness {harness}", stream=sys.stderr), file=sys.stderr)
            return 2
        for item in list_sessions(harness, cwd):
            rows.append(session_to_dict(item))
    if args.json:
        print(json.dumps({"cwd": str(cwd), "sessions": rows}, indent=2))
        return 0
    if not rows:
        print("no sessions found for this directory")
        return 0
    print(dim(f"{'harness':<14}{'session_id':<40}path"))
    for row in rows:
        harness = cyan(f"{row['harness']:<14}")
        print(f"{harness}{row['session_id']:<40}{row['path']}")
    return 0


def cmd_detach(args: argparse.Namespace) -> int:
    pane_id = getattr(args, "pane", None)
    if not pane_id:
        local = panes_for_cwd()
        if not local:
            print(ok("nothing attached here"))
            return 0
        if len(local) > 1:
            ids = ", ".join(p.pane_id for p in local)
            print(
                err(
                    f"This directory has more than one attach ({ids}). "
                    "baton detach --pane <id>",
                    stream=sys.stderr,
                ),
                file=sys.stderr,
            )
            return 1
        pane_id = local[0].pane_id
    try:
        resp = send_request(pane_id, {"op": "detach"})
        if not resp.get("ok"):
            print(err(f"error: {resp.get('error')}", stream=sys.stderr), file=sys.stderr)
            return 1
        print(ok(f"detached pane {pane_id}"))
        return 0
    except (FileNotFoundError, ConnectionError, TimeoutError, OSError):
        remove_pane(pane_id)
        print(ok(f"cleared stale pane {pane_id}"))
        return 0


def cmd_attach(args: argparse.Namespace) -> int:
    _ensure_ready(verbose=False)
    workdir = Path(args.cwd).resolve() if getattr(args, "cwd", None) else Path.cwd()
    live = _already_attached(workdir)
    if live:
        pane = live[0]
        log(
            f"already attached here ({pane.pane_id} → {pane.model_id}). "
            f"type /baton in that terminal, or: baton detach",
            kind="error",
        )
        return 1
    extras = list(getattr(args, "provider_args", None) or [])
    session = getattr(args, "session", None) or session_id_from_argv(extras)
    return attach(
        cwd=workdir,
        thread_id=getattr(args, "thread", None),
        model_id=getattr(args, "model", None),
        session_id=session,
        harness=getattr(args, "harness", None),
        extra_args=extras,
    )


def cmd_init(args: argparse.Namespace) -> int:
    from baton.paths import config_path

    cfg, installed = _ensure_ready(verbose=not getattr(args, "json", False))
    if getattr(args, "json", False):
        payload = {
            "config": str(config_path()),
            "clis": {
                h: {"enabled": r.enabled, "bin": r.bin, "found": r.found}
                for h, r in cfg.clis.items()
            },
            "txcript": find_txcript(cfg.txcript_bin),
            "slash": installed,
        }
        print(json.dumps(payload, indent=2))
        return 0
    skip_logo = not getattr(args, "no_attach", False) and sys.stdin.isatty()
    if not skip_logo:
        print_logo(file=sys.stdout, tagline="hand off the thread")
        print()
    print(dim(f"wrote {config_path()}"))
    print(_print_clis(cfg))
    if installed:
        print()
        print(ok("installed /baton slash commands for Claude, Codex, and Cursor."))
    if getattr(args, "no_attach", False) or not sys.stdin.isatty():
        print()
        print(dim("next: cd /path/to/project && baton claude|codex|agent"))
        return 0
    print()
    print(brass("attaching this terminal…  /baton switches models."))
    return cmd_attach(args)


def _add_attach_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cwd")
    parser.add_argument("--thread")
    parser.add_argument("--model", help="starting --model id; omit to use the home default")
    parser.add_argument(
        "--session",
        help="Baton-only: native session id if you are not passing the home CLI's resume flag",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baton",
        description="One terminal for Claude Code, Codex, and Cursor CLI. /baton switches.",
    )
    parser.add_argument("--version", action="version", version=f"baton {__version__}")
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument("--json", action="store_true", help="machine-readable output")
    parser.set_defaults(
        func=cmd_attach,
        harness=None,
        cwd=None,
        thread=None,
        model=None,
        session=None,
        json=False,
        no_attach=False,
        provider_args=None,
    )
    sub = parser.add_subparsers(dest="cmd", required=False)

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

    models = sub.add_parser(
        "models",
        parents=[json_parent],
        help="List models sourced from each enabled home CLI",
    )
    models.set_defaults(func=cmd_models)

    status = sub.add_parser("status", parents=[json_parent], help="List attached terminal panes")
    status.set_defaults(func=cmd_status)

    model = sub.add_parser("model", help="Tell an attached pane to switch models")
    model.add_argument("model", help="model key from `baton models`, or a unique --model id")
    model.add_argument("--pane")
    model.add_argument(
        "--range",
        dest="range",
        help="txcript message range to continue, e.g. 5- or 12",
    )
    model.set_defaults(func=cmd_model)

    att = sub.add_parser("attach", help="Take over this terminal (same as `baton`)")
    _add_attach_flags(att)
    att.set_defaults(func=cmd_attach, harness=None)

    for name, harness in HOME_COMMANDS.items():
        home = sub.add_parser(name, help=f"Attach and start {harness}")
        _add_attach_flags(home)
        home.set_defaults(func=cmd_attach, harness=harness)

    set_p = sub.add_parser(
        "set",
        aliases=["list", "select", "sidecar"],
        help="Pick a live model and switch the attached pane (backup for /baton)",
    )
    set_p.set_defaults(func=cmd_set)

    hook = sub.add_parser(
        "hook",
        help="Internal: handle /baton from a home CLI prompt hook",
    )
    hook.add_argument(
        "--reply",
        choices=["claude", "codex", "cursor"],
        default="claude",
    )
    hook.set_defaults(func=cmd_hook)

    doctor = sub.add_parser(
        "doctor",
        parents=[json_parent],
        help="Check CLIs, txcript, session directories, and user skill roots",
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
        help="Write config and slash hooks, then attach if this is a tty",
    )
    init.add_argument("--no-attach", action="store_true", help="set up only; do not take over this tty")
    _add_attach_flags(init)
    init.set_defaults(func=cmd_init)

    return parser


def parse_cli(
    argv: list[str] | None = None,
) -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = build_parser()
    args, unknown = parser.parse_known_args(argv)
    cmd = getattr(args, "cmd", None)
    allow = cmd in _PASSTHROUGH_CMDS
    if cmd == "init" and getattr(args, "no_attach", False):
        allow = False
    if unknown and not allow:
        parser.error("unrecognized arguments: " + " ".join(unknown))
    args.provider_args = unknown
    return parser, args


def main(argv: list[str] | None = None) -> int:
    parser, args = parse_cli(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    try:
        return func(args)
    except (KeyError, RuntimeError) as exc:
        print(err(f"error: {exc}", stream=sys.stderr), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
