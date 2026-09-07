#!/usr/bin/env bash
# Install homeswitch via npm (preferred) or pip.
#   curl -fsSL https://raw.githubusercontent.com/homeswitch/homeswitch/main/install.sh | bash
set -euo pipefail

need_python() {
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
    return
  fi
  echo "homeswitch needs Python 3.11+" >&2
  exit 1
}

need_python

if command -v npm >/dev/null 2>&1; then
  echo "Installing homeswitch with npm -g"
  npm install -g homeswitch
  echo "Run: homeswitch init"
  exit 0
fi

if command -v pipx >/dev/null 2>&1; then
  echo "npm not found; installing with pipx"
  pipx install homeswitch
  echo "Run: homeswitch init"
  exit 0
fi

echo "npm not found; installing with python3 -m pip --user"
python3 -m pip install --user homeswitch
echo "Run: homeswitch init"
echo "If the command is missing, add your user pip bin dir to PATH."
