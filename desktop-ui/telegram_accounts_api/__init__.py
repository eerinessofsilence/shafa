from pathlib import Path
import sys


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REAL_PACKAGE_DIR = _PROJECT_ROOT / "telegram_accounts_api"
_project_root_str = str(_PROJECT_ROOT)

if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

# Allow imports like `telegram_accounts_api.main` when Python is started from
# `desktop-ui/`, for example via `uvicorn --reload` during frontend-driven dev.
__path__ = [str(_REAL_PACKAGE_DIR)]
