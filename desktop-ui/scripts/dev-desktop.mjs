import path from "node:path";
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

import waitOn from "wait-on";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "..");
const require = createRequire(import.meta.url);
const electronBinary = require("electron");
const rendererUrl = "http://127.0.0.1:5173";

await waitOn({
  resources: ["tcp:5173", path.join(appRoot, "dist-electron", "main.js")],
});

const child = spawn(electronBinary, ["."], {
  cwd: appRoot,
  env: {
    ...process.env,
    ELECTRON_RENDERER_URL: rendererUrl,
  },
  stdio: "inherit",
});

const forwardSignal = (signal) => {
  if (child.exitCode === null && !child.killed) {
    child.kill(signal);
  }
};

process.on("SIGINT", () => forwardSignal("SIGINT"));
process.on("SIGTERM", () => forwardSignal("SIGTERM"));

child.on("error", (error) => {
  console.error(String(error));
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
