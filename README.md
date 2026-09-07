# Baton

Sidecar model switcher for **Claude Code**, **Codex**, and **Cursor CLI**.

One shared model catalog. Each model has a **home CLI**. The switcher is a separate process (adjacent pane or another window). The coding terminal stays the same window; the operator binary is replaced.

This is **not** a fork of [txcript](https://github.com/skillsynchq/txcript). Txcript converts transcripts. Baton is the control plane: catalog, CLI registration, pane supervisor, and `txcript continue --no-resume` on harness hops.

Apache-2.0.

## Install

Requires **Python 3.11+**. The npm package is a thin launcher. The command is `baton`. Unscoped npm `baton` and PyPI `baton` / `baton-cli` belong to other projects, so this one publishes as `@baton-cli/cli` and `tty-baton`.

```sh
npm install -g @baton-cli/cli
baton init
```

Other options:

```sh
# from this repo
npm install -g .

# pip
python3 -m pip install --user .
# or, once published: python3 -m pip install --user tty-baton

# curl installer (uses npm if present, else pipx/pip)
curl -fsSL https://raw.githubusercontent.com/Mvp2o-ai/baton/main/install.sh | bash
```

[`@batonai/cli`](https://github.com/niketkal/baton) also installs a `baton` binary. If both are on PATH, whichever comes first wins. Their `.baton/` directory is project-local; this product's config is `~/.baton`.

Cross-harness hops need the [txcript CLI](https://github.com/skillsynchq/txcript):

```sh
cargo install --git https://github.com/skillsynchq/txcript txcript-cli
```

## Quick start

Terminal A (the coding pane):

```sh
cd /path/to/repo
baton clis          # toggle detected CLIs; repeat anytime
baton attach --model opus
```

Terminal B (the product / sidecar):

```sh
baton sidecar
# type: gpt
# type: composer
# type: opus
```

Or from any shell:

```sh
baton model gpt
baton status
baton doctor
```

Homes:

| Catalog id | Provider model (default) | Home harness | Binary |
|---|---|---|---|
| `opus` `sonnet` `haiku` | Claude models | `claude_code` | `claude` |
| `gpt` `codex` | GPT / Codex models | `codex` | `codex` |
| `composer` | Cursor models | `cursor` | `agent` |

No desktop apps. Cursor IDE `state.vscdb` is out of scope.

## Session directories

Baton **reads** these trees to list sessions and to recover an id after a CLI exits. Writes on a harness hop are done by **txcript**.

| Harness | Root | Session files | Relocate with |
|---|---|---|---|
| Claude Code | `~/.claude/projects/<encoded-cwd>/` | `<session-id>.jsonl` (sometimes under `sessions/`) | `CLAUDE_CONFIG_DIR` |
| Codex | `$CODEX_HOME/sessions/YYYY/MM/DD/` | `rollout-<timestamp>-<uuid>.jsonl` (listed only when `session_meta.payload.cwd` matches this directory) | `CODEX_HOME` (default `~/.codex`) |
| Cursor CLI | `<cursor-store>/chats/<md5(abs-cwd)>/<uuid>/` | `store.db` + `meta.json` | `CURSOR_STORE_ROOT`, else `CURSOR_DATA_PATH`, else `$XDG_CONFIG_HOME/cursor` if that tree exists, else `~/.cursor` |

Claude project folder encoding (official): the absolute cwd with every non-alphanumeric character replaced by `-`.

Codex also keeps a SQLite thread index under `CODEX_SQLITE_HOME` or `$CODEX_HOME` (`state_*.sqlite`). Txcript registers resume ids there when it writes a Codex copy.

Cursor **CLI** chats are not Cursor **desktop**. Desktop Composer lives in `state.vscdb` under Application Support / `%APPDATA%`. Baton does not touch that.

`baton doctor` prints the resolved paths for the current cwd.

## Config

`~/.baton/config.json` (or `$BATON_HOME`).

Register CLIs whenever you install a new one:

```sh
baton clis
baton clis enable cursor
baton clis set cursor --bin ~/.local/bin/agent
baton clis refresh
```

Cursor’s documented install drops `agent` in `~/.local/bin`. That directory is searched even when it is missing from `PATH`.

## Commands

| Command | Purpose |
|---|---|
| `baton init` | Write config and register detected CLIs |
| `baton clis` | Interactive enable/disable (anytime) |
| `baton attach` | Supervisor in **this** tty; spawns the home CLI |
| `baton sidecar` | Picker UI that sends `set_model` |
| `baton model <id>` | Switch the attached pane |
| `baton model gpt --range 5-` | Hop with a txcript message range |
| `baton status` | Attached panes |
| `baton sessions` | Native sessions on disk for this directory |
| `baton doctor` | CLIs, txcript, directories |
| `baton detach` | Stop the supervisor |
| `baton models` | Catalog |

--json works on `baton models --json`, `status`, `sessions`, `doctor`, and `clis list`.

## How a switch works

1. Sidecar sends `{ "op": "set_model", "model": "gpt" }` on a Unix socket under `~/.baton/sockets/`.
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
node bin/baton.js --version
```

## License

Apache License 2.0. Txcript is a separate Apache-2.0 project; use it as a CLI dependency, do not fork it into this repo.
