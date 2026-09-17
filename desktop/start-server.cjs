"use strict";

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

function forgeRoot() {
  if (process.env.FORGE_ROOT) return process.env.FORGE_ROOT;
  const unpacked = path.join(__dirname, "..");
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

const python = process.env.FORGE_PYTHON || process.env.PYTHON || "";
const candidates = python
  ? [[python]]
  : process.platform === "win32"
    ? [["py", "-3"], ["python"], ["python3"]]
    : [["python3"], ["python"]];

function run(cmd) {
  const [bin, ...prefix] = cmd;
  const child = spawn(bin, [...prefix, "-m", "forge", "serve", "--host", bind, "--port", port], {
    cwd: root,
    env: {
      ...process.env,
      PYTHONPATH: src + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ""),
    },
    stdio: "inherit",
  });
  child.on("error", (err) => {
    if (err.code === "ENOENT") return tryNext();
    console.error(err);
    process.exit(1);
  });
  child.on("exit", (code, signal) => {
    if (signal) process.kill(process.pid, signal);
    process.exit(code ?? 1);
  });
}

let i = 0;
function tryNext() {
  if (i >= candidates.length) {
    console.error("Forge needs Python 3.11+ (py -3 or python on PATH).");
    process.exit(1);
  }
  run(candidates[i++]);
}

tryNext();
