# Changelog

## Unreleased

- Picker catalogs stay current: Codex lists GPT-5.6 and newer only; Claude Code adds recent Sonnet / Opus / Fable IDs (`claude-opus-5`, `claude-sonnet-5`, `claude-fable-5-1`, …) and keeps aliases, not older 4.x pins. Cursor stays Composer + Grok (Cursor Models pool).
- Recover control sockets and pane records in flight; disconnected or stalled hooks no longer take down the listener, and health-check timeouts do not delete a live supervisor's socket.
- Reuse the attach's model catalog, keep successful rows on refresh failure, and retain bundled/cached Codex models after catalog timeouts. Model discovery runs concurrently with stdin disconnected.
- Keep `/baton` and resume controls working after CLI exit; retry crashes with the saved session and restore the source after failed handoffs or destination startup. Scope delayed termination to the original child, handle picker Escape/EOF, and bound transcript conversion waits.
- Closing the attach tty (SIGHUP) unlinks the pane socket immediately; a crashed leftover is still reaped on the next list/status/detach/attach. `baton detach` after Connection refused is not a stuck state.
- `baton claude|codex|agent` forwards unknown flags to that home CLI (`--resume=…`, `--print`, `resume <id>`, …). `--cwd` / `--thread` / `--model` / `--session` stay Baton's.
- `/baton` from Cursor, Claude, and Codex hooks matches the live pane using the hook payload’s project directory (`workspace_roots` / `cwd`, then transcript path), not the hook process working directory. Cursor IDE chats no longer fail as “not attached (`~/.cursor`)” when that project already has a pane.
- On a harness hop, request directory symlinks so the destination CLI can see user-global skills created in another provider. The real folder stays where it was created. Cursor already sharing `~/.agents` with Codex is expected; hops to Cursor skip links those trees already expose.
- README and `docs/directories.md` lead with that hop: skills come with you (prompt, hop matrix, what is out of scope).

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
