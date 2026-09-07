# Changelog

## 0.1.0

- First public release: sidecar model switcher, CLI registration, txcript hops. Txcript is credited as the converter (README + NOTICE); this repo does not vendor it.
- Canonical session roots for Claude Code, Codex, and Cursor CLI (no desktop).
- Config lives in `~/.baton` (`BATON_HOME`).
- `baton set` (aliases: `list`, `select`, `sidecar`) is the live model picker; no typed catalog ids.
- Install as a global npm CLI: `npm install -g @batoncli/cli` (binary name `baton`).
- Claude Code lineup comes from documented `/model` aliases plus user settings; Codex unions bundled + live `codex debug models` (including `visibility: hide`); Cursor is Composer + Grok flavors only.
- `baton`, `baton attach`, and `baton claude`/`codex`/`agent` are the one-terminal entry: init if needed, then attach. `/baton` inside the CLI opens the model list.
- `/baton` is intercepted in the attach PTY, so Codex still switches even though it rejects unknown slash commands and never sends them to hooks.
- Codex session listing is scoped to `session_meta.payload.cwd`.
