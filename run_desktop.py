from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _resolve_npm_command() -> str:
    candidates = ["npm.cmd", "npm.exe", "npm"] if os.name == "nt" else ["npm"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    if os.name == "nt":
        windows_candidates = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / "npm.cmd",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "nodejs" / "npm.cmd",
            Path.home() / "AppData" / "Roaming" / "npm" / "npm.cmd",
        ]
        for candidate in windows_candidates:
            if candidate.exists():
                return str(candidate)

    raise FileNotFoundError("npm")


def main() -> None:
    root = Path(__file__).resolve().parent
    desktop_ui = root / "desktop-ui"
    command = [_resolve_npm_command(), "run", "dev"]

    print(f"Starting desktop app in dev mode from {desktop_ui}", flush=True)
    subprocess.run(
        command,
        cwd=desktop_ui,
        env={**os.environ},
        check=True,
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
    except FileNotFoundError:
        print("npm was not found in PATH. Install Node.js or reopen the terminal after installation.", file=sys.stderr)
        raise SystemExit(1)
