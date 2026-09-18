"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

function exists(file) {
  try {
    return Boolean(file && fs.existsSync(file) && fs.statSync(file).isFile());
  } catch {
    return false;
  }
}

function versionOk(exe, extra = []) {
  const result = spawnSync(exe, [...extra, "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"], {
    encoding: "utf8",
    windowsHide: true,
    timeout: 8000,
  });
  return result.status === 0;
}

function pythonDirs(root) {
  const local = process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
  const pf = process.env.ProgramFiles || "C:\\Program Files";
  const pf86 = process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)";
  const bundled = [
    process.env.FORGE_PYTHON,
    root ? path.join(root, "python", "python.exe") : "",
    process.resourcesPath ? path.join(process.resourcesPath, "python", "python.exe") : "",
  ].filter(Boolean);
  const launchers = [
    "C:\\Windows\\py.exe",
    path.join(local, "Programs", "Python", "Launcher", "py.exe"),
  ];
  const installs = [];
  for (const base of [path.join(local, "Programs", "Python"), pf, pf86]) {
    if (!fs.existsSync(base)) continue;
    let names = [];
    try {
      names = fs.readdirSync(base);
    } catch {
      names = [];
    }
    for (const name of names.sort().reverse()) {
      if (/^Python3\d+/i.test(name)) {
        installs.push(path.join(base, name, "python.exe"));
      }
    }
  }
  return { bundled, launchers, installs };
}

function findPython(root) {
  const { bundled, launchers, installs } = pythonDirs(root);
  const ordered = [];
  for (const exe of bundled) ordered.push({ exe, args: [], source: "bundled" });
  for (const exe of launchers) ordered.push({ exe, args: ["-3"], source: "py-launcher" });
  for (const exe of installs) ordered.push({ exe, args: [], source: "known-path" });
  for (const name of process.platform === "win32" ? ["py", "python", "python3"] : ["python3", "python"]) {
    ordered.push({ exe: name, args: name === "py" ? ["-3"] : [], source: "path", pathLookup: true });
  }
  const seen = new Set();
  for (const row of ordered) {
    const key = `${row.exe} ${row.args.join(" ")}`;
    if (seen.has(key)) continue;
    seen.add(key);
    if (!row.pathLookup && !exists(row.exe)) continue;
    if (versionOk(row.exe, row.args)) {
      return { ok: true, exe: row.exe, args: row.args, source: row.source };
    }
  }
  return {
    ok: false,
    exe: "",
    args: [],
    source: "",
    error: "Python 3.11+ not found. Set FORGE_PYTHON or drop python.exe under python/ next to Forge.",
  };
}

module.exports = { findPython };

if (require.main === module) {
  const found = findPython(process.env.FORGE_ROOT || path.join(__dirname, ".."));
  if (!found.ok) {
    console.error(found.error);
    process.exit(1);
  }
  console.log(JSON.stringify(found));
}
