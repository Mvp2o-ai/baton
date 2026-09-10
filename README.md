# Baton

Sidecar model switcher for **Claude Code**, **Codex**, and **Cursor CLI**.

One shared model catalog. Each model has a **home CLI**. The switcher is a separate process (adjacent pane or another window). The coding terminal stays the same window; the operator binary is replaced.

**The hop keeps your personal skills.** Claude, Cursor, and Codex each store user skills in a different home. A model switch used to leave those folders behind. After txcript continues the session, Baton inventories user-global skills and asks to directory-symlink anything the destination cannot already see. The real folder stays where you created it. No copies. No third tree. See [Skills come with you](#skills-come-with-you).

**Built on [txcript](https://github.com/skillsynchq/txcript)** (Apache-2.0, [Skillsync](https://github.com/skillsynchq)). Txcript converts a session into another harness’s native format and writes it where that CLI can `--resume`. Baton does not convert transcripts. It is the control plane: catalog, CLI registration, pane supervisor, skill bridging, and `txcript continue --no-resume` on a harness hop. Not a fork.

Apache-2.0.

## Install

Install like any other CLI. Unscoped npm `baton` belongs to another project, so this one is `@batoncli/cli`. The binary name is still `baton`. Python 3.11+ must be on PATH (Homebrew `python3` is fine); the npm package is the launcher plus the Python CLI.

```sh
npm install -g @batoncli/cli
baton init
```

From a clone:

```sh
npm install -g .
baton init
```

Other options:

```sh
# pip
python3 -m pip install --user .
# or, once published: python3 -m pip install --user tty-baton

# curl installer (uses npm if present, else pipx/pip)
curl -fsSL https://raw.githubusercontent.com/Mvp2o-ai/baton/main/install.sh | bash
```

[`@batonai/cli`](https://github.com/niketkal/baton) also installs a `baton` binary. If both are on PATH, whichever comes first wins. Their `.baton/` directory is project-local; this product's config is `~/.baton`.

Cross-harness hops need the [txcript CLI](https://github.com/skillsynchq/txcript):

```sh
cargo install --git https://github.com/wiltshirek/txcript --rev b35b6bee9f996cc2aea58dadef0a54fb5fa1d2fe txcript-cli
```

## Quick start

```sh
cd /path/to/repo
baton claude     # or: baton codex   baton agent
```

First run writes `~/.baton` and installs `/baton` slash hooks, then this terminal becomes that CLI. Same for `baton`, `baton attach`, and `baton init` (init prints the CLI table, then attaches).

Inside Claude, Codex, or Cursor, type **`/baton`** (or `/baton list`). The picker opens in the attach terminal. An IDE chat for that same project uses the hook payload’s workspace (`cwd` / `workspace_roots`), not the hook process directory. Enter hops; `q` keeps the current CLI.

`baton set` in another terminal is a backup. `baton clis` toggles homes if you need to.

Homes:

Each enabled CLI contributes **its home models only**. Claude Code: documented `/model` aliases (plus `settings.json` `availableModels` / `modelPicker`). Codex: union of `codex debug models --bundled` and the live catalog (live is entitlement-thinned). Cursor: Composer and Grok flavors from `agent models` — not the rest of Cursor's kitchen-sink list. Picking a row always launches **that** CLI with that `--model` id.

No desktop apps. Cursor IDE `state.vscdb` is out of scope.

## Skills come with you

This is the hop advantage the other CLIs do not give you.

Personal skills live in **one** provider home. Cursor already scans Claude and `~/.agents` / `~/.codex`. Claude and Codex do **not** scan `~/.cursor/skills`. Without a bridge, Cursor → Claude (and Cursor → Codex) drops the skills you actually use.

On a harness hop, Baton inventories **user-global** skill folders and asks only for names the destination cannot already see:

```text
3 user skills not visible to Claude Code:
  complete-releases  →  ~/.cursor/skills/complete-releases
  …
Link them into ~/.claude/skills? [Y/n]
```

Enter links them. `n` skips. The hop still proceeds. No tty means it logs and does not `ln`.

The real directory stays where it was created. Links are the **whole skill folder**, not `SKILL.md` alone (Codex ignores a file symlink). Cursor and Codex sharing `~/.agents/skills` is the intended layout.

| Created in | Hop to Cursor | Hop to Claude | Hop to Codex |
|---|---|---|---|
| `~/.cursor/skills` | already there | link | link into `~/.agents/skills` |
| `~/.claude/skills` | already visible | already there | link into `~/.agents/skills` |
| `~/.agents/skills` | already visible (shared) | link | already there |

Out of scope: project `.claude/skills` / `.cursor/skills` / `.agents/skills`, Cursor `skills-cursor`, Claude `synced`, Baton's own `/baton` stub, two different real folders with the same name.

| Provider | User-global skills | Relocate with |
|---|---|---|
| Claude Code | `$CLAUDE_CONFIG_DIR/skills` or `~/.claude/skills` | `CLAUDE_CONFIG_DIR` |
| Cursor CLI | `~/.cursor/skills` | — |
| Codex | `~/.agents/skills` (official USER root; shared with Cursor) | — |

Codex still scans `$CODEX_HOME/skills` as a deprecated user root. A skill created there stays there; Baton will not move it. New links go to `~/.agents/skills`.

`baton doctor` prints the resolved skill roots. Path details: [docs/directories.md](docs/directories.md).

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

`baton doctor` prints the resolved session and skill-root paths for the current cwd.

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
| `baton` / `baton attach` | Ensure config + slash hooks, then take over this tty |
| `baton claude` / `codex` / `agent` | Same, starting on that home (`cursor` and `agentx` are aliases for agent). Extra flags go to that CLI |
| `baton init` | Print the CLI table, then attach (`--no-attach` to skip) |
| `baton clis` | Toggle homes (optional) |
| `baton set` | Pick a live model and switch the attached pane (`list`, `select`, `sidecar` are aliases) |
| `baton model <id>` | Switch the attached pane by id (`claude_code:opus`, or a unique `--model` slug) |
| `baton models` | Print the live catalog (non-interactive) |
| `baton status` | Attached panes |
| `baton sessions` | Native sessions on disk for this directory |
| `baton doctor` | CLIs, txcript, session directories, user skill roots |
| `baton detach` | Stop the supervisor |

`--json` works on `baton models --json`, `status`, `sessions`, `doctor`, and `clis list`.

## How a switch works

1. `/baton list` in the home CLI (or `baton set` from another tty) sends `{ "op": "pick" }` or `{ "op": "set_model", ... }` on a Unix socket under `~/.baton/sockets/`.
2. Supervisor stops the current CLI (SIGTERM).
3. If the home harness changed: `txcript continue <id> --from <src> --with <dst> --no-resume`.
4. **Skills come with you:** if the destination cannot already see a **user-global** skill, Baton asks to directory-symlink it into that provider's user skills root. See [Skills come with you](#skills-come-with-you). Enter accepts; `n` skips. The hop is not blocked.
5. Supervisor respawns the **registered** binary with `--model` / `resume` flags documented for that CLI.
6. Same tty. New operator.

Same-harness model changes skip txcript and only change the launch flag.

Attach is POSIX-only (Unix sockets). Use macOS, Linux, or WSL.

## Development

```sh
python3 -m pip install -e ".[dev]"
python3 -m pytest -q
node bin/baton.js --version
```

## License

Apache License 2.0. See `LICENSE` and `NOTICE`.

Cross-harness hops require the [txcript](https://github.com/skillsynchq/txcript) CLI, a separate Apache-2.0 project by Skillsync. Install it yourself; this repo does not vendor or fork it.
