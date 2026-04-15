import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("desktopShell", {
  platform: process.platform,
  electronVersion: process.versions.electron,
  chromeVersion: process.versions.chrome,
});
