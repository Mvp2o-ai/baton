# Changelog

## 0.1.0

- First public release: sidecar model switcher, CLI registration, txcript hops.
- Canonical session roots for Claude Code, Codex, and Cursor CLI (no desktop).
- Config lives in `~/.baton` (`BATON_HOME`).
- `baton init` enables CLIs that are actually on PATH (missing harnesses are not treated as user-disabled).
- Codex session listing is scoped to `session_meta.payload.cwd`.
