from pathlib import Path
import sys


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REAL_PACKAGE_DIR = _PROJECT_ROOT / "telegram_accounts_api"
_project_root_str = str(_PROJECT_ROOT)

if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

# Let Python resolve telegram_accounts_api submodules from the real package
# that lives one level above shafa_logic.
__path__ = [str(_REAL_PACKAGE_DIR)]
