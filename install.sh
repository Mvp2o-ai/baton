#!/usr/bin/env bash
# Install baton via npm (preferred) or pip.
#   curl -fsSL https://raw.githubusercontent.com/Mvp2o-ai/baton/main/install.sh | bash
set -euo pipefail

need_python() {
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
    return
  fi
  echo "baton needs Python 3.11+" >&2
  exit 1
}

need_python

if command -v npm >/dev/null 2>&1; then
  echo "Installing @baton-cli/cli with npm -g"
  npm install -g @baton-cli/cli
  echo "Run: baton init"
  exit 0
fi

if command -v pipx >/dev/null 2>&1; then
  echo "npm not found; installing with pipx"
  pipx install tty-baton
  echo "Run: baton init"
  exit 0
fi

echo "npm not found; installing with python3 -m pip --user"
python3 -m pip install --user tty-baton
echo "Run: baton init"
echo "If the command is missing, add your user pip bin dir to PATH."
