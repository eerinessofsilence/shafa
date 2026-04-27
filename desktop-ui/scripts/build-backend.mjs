import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..", "..");
const buildScript = path.join(repoRoot, "build_backend.py");
const pythonName = process.platform === "win32" ? "python.exe" : "python";

function resolveCandidates() {
  const candidates = [];
  const envPython = process.env.SHAFA_BACKEND_PYTHON?.trim();

  if (envPython) {
    candidates.push({
      command: envPython,
      args: [buildScript],
      requiresExistingPath: path.isAbsolute(envPython),
    });
  }

  candidates.push(
    {
      command: path.join(repoRoot, "venv", process.platform === "win32" ? "Scripts" : "bin", pythonName),
      args: [buildScript],
      requiresExistingPath: true,
    },
    {
      command: path.join(repoRoot, ".venv", process.platform === "win32" ? "Scripts" : "bin", pythonName),
      args: [buildScript],
      requiresExistingPath: true,
    },
  );

  if (process.platform === "win32") {
    candidates.push(
      { command: "py", args: ["-3", buildScript], requiresExistingPath: false },
      { command: "python", args: [buildScript], requiresExistingPath: false },
    );
  } else {
    candidates.push(
      { command: "python3", args: [buildScript], requiresExistingPath: false },
      { command: "python", args: [buildScript], requiresExistingPath: false },
    );
  }

  return candidates;
}

function runCandidate(candidate) {
  return new Promise((resolve, reject) => {
    const child = spawn(candidate.command, candidate.args, {
      cwd: repoRoot,
      env: {
        ...process.env,
        SHAFA_BACKEND_TARGET: process.env.SHAFA_BACKEND_TARGET ?? "win32",
      },
      stdio: "inherit",
    });

    child.on("error", (error) => {
      reject(error);
    });
    child.on("exit", (code) => {
      resolve(code ?? 1);
    });
  });
}

for (const candidate of resolveCandidates()) {
  if (candidate.requiresExistingPath && !fs.existsSync(candidate.command)) {
    continue;
  }

  try {
    console.log(`Building backend with ${candidate.command}`);
    const exitCode = await runCandidate(candidate);
    process.exit(exitCode);
  } catch (error) {
    if (error && typeof error === "object" && "code" in error && error.code === "ENOENT") {
      continue;
    }
    throw error;
  }
}

throw new Error(
  "Unable to find a Python interpreter for backend build. Set SHAFA_BACKEND_PYTHON or create venv/.venv.",
);
