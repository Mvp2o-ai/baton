# Session directories (verified 2026-09)

Sources: Claude Code sessions docs, OpenAI Codex `CODEX_HOME`, txcript 0.13 store defaults, Cursor CLI / store-stack writeups.

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
