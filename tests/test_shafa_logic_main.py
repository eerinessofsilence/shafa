from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType


def _reload_shafa_main() -> ModuleType:
    sys.modules.pop("shafa_logic.main", None)
    shafa_logic_dir = Path(__file__).resolve().parents[1] / "shafa_logic"
    path_entry = str(shafa_logic_dir)
    if path_entry not in sys.path:
        sys.path.insert(0, path_entry)
    return importlib.import_module("shafa_logic.main")


def test_noninteractive_shafa_mode_does_not_require_inquirer(monkeypatch) -> None:
    module = _reload_shafa_main()
    calls: list[object] = []

    monkeypatch.setitem(sys.modules, "inquirer", None)
    monkeypatch.setattr(module, "sync_channels_from_runtime_config", lambda: calls.append("sync"))
    monkeypatch.setattr(module, "_auto_create_product", lambda **kwargs: calls.append(kwargs))

    module.main(shafa=True)

    assert calls == ["sync", {"shafa": True}]


def test_prompt_list_reports_missing_inquirer(monkeypatch) -> None:
    module = _reload_shafa_main()

    monkeypatch.setattr(module.sys.stdin, "isatty", lambda: True)
    monkeypatch.delitem(sys.modules, "inquirer", raising=False)

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "inquirer":
            raise ModuleNotFoundError("No module named 'inquirer'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    try:
        module._prompt_list("Choose", [("One", 1)])
    except RuntimeError as exc:
        assert "интерактивного CLI-меню" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when inquirer is unavailable")
