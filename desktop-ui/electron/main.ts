import fs from "node:fs";
import path from "node:path";
import { spawn, type ChildProcessByStdio } from "node:child_process";
import type { Readable } from "node:stream";
import { app, BrowserWindow, dialog } from "electron";

const rendererUrl = process.env.ELECTRON_RENDERER_URL;
const BACKEND_START_TIMEOUT_MS = 30_000;
const API_BASE_URL_ARGUMENT = "--shafa-api-base-url";
const DEFAULT_BACKEND_PORT = 8000;
type BackendProcess = ChildProcessByStdio<null, Readable, Readable>;

let backendProcess: BackendProcess | null = null;
let quitting = false;

function repoRoot(): string {
  return path.resolve(__dirname, "..", "..");
}

function createDelay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function resolveBackendPort(): number {
  const configuredPort = process.env.SHAFA_BACKEND_PORT?.trim();
  if (!configuredPort) {
    return DEFAULT_BACKEND_PORT;
  }

  const port = Number.parseInt(configuredPort, 10);
  if (!Number.isFinite(port) || port <= 0 || port > 65_535) {
    throw new Error(`Invalid SHAFA_BACKEND_PORT value: ${configuredPort}`);
  }

  return port;
}

function streamBackendLogs(
  stream: Readable | null,
  label: "stdout" | "stderr",
): void {
  if (!stream) {
    return;
  }

  let buffered = "";
  stream.setEncoding("utf8");
  stream.on("data", (chunk: string) => {
    buffered += chunk;
    const lines = buffered.split(/\r?\n/);
    buffered = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed) {
        console.log(`[backend:${label}] ${trimmed}`);
      }
    }
  });
  stream.on("end", () => {
    const trimmed = buffered.trim();
    if (trimmed) {
      console.log(`[backend:${label}] ${trimmed}`);
    }
  });
}

function resolveDevBackendCommand(): { command: string; args: string[]; cwd: string } {
  const root = repoRoot();
  const scriptPath = path.join(root, "desktop_backend.py");
  const pythonCandidates = [
    process.env.SHAFA_BACKEND_PYTHON,
    path.join(root, "venv", process.platform === "win32" ? "Scripts" : "bin", process.platform === "win32" ? "python.exe" : "python"),
    path.join(root, ".venv", process.platform === "win32" ? "Scripts" : "bin", process.platform === "win32" ? "python.exe" : "python"),
  ].filter((candidate): candidate is string => Boolean(candidate));

  for (const candidate of pythonCandidates) {
    if (!path.isAbsolute(candidate) || fs.existsSync(candidate)) {
      return { command: candidate, args: [scriptPath], cwd: root };
    }
  }

  if (process.platform === "win32") {
    return { command: "py", args: ["-3", scriptPath], cwd: root };
  }

  return { command: "python3", args: [scriptPath], cwd: root };
}

function resolvePackagedBackendCommand(): { command: string; args: string[]; cwd: string } {
  const filename = process.platform === "win32" ? "ShafaControlBackend.exe" : "ShafaControlBackend";
  const command = path.join(process.resourcesPath, "backend", filename);
  return {
    command,
    args: [],
    cwd: path.dirname(command),
  };
}

async function waitForBackendReady(
  apiBaseUrl: string,
  child: BackendProcess,
): Promise<void> {
  const deadline = Date.now() + BACKEND_START_TIMEOUT_MS;

  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`Backend exited before startup completed (code ${child.exitCode}).`);
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2_000);

    try {
      const response = await fetch(`${apiBaseUrl}/health`, {
        signal: controller.signal,
      });
      if (response.ok) {
        return;
      }
    } catch {
      // Backend is still starting up.
    } finally {
      clearTimeout(timeoutId);
    }

    await createDelay(250);
  }

  throw new Error(`Backend did not become healthy within ${BACKEND_START_TIMEOUT_MS / 1000} seconds.`);
}

async function startBackend(): Promise<string> {
  const port = resolveBackendPort();
  const apiBaseUrl = `http://127.0.0.1:${port}`;
  const userDataDir = path.join(app.getPath("userData"), "backend-data");
  const launch = app.isPackaged ? resolvePackagedBackendCommand() : resolveDevBackendCommand();
  const child = spawn(launch.command, launch.args, {
    cwd: launch.cwd,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: "1",
      SHAFA_BACKEND_HOST: "127.0.0.1",
      SHAFA_BACKEND_PORT: String(port),
      SHAFA_DESKTOP_DATA_DIR: userDataDir,
    },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });

  streamBackendLogs(child.stdout, "stdout");
  streamBackendLogs(child.stderr, "stderr");

  child.on("exit", (code, signal) => {
    backendProcess = null;
    if (!quitting) {
      const exitLabel = signal ? `signal ${signal}` : `code ${code ?? "unknown"}`;
      dialog.showErrorBox(
        "Shafa Control",
        `Local backend stopped unexpectedly (${exitLabel}).`,
      );
    }
  });

  await new Promise<void>((resolve, reject) => {
    const handleError = (error: Error) => {
      child.off("spawn", handleSpawn);
      reject(error);
    };
    const handleSpawn = () => {
      child.off("error", handleError);
      resolve();
    };

    child.once("error", handleError);
    child.once("spawn", handleSpawn);
  });

  await waitForBackendReady(apiBaseUrl, child);
  backendProcess = child;
  process.env.SHAFA_API_BASE_URL = apiBaseUrl;
  return apiBaseUrl;
}

function stopBackend(): void {
  if (!backendProcess || backendProcess.killed) {
    return;
  }
  backendProcess.kill();
  backendProcess = null;
}

function createWindow(apiBaseUrl: string): void {
  const window = new BrowserWindow({
    width: 1500,
    height: 960,
    minWidth: 1220,
    minHeight: 820,
    backgroundColor: "#091018",
    autoHideMenuBar: true,
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      additionalArguments: [
        `${API_BASE_URL_ARGUMENT}=${encodeURIComponent(apiBaseUrl)}`,
      ],
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (rendererUrl) {
    void window.loadURL(rendererUrl);
    return;
  }

  void window.loadFile(path.join(__dirname, "..", "dist", "index.html"));
}

app.whenReady().then(async () => {
  let apiBaseUrl: string;

  try {
    apiBaseUrl = await startBackend();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    dialog.showErrorBox("Shafa Control", `Failed to start local backend.\n\n${message}`);
    app.quit();
    return;
  }

  createWindow(apiBaseUrl);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow(apiBaseUrl);
    }
  });
});

app.on("before-quit", () => {
  quitting = true;
  stopBackend();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
