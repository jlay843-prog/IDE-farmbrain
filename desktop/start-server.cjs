"use strict";

const { spawn } = require("node:child_process");
const path = require("node:path");
const { findPython } = require("./find-python.cjs");

function forgeRoot() {
  if (process.env.FORGE_ROOT) return process.env.FORGE_ROOT;
  const unpacked = path.join(__dirname, "..");
  const fs = require("node:fs");
  if (fs.existsSync(path.join(unpacked, "src", "forge"))) return unpacked;
  if (process.resourcesPath && fs.existsSync(path.join(process.resourcesPath, "src", "forge"))) {
    return process.resourcesPath;
  }
  return unpacked;
}

const root = forgeRoot();
const bind = process.env.FORGE_BIND || "127.0.0.1";
const port = String(process.env.FORGE_PORT || "43180");
const src = path.join(root, "src");
const found = findPython(root);

if (!found.ok) {
  console.error(found.error || "Forge needs Python 3.11+.");
  process.exit(1);
}

const child = spawn(found.exe, [...found.args, "-m", "forge", "serve", "--host", bind, "--port", port], {
  cwd: root,
  env: {
    ...process.env,
    PYTHONPATH: src + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ""),
  },
  stdio: "inherit",
  windowsHide: true,
});
child.on("error", (err) => {
  console.error(err);
  process.exit(1);
});
child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
});
