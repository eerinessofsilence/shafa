from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SHAFA_LOGIC_DIR = ROOT / "shafa_logic"

for path in (ROOT, SHAFA_LOGIC_DIR):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)
