#!/usr/bin/env python3
"""Minimal Qt test to diagnose segfault"""
import sys
print("[1] Python started")

try:
    from PySide6.QtWidgets import QApplication
    print("[2] QApplication imported")
    
    app = QApplication(sys.argv)
    print("[3] QApplication created")
    
    from PySide6.QtWidgets import QMainWindow, QLabel
    print("[4] QMainWindow imported")
    
    window = QMainWindow()
    print("[5] QMainWindow created")
    
    window.setWindowTitle("Test")
    print("[6] Window title set")
    
    window.show()
    print("[7] Window shown")
    
    print("[OK] Qt initialization successful")
    sys.exit(0)
    
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
