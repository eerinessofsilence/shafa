from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    desktop_ui = root / "desktop-ui"
    command = ["npm", "run", "dev"]

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
        print("npm was not found. Install Node.js and npm, then try again.", file=sys.stderr)
        raise SystemExit(1)
