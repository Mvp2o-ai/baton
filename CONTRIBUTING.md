# Contributing

Baton is Apache-2.0. Issues and pull requests are welcome.

`main` is protected: changes go through a PR, and the `CI` check must pass. Direct pushes are blocked. There is one maintainer (`wiltshirek`); GitHub does not count self-approvals, so required review count is zero until there is a second reviewer. Fork PRs are welcome.

## Setup

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
```

Do not execute vendor CLIs (`claude`, `codex`, `agent`) just to read `--help`. Path detection uses `PATH` lookup only. Session directories are documented in `baton/dirs.py` with links to the vendor/txcript sources.

## Scope

- Claude models always home to Claude Code CLI (`claude_code`).
- GPT / Codex models always home to Codex CLI (`codex`).
- Composer / Cursor models always home to Cursor CLI (`cursor` / `agent`).
- No Cursor desktop (`state.vscdb`) and no Claude Desktop.

The converter is [txcript](https://github.com/skillsynchq/txcript). Hop-blocking writer fixes land on the documented pin remote first (`wiltshirek/txcript`), then this repo’s pin (README, CI, `baton/txcript_pin.py`) bumps in the same product change. A clone plus the README `cargo install --git … --rev` must hop. Do not vendor a fork unless a store-writer bug cannot be upstreamed.
