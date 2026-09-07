#!/usr/bin/env node
"use strict";

const { spawnSync } = require("child_process");

const candidates = [
  process.env.BATON_PYTHON,
  "python3",
  "python",
  "/opt/homebrew/bin/python3",
  "/usr/local/bin/python3",
  "/usr/bin/python3",
].filter(Boolean);

for (const bin of candidates) {
  const result = spawnSync(
    bin,
    ["-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"],
    { encoding: "utf8" },
  );
  if (result.status === 0) {
    process.exit(0);
  }
}

console.error("baton needs Python 3.11+ on PATH (python3 or python).");
console.error("The npm package is a launcher; the CLI itself is Python.");
process.exit(1);
