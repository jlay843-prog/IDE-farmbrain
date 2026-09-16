"use strict";

const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { spawn } = require("node:child_process");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");

const root = path.join(__dirname, "..");
const port = Number(process.env.FORGE_PORT || 43180);
const bind = process.env.FORGE_BIND || "127.0.0.1";
const url = `http://${bind}:${port}/`;

const localAppData =
  process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
app.setName("Forge");
app.setPath("userData", process.env.FORGE_ELECTRON_DATA || path.join(localAppData, "Forge", "electron"));

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
      FORGE_BIND: bind,
      FORGE_PORT: String(port),
      FORGE_DATA: process.env.FORGE_DATA || path.join(localAppData, "Forge"),
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
    icon: path.join(root, "ui", "forge-icon.svg"),
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
