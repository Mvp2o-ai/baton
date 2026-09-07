# Changelog

## 0.1.0

- First public release: sidecar model switcher, CLI registration, txcript hops.
- Canonical session roots for Claude Code, Codex, and Cursor CLI (no desktop).
- Config lives in `~/.baton` (`BATON_HOME`).
- `baton set` (aliases: `list`, `select`, `sidecar`) is the live model picker; no typed catalog ids.
- Install as a global npm CLI from the repo with `npm install -g .` (`@baton-cli/cli` is not on the public registry yet).
- Claude Code lineup comes from documented `/model` aliases plus user settings; Codex from `codex debug models`; Cursor from `agent models`.
- `baton`, `baton attach`, and `baton claude`/`codex`/`agent` are the one-terminal entry: init if needed, then attach. `/baton` inside the CLI opens the model list.
- `/baton` is intercepted in the attach PTY, so Codex still switches even though it rejects unknown slash commands and never sends them to hooks.
- Codex session listing is scoped to `session_meta.payload.cwd`.
