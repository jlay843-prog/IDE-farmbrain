"use strict";

const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
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
const port = Number(process.env.FORGE_PORT || 43180);
const bind = process.env.FORGE_BIND || "127.0.0.1";
const url = `http://${bind}:${port}/`;

const localAppData =
  process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
const forgeData = process.env.FORGE_DATA || path.join(localAppData, "Forge");
app.setName("Forge");
app.setPath("userData", process.env.FORGE_ELECTRON_DATA || path.join(localAppData, "Forge", "electron"));

function appIcon() {
  const candidates = [
    path.join(__dirname, "..", "ui", "forge.ico"),
    path.join(root, "ui", "forge.ico"),
    path.join(root, "ui", "forge-icon.svg"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return undefined;
}

function readWorkspaceFromState() {
  try {
    const raw = fs.readFileSync(path.join(forgeData, "state.json"), "utf8");
    const state = JSON.parse(raw);
    return String(state.workspace || "").trim();
  } catch {
    return "";
  }
}

function postWorkspace(folderPath) {
  const data = JSON.stringify({ path: folderPath });
  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        hostname: bind,
        port,
        path: "/api/open",
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(data),
        },
      },
      (res) => {
        res.resume();
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve();
          return;
        }
        reject(new Error(`workspace set failed (${res.statusCode})`));
      }
    );
    req.on("error", reject);
    req.write(data);
    req.end();
  });
}

async function ensureFirstRunWorkspace() {
  const current = readWorkspaceFromState();
  if (current && fs.existsSync(current)) return;
  const result = await dialog.showOpenDialog({
    title: "Choose your Forge workspace",
    message: "Pick the project folder Forge should open first. You can change this later from Project.",
    defaultPath: current || process.env.USERPROFILE || os.homedir(),
    properties: ["openDirectory", "createDirectory"],
  });
  if (result.canceled || !result.filePaths.length) return;
  await postWorkspace(result.filePaths[0]);
}

let server = null;
let win = null;

function waitForHealth(timeoutMs = 60000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const ping = () => {
      const req = http.get(`http://${bind}:${port}/api/health`, (res) => {
        res.resume();
        if (res.statusCode === 200) {
          resolve();
          return;
        }
        retry();
      });
      req.on("error", retry);
      req.setTimeout(1500, () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        reject(new Error("Forge did not start in time."));
        return;
      }
      setTimeout(ping, 400);
    };
    ping();
  });
}

function startServer() {
  if (process.env.FORGE_EXTERNAL_URL) return null;
  const child = spawn(process.execPath, [path.join(__dirname, "start-server.cjs")], {
    cwd: root,
    env: {
      ...process.env,
      ELECTRON_RUN_AS_NODE: "1",
      FORGE_ROOT: root,
      FORGE_BIND: bind,
      FORGE_PORT: String(port),
      FORGE_DATA: forgeData,
      PYTHONPATH: path.join(root, "src") + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ""),
    },
    stdio: "inherit",
    windowsHide: true,
  });
  child.on("exit", (code) => {
    if (!app.isQuitting && code && code !== 0) {
      console.error(`Forge server exited ${code}`);
    }
  });
  return child;
}

function createWindow() {
  win = new BrowserWindow({
    width: 1560,
    height: 960,
    minWidth: 980,
    minHeight: 680,
    title: "Forge",
    autoHideMenuBar: true,
    backgroundColor: "#120e0a",
    icon: appIcon(),
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.removeMenu();
  win.webContents.setWindowOpenHandler(({ url: target }) => {
    if (target.startsWith("http://127.0.0.1") || target.startsWith("http://localhost")) {
      return { action: "allow" };
    }
    void shell.openExternal(target);
    return { action: "deny" };
  });
  return win.loadURL(process.env.FORGE_EXTERNAL_URL || url);
}

function stopServer() {
  if (server && !server.killed) {
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(server.pid), "/t", "/f"], { windowsHide: true });
    } else {
      server.kill();
    }
  }
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  ipcMain.handle("forge:open-folder", async (event, defaultPath) => {
    const bw = BrowserWindow.fromWebContents(event.sender) || win;
    const result = await dialog.showOpenDialog(bw || undefined, {
      title: "Open workspace",
      defaultPath: defaultPath || undefined,
      properties: ["openDirectory"],
    });
    if (result.canceled || !result.filePaths.length) return null;
    return result.filePaths[0];
  });

  app.on("second-instance", () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });

  app.whenReady().then(async () => {
    app.isQuitting = false;
    try {
      await waitForHealth(1200);
    } catch {
      server = startServer();
      await waitForHealth();
    }
    await ensureFirstRunWorkspace();
    await createWindow();
  }).catch((err) => {
    console.error(err);
    stopServer();
    app.exit(1);
  });

  app.on("window-all-closed", () => {
    app.isQuitting = true;
    stopServer();
    app.quit();
  });

  app.on("before-quit", () => {
    app.isQuitting = true;
    stopServer();
  });
}
