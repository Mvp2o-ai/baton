# Homeswitch

Sidecar model switcher for **Claude Code**, **Codex**, and **Cursor CLI**.

One shared model catalog. Each model has a **home CLI**. The switcher is a separate process (adjacent pane or another window). The coding terminal stays the same window; the operator binary is replaced.

This is **not** a fork of [txcript](https://github.com/skillsynchq/txcript). Txcript converts transcripts. Homeswitch is the control plane: catalog, CLI registration, pane supervisor, and `txcript continue --no-resume` on harness hops.

Apache-2.0.

## Install

Requires **Python 3.11+**. The npm package is a thin launcher.

```sh
npm install -g homeswitch
homeswitch init
```

Other options:

```sh
# from this repo
npm install -g .

# pip
python3 -m pip install --user .

# curl installer (uses npm if present, else pipx/pip)
curl -fsSL https://raw.githubusercontent.com/homeswitch/homeswitch/main/install.sh | bash
```

Cross-harness hops need the [txcript CLI](https://github.com/skillsynchq/txcript):

```sh
cargo install --git https://github.com/skillsynchq/txcript txcript-cli
```

## Quick start

Terminal A (the coding pane):

```sh
cd /path/to/repo
homeswitch clis          # toggle detected CLIs; repeat anytime
homeswitch attach --model opus
```

Terminal B (the product / sidecar):

```sh
homeswitch sidecar
# type: gpt
# type: composer
# type: opus
```

Or from any shell:

```sh
homeswitch model gpt
homeswitch status
homeswitch doctor
```

Homes:

| Catalog id | Provider model (default) | Home harness | Binary |
|---|---|---|---|
| `opus` `sonnet` `haiku` | Claude models | `claude_code` | `claude` |
| `gpt` `codex` | GPT / Codex models | `codex` | `codex` |
| `composer` | Cursor models | `cursor` | `agent` |

No desktop apps. Cursor IDE `state.vscdb` is out of scope.

## Session directories

Homeswitch **reads** these trees to list sessions and to recover an id after a CLI exits. Writes on a harness hop are done by **txcript**.

| Harness | Root | Session files | Relocate with |
|---|---|---|---|
| Claude Code | `~/.claude/projects/<encoded-cwd>/` | `<session-id>.jsonl` (sometimes under `sessions/`) | `CLAUDE_CONFIG_DIR` |
| Codex | `$CODEX_HOME/sessions/YYYY/MM/DD/` | `rollout-<timestamp>-<uuid>.jsonl` | `CODEX_HOME` (default `~/.codex`) |
| Cursor CLI | `<cursor-store>/chats/<md5(abs-cwd)>/<uuid>/` | `store.db` + `meta.json` | `CURSOR_STORE_ROOT`, else `CURSOR_DATA_PATH`, else `$XDG_CONFIG_HOME/cursor` if that tree exists, else `~/.cursor` |

Claude project folder encoding (official): the absolute cwd with every non-alphanumeric character replaced by `-`.

Codex also keeps a SQLite thread index under `CODEX_SQLITE_HOME` or `$CODEX_HOME` (`state_*.sqlite`). Txcript registers resume ids there when it writes a Codex copy.

Cursor **CLI** chats are not Cursor **desktop**. Desktop Composer lives in `state.vscdb` under Application Support / `%APPDATA%`. Homeswitch does not touch that.

`homeswitch doctor` prints the resolved paths for the current cwd.

## Config

`~/.homeswitch/config.json` (or `$HOMESWITCH_HOME`).

Register CLIs whenever you install a new one:

```sh
homeswitch clis
homeswitch clis enable cursor
homeswitch clis set cursor --bin ~/.local/bin/agent
homeswitch clis refresh
```

Cursor’s documented install drops `agent` in `~/.local/bin`. That directory is searched even when it is missing from `PATH`.

## Commands

| Command | Purpose |
|---|---|
| `homeswitch init` | Write config and register detected CLIs |
| `homeswitch clis` | Interactive enable/disable (anytime) |
| `homeswitch attach` | Supervisor in **this** tty; spawns the home CLI |
| `homeswitch sidecar` | Picker UI that sends `set_model` |
| `homeswitch model <id>` | Switch the attached pane |
| `homeswitch model gpt --range 5-` | Hop with a txcript message range |
| `homeswitch status` | Attached panes |
| `homeswitch sessions` | Native sessions on disk for this directory |
| `homeswitch doctor` | CLIs, txcript, directories |
| `homeswitch detach` | Stop the supervisor |
| `homeswitch models` | Catalog |

--json works on `homeswitch models --json`, `status`, `sessions`, `doctor`, and `clis list`.

## How a switch works

1. Sidecar sends `{ "op": "set_model", "model": "gpt" }` on a Unix socket under `~/.homeswitch/sockets/`.
2. Supervisor stops the current CLI (SIGTERM).
3. If the home harness changed: `txcript continue <id> --from <src> --with <dst> --no-resume`.
4. Supervisor respawns the **registered** binary with `--model` / `resume` flags documented for that CLI.
5. Same tty. New operator.

Same-harness model changes skip txcript and only change the launch flag.

Attach is POSIX-only (Unix sockets). Use macOS, Linux, or WSL.

## Development

```sh
python3 -m pip install -e ".[dev]"
python3 -m pytest -q
node bin/homeswitch.js --version
```

## License

Apache License 2.0. Txcript is a separate Apache-2.0 project; use it as a CLI dependency, do not fork it into this repo.
