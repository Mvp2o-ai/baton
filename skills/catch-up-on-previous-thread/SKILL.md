---
name: catch-up-on-previous-thread
description: >-
  Read the previous chat for this project from Cursor, Claude Code, or Codex
  JSONL on disk and extract only facts relevant to the current request. Use when
  the user says "catch up on the previous thread", "check the last session",
  "what did we do last time", "read the Claude/Codex/Cursor thread", or any
  phrasing that implies retrieving context from a prior conversation — including
  one started in a different CLI.
---

# Catch Up on Previous Thread

Stay in this CLI. Read the previous thread from disk. Do not hop. Do not
summarize the whole chat — pull only the facts the current request needs.

Baton is optional. This skill only reads JSONL.

## Locate

Scripts live next to this `SKILL.md` (follow directory symlinks). Prefer the
linked copy in a user skill home:

```bash
python3 ~/.cursor/skills/catch-up-on-previous-thread/scripts/locate_previous.py
python3 ~/.claude/skills/catch-up-on-previous-thread/scripts/locate_previous.py
python3 ~/.agents/skills/catch-up-on-previous-thread/scripts/locate_previous.py
```

From a clone of this repo:

```bash
python3 skills/catch-up-on-previous-thread/scripts/locate_previous.py --cwd "$PWD"
```

Newest first. Columns: `harness`, `mtime`, `path`.

Skip the live session (usually the newest file from the CLI you are in). The
previous thread is the next row. If the user named a provider, keep that
harness only (`cursor_ide`, `claude`, `codex`).

Never hardcode a username. The locator derives paths from `$HOME`,
`$CLAUDE_CONFIG_DIR`, and `$CODEX_HOME`.

## Where those files live

| Harness | JSONL |
|---|---|
| Cursor IDE | `~/.cursor/projects/<cwd-with-slashes-as-hyphens>/agent-transcripts/**/*.jsonl` |
| Claude Code | `$CLAUDE_CONFIG_DIR/projects/<encoded-cwd>/**/*.jsonl` (default `~/.claude`) |
| Codex | `$CODEX_HOME/sessions/**/rollout-*.jsonl` whose first line is `session_meta` with `payload.cwd` equal to this directory (also `archived_sessions/`) |

Cursor slug: absolute cwd, `/` → `-`, strip a leading hyphen (`/Users/a/b` → `Users-a-b`).

Claude encoding: absolute cwd, every non-alphanumeric character → `-` (`/Users/a/b` → `-Users-a-b`). Paths longer than 200 characters are truncated with a hash suffix. Prefer the `cwd` field inside the file over reversing the folder name.

Cursor CLI chats are `store.db` under `<cursor-store>/chats/<md5(cwd)>/`. That tree is not JSONL. Ignore it here. A Baton hop is what continues that store.

## Read

**Cursor IDE** — `role` is `user` or `assistant`. `message.content` is a list of `{ "type": "text", "text": "..." }`.

**Claude** — `type` is `user`, `assistant`, or `summary`. `message.content` is a string or a list of blocks (`text`, `thinking`, `tool_use`, `tool_result`). `cwd` is the project. Read `summary` first for a title, then user/assistant text.

**Codex** — first line `type: session_meta`. Turns are `type: response_item` with `payload.type == "message"` and `payload.role` of `user` or `assistant`. Text is in `payload.content[].text` or `input_text`. Skip `developer` / `system` blobs.

## Report

Decisions, files touched, open questions, next steps that the current request
needs. If nothing is relevant, say so and name which session you read.
