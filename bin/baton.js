#!/usr/bin/env node
"use strict";

const { spawn, spawnSync } = require("child_process");
const path = require("path");

const root = path.resolve(__dirname, "..");
const env = { ...process.env };
env.PYTHONPATH = root + path.delimiter + (env.PYTHONPATH || "");

function pickPython() {
  const candidates = [process.env.BATON_PYTHON, "python3", "python"].filter(Boolean);
  for (const bin of candidates) {
    const result = spawnSync(
      bin,
      ["-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"],
      { encoding: "utf8" },
    );
    if (result.status === 0) {
      return bin;
    }
  }
  return null;
}

const python = pickPython();
if (!python) {
  console.error("baton needs Python 3.11+ on PATH (python3 or python).");
  console.error("Install Python, then retry: npm install -g @baton-cli/cli");
  process.exit(1);
}

const child = spawn(python, ["-m", "baton", ...process.argv.slice(2)], {
  stdio: "inherit",
  env,
  cwd: process.cwd(),
});
child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code == null ? 1 : code);
});
child.on("error", (err) => {
  console.error("failed to start Python:", err.message);
  process.exit(1);
});
