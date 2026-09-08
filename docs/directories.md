# Session directories and skill roots (verified 2026-09)

Sources: Claude Code sessions docs, OpenAI Codex `CODEX_HOME`, txcript 0.13 store defaults, Cursor CLI / store-stack writeups.

Baton hops keep more than the transcript. After txcript writes the destination store, Baton bridges **user-global skills** so the next CLI can see the personal folders you already have. Session paths are below; skill bridging is in [User-global skills](#user-global-skills).

## Claude Code

- Config: `$CLAUDE_CONFIG_DIR` or `~/.claude`
- Transcripts: `<config>/projects/<encoded-cwd>/<session-id>.jsonl`
- Encoding: non-alphanumeric → `-`. Very long paths are truncated with a hash suffix.
- Some versions also use `<project>/sessions/<id>.jsonl`. Baton lists both.

## Codex CLI

- Home: `$CODEX_HOME` or `~/.codex`
- Rollouts: `<home>/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl`
- Archive: `<home>/archived_sessions/`
- SQLite index: `$CODEX_SQLITE_HOME` or `<home>/state_*.sqlite`
- Baton keeps only rollouts whose first line is `session_meta` with `payload.cwd` equal to the current directory. Codex pools all projects in one date-sharded tree.

## Cursor CLI (not desktop)

- Store root: `CURSOR_STORE_ROOT`, else `CURSOR_DATA_PATH` if it is a store tree, else `$XDG_CONFIG_HOME/cursor` when that tree exists, else `~/.cursor`
- Chats: `<store>/chats/<md5(absolute-cwd)>/<session-uuid>/store.db`
- Binary: `agent` (also `cursor-agent`), often `~/.local/bin/agent`
- Resume: `agent --resume=<id>`

Cursor desktop Composer (`state.vscdb` under Application Support / `%APPDATA%`) is not a supported home harness.

## User-global skills (verified 2026-09)

Sources: Claude Code skills docs, OpenAI Codex skills docs, Cursor skills docs / CLI 2.5+ symlink fix.

**Why this is the hop advantage.** Each CLI invented its own user-global skills home. Cursor already scans Claude and the shared `~/.agents` / `~/.codex` trees. Claude and Codex do not scan `~/.cursor/skills`. A Cursor → Claude hop used to keep the thread and drop the skills. Baton inventories those roots on switch and asks to directory-symlink anything the destination cannot already see. The real folder stays where it was created. No copies. No third Baton tree.

On a tty:

```text
3 user skills not visible to Claude Code:
  complete-releases  →  ~/.cursor/skills/complete-releases
  …
Link them into ~/.claude/skills? [Y/n]
```

Enter links them. `n` skips. The hop is not blocked. No tty: log and skip `ln`. `baton doctor` lists the resolved roots.

| Created in | Hop to Cursor | Hop to Claude | Hop to Codex |
|---|---|---|---|
| `~/.cursor/skills` | already there | link | link into `~/.agents/skills` |
| `~/.claude/skills` | already visible | already there | link into `~/.agents/skills` |
| `~/.agents/skills` | already visible (shared) | link | already there |

Baton only bridges **user-global** skills on a hop. Project trees (`.claude/skills`, `.cursor/skills`, `.agents/skills`) stay out of this.

| Provider | User-global skills | Relocate with |
|---|---|---|
| Claude Code | `$CLAUDE_CONFIG_DIR/skills` or `~/.claude/skills` | `CLAUDE_CONFIG_DIR` |
| Cursor CLI | `~/.cursor/skills` | — |
| Codex | `~/.agents/skills` | — |

Codex also still reads `$CODEX_HOME/skills` (deprecated USER root). New links are written to `~/.agents/skills`. A skill created under the deprecated root stays there; Baton will not move it.

Do not touch:

- `~/.cursor/skills-cursor` (Cursor built-ins)
- Claude reserved name `synced`
- Baton's managed `/baton` stub
- Codex SYSTEM / ADMIN / `$CODEX_HOME/skills/.system`
- Two different real folders that already share a name (left unlinked)

A personal skill folder may be a directory symlink. Codex skips a symlinked `SKILL.md` file; link the folder. Cursor CLI follows per-skill folder symlinks (fixed around `2026.02.27`). Claude follows directory symlinks and dedupes the same target.

Cursor already scans `~/.claude/skills`, `~/.codex/skills`, and `~/.agents/skills`. Claude and Codex do not scan `~/.cursor/skills`. That is why hops *to* Cursor usually need no extra link, and hops *from* Cursor usually do.
