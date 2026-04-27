import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { spawn, type ChildProcessByStdio } from "node:child_process";
import type { Readable } from "node:stream";
import { app, BrowserWindow, dialog } from "electron";

const rendererUrl = process.env.ELECTRON_RENDERER_URL;
const BACKEND_START_TIMEOUT_MS = 30_000;
const BACKEND_START_MAX_ATTEMPTS = 3;
const BACKEND_START_RETRY_DELAY_MS = 1_500;
const API_BASE_URL_ARGUMENT = "--shafa-api-base-url";
const DEFAULT_BACKEND_PORT = 8000;
type BackendProcess = ChildProcessByStdio<null, Readable, Readable>;

interface BackendBuildInfo {
  executableName: string;
  hostPlatform: string;
  pythonVersion: string;
  targetPlatform: string;
}

let backendProcess: BackendProcess | null = null;
let backendLogPath: string | null = null;
let quitting = false;

interface RetryableBackendStartupError extends Error {
  retryable?: boolean;
}

function repoRoot(): string {
  return path.resolve(__dirname, "..", "..");
}

function createDelay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function resolveBackendLogPath(): string {
  if (!backendLogPath) {
    const logDir = path.join(app.getPath("userData"), "logs");
    fs.mkdirSync(logDir, { recursive: true });
    backendLogPath = path.join(logDir, "backend-launch.log");
  }
  return backendLogPath;
}

function appendBackendLog(message: string): void {
  const line = `[${new Date().toISOString()}] ${message}\n`;

  try {
    fs.appendFileSync(resolveBackendLogPath(), line, "utf8");
  } catch (error) {
    console.warn("Failed to write backend log.", error);
  }
}

function createBackendStartupError(
  message: string,
  retryable: boolean,
): RetryableBackendStartupError {
  const error = new Error(message) as RetryableBackendStartupError;
  error.retryable = retryable;
  return error;
}

function isRetryableBackendStartupError(error: unknown): boolean {
  return Boolean(
    error &&
      typeof error === "object" &&
      "retryable" in error &&
      (error as RetryableBackendStartupError).retryable,
  );
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

async function fetchBackendHealth(
  apiBaseUrl: string,
): Promise<"healthy" | "unreachable" | "unexpected-response"> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 2_000);

  try {
    const response = await fetch(`${apiBaseUrl}/health`, {
      signal: controller.signal,
    });
    if (response.ok) {
      return "healthy";
    }
    return "unexpected-response";
  } catch {
    return "unreachable";
  } finally {
    clearTimeout(timeoutId);
  }
}

function isLocalPortInUse(host: string, port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port });

    const finish = (result: boolean) => {
      socket.removeAllListeners();
      socket.destroy();
      resolve(result);
    };

    socket.setTimeout(1_500);
    socket.once("connect", () => finish(true));
    socket.once("timeout", () => finish(true));
    socket.once("error", (error: NodeJS.ErrnoException) => {
      if (error.code === "ECONNREFUSED") {
        finish(false);
        return;
      }
      finish(true);
    });
  });
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
        appendBackendLog(`[${label}] ${trimmed}`);
      }
    }
  });
  stream.on("end", () => {
    const trimmed = buffered.trim();
    if (trimmed) {
      console.log(`[backend:${label}] ${trimmed}`);
      appendBackendLog(`[${label}] ${trimmed}`);
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

function readPackagedBackendBuildInfo(): BackendBuildInfo | null {
  const infoPath = path.join(process.resourcesPath, "backend", "backend-build-info.json");
  if (!fs.existsSync(infoPath)) {
    return null;
  }

  try {
    return JSON.parse(fs.readFileSync(infoPath, "utf8")) as BackendBuildInfo;
  } catch (error) {
    appendBackendLog(`Failed to read backend build info: ${String(error)}`);
    return null;
  }
}

function resolvePackagedBackendCommand(): { command: string; args: string[]; cwd: string } {
  const backendDir = path.join(process.resourcesPath, "backend");
  const buildInfo = readPackagedBackendBuildInfo();

  if (buildInfo) {
    if (buildInfo.targetPlatform !== process.platform) {
      throw new Error(
        `Bundled backend targets ${buildInfo.targetPlatform}, but this desktop app is running on ${process.platform}. ` +
          "Rebuild the Windows desktop app on Windows so it can include a Windows backend binary.",
      );
    }

    const command = path.join(backendDir, buildInfo.executableName);
    if (!fs.existsSync(command)) {
      throw new Error(
        `Bundled backend executable was not found: ${command}. Rebuild the desktop package.`,
      );
    }

    return {
      command,
      args: [],
      cwd: path.dirname(command),
    };
  }

  const expectedFilename =
    process.platform === "win32" ? "ShafaControlBackend.exe" : "ShafaControlBackend";
  const command = path.join(backendDir, expectedFilename);
  if (!fs.existsSync(command)) {
    throw new Error(
      `Bundled backend executable was not found: ${command}. Rebuild the desktop package.`,
    );
  }

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
      throw createBackendStartupError(
        `Backend exited before startup completed (code ${child.exitCode}).`,
        true,
      );
    }

    const health = await fetchBackendHealth(apiBaseUrl);
    if (health === "healthy") {
      return;
    }

    await createDelay(250);
  }

  throw createBackendStartupError(
    `Backend did not become healthy within ${BACKEND_START_TIMEOUT_MS / 1000} seconds.`,
    true,
  );
}

async function launchBackendProcess(
  command: string,
  args: string[],
  {
    apiBaseUrl,
    cwd,
    host,
    port,
    userDataDir,
  }: {
    apiBaseUrl: string;
    cwd: string;
    host: string;
    port: number;
    userDataDir: string;
  },
): Promise<BackendProcess> {
  appendBackendLog(
    `Launching backend from ${command} on ${apiBaseUrl} with data dir ${userDataDir}`,
  );
  const child = spawn(command, args, {
    cwd,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: "1",
      SHAFA_BACKEND_HOST: host,
      SHAFA_BACKEND_PORT: String(port),
      SHAFA_DESKTOP_DATA_DIR: userDataDir,
    },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });

  streamBackendLogs(child.stdout, "stdout");
  streamBackendLogs(child.stderr, "stderr");

  let reportUnexpectedExit = false;

  child.on("exit", (code, signal) => {
    if (backendProcess === child) {
      backendProcess = null;
    }
    const exitLabel = signal ? `signal ${signal}` : `code ${code ?? "unknown"}`;
    appendBackendLog(`Backend process exited (${exitLabel}).`);
    if (!quitting && reportUnexpectedExit) {
      dialog.showErrorBox(
        "Shafa Control",
        `Local backend stopped unexpectedly (${exitLabel}).\n\nLog: ${resolveBackendLogPath()}`,
      );
    }
  });

  await new Promise<void>((resolve, reject) => {
    const handleError = (error: Error) => {
      child.off("spawn", handleSpawn);
      reject(createBackendStartupError(String(error), true));
    };
    const handleSpawn = () => {
      child.off("error", handleError);
      resolve();
    };

    child.once("error", handleError);
    child.once("spawn", handleSpawn);
  });

  try {
    await waitForBackendReady(apiBaseUrl, child);
  } catch (error) {
    if (child.exitCode === null && !child.killed) {
      child.kill();
    }
    throw error;
  }

  reportUnexpectedExit = true;
  return child;
}

async function startBackend(): Promise<string> {
  const host = "127.0.0.1";
  const port = resolveBackendPort();
  const apiBaseUrl = `http://${host}:${port}`;
  const userDataDir = path.join(app.getPath("userData"), "backend-data");
  const launch = app.isPackaged ? resolvePackagedBackendCommand() : resolveDevBackendCommand();

  for (let attempt = 1; attempt <= BACKEND_START_MAX_ATTEMPTS; attempt += 1) {
    const existingHealth = await fetchBackendHealth(apiBaseUrl);

    if (existingHealth === "healthy") {
      appendBackendLog(`Reusing already running backend at ${apiBaseUrl}.`);
      process.env.SHAFA_API_BASE_URL = apiBaseUrl;
      return apiBaseUrl;
    }

    if (await isLocalPortInUse(host, port)) {
      throw new Error(
        `Port ${port} on ${host} is already in use, but no Shafa backend answered on ${apiBaseUrl}/health. ` +
          "Stop the conflicting process or set SHAFA_BACKEND_PORT to another port.",
      );
    }

    appendBackendLog(
      `Starting backend attempt ${attempt}/${BACKEND_START_MAX_ATTEMPTS}.`,
    );

    try {
      const child = await launchBackendProcess(launch.command, launch.args, {
        apiBaseUrl,
        cwd: launch.cwd,
        host,
        port,
        userDataDir,
      });
      backendProcess = child;
      process.env.SHAFA_API_BASE_URL = apiBaseUrl;
      appendBackendLog(
        `Backend became healthy on attempt ${attempt}/${BACKEND_START_MAX_ATTEMPTS}.`,
      );
      return apiBaseUrl;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      appendBackendLog(
        `Backend start attempt ${attempt}/${BACKEND_START_MAX_ATTEMPTS} failed: ${message}`,
      );
      if (
        !isRetryableBackendStartupError(error) ||
        attempt === BACKEND_START_MAX_ATTEMPTS
      ) {
        throw error;
      }
      await createDelay(BACKEND_START_RETRY_DELAY_MS);
    }
  }

  throw new Error("Backend start attempts were exhausted.");
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
    appendBackendLog(`Failed to start local backend: ${message}`);
    dialog.showErrorBox(
      "Shafa Control",
      `Failed to start local backend.\n\n${message}\n\nLog: ${resolveBackendLogPath()}`,
    );
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
