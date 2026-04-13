#!/usr/bin/env python3
"""Manual Qt smoke test.

This file is intentionally not a pytest test module. Run it directly when you
need to verify that Qt can initialize in the current environment.
"""

import sys


def main() -> int:
    print("[1] Python started")
    try:
        from PySide6.QtWidgets import QApplication, QMainWindow

        print("[2] QApplication imported")
        app = QApplication(sys.argv)
        print("[3] QApplication created")

        window = QMainWindow()
        print("[4] QMainWindow created")
        window.setWindowTitle("Test")
        window.show()

        print("[OK] Qt initialization successful")
        return app.exec()
    except Exception as exc:
        print(f"[ERROR] {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
