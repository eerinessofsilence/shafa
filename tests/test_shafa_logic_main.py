from __future__ import annotations

import importlib
import sys
import types
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


def test_auto_create_product_shafa_mode_does_not_import_with_playwright(monkeypatch) -> None:
    module = _reload_shafa_main()
    calls: list[object] = []
    real_import = __import__

    def fake_no_playwright_main() -> None:
        calls.append("no_playwright_main")

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "core.with_playwright":
            raise AssertionError("with_playwright should not be imported in shafa mode")
        if name == "core.no_playwright":
            return types.SimpleNamespace(main=fake_no_playwright_main)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)
    monkeypatch.setattr(
        module,
        "run_periodic",
        lambda action, label, shafa=None: calls.append((action, label, shafa)),
    )

    module._auto_create_product(shafa=True)

    assert calls == [(fake_no_playwright_main, "Без Playwright", True)]


def test_auto_create_product_cli_no_gui_uses_no_playwright(monkeypatch) -> None:
    module = _reload_shafa_main()
    calls: list[object] = []
    real_import = __import__

    def fake_no_playwright_main() -> None:
        calls.append("no_playwright_main")

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "core.with_playwright":
            raise AssertionError("with_playwright should not be imported when GUI is disabled")
        if name == "core.no_playwright":
            return types.SimpleNamespace(main=fake_no_playwright_main)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)
    monkeypatch.setattr(module, "_choose_yes_no", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        module,
        "run_periodic",
        lambda action, label, shafa=None: calls.append((action, label, shafa)),
    )

    module._auto_create_product(shafa=False)

    assert calls == [(fake_no_playwright_main, "Без Playwright", None)]
