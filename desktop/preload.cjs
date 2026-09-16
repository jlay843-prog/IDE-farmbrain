"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("forge", {
  openFolder: (defaultPath) => ipcRenderer.invoke("forge:open-folder", defaultPath || ""),
});
