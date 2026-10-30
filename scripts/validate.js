#!/usr/bin/env node
// Shim so `node scripts/validate.js` works from repo root (gate G2).
const { spawnSync } = require("child_process");
const result = spawnSync("node", ["frontend/scripts/validate.js"], { stdio: "inherit" });
process.exit(result.status ?? 1);
