from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SHAFA_DIR = ROOT / "shafa"

for path in (ROOT, SHAFA_DIR):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)
