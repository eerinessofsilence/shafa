from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace


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


def test_no_playwright_request_helpers_import_without_playwright(monkeypatch) -> None:
    shafa_logic_dir = Path(__file__).resolve().parents[1] / "shafa_logic"
    path_entry = str(shafa_logic_dir)
    if path_entry not in sys.path:
        sys.path.insert(0, path_entry)

    for module_name in (
        "core.requests.create_product",
        "core.requests.upload_photo",
    ):
        sys.modules.pop(module_name, None)

    real_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "playwright.sync_api":
            raise ModuleNotFoundError("No module named 'playwright'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)

    create_product_module = importlib.import_module("core.requests.create_product")
    upload_photo_module = importlib.import_module("core.requests.upload_photo")

    assert create_product_module.BrowserContext is object
    assert upload_photo_module.BrowserContext is object


def test_launch_visible_browser_prefers_msedge_on_windows(monkeypatch) -> None:
    module = _reload_shafa_main()
    calls: list[tuple[str | None, bool]] = []

    class _Chromium:
        def launch(self, *, headless: bool, channel: str | None = None):
            calls.append((channel, headless))
            return f"browser:{channel or 'chromium'}"

    monkeypatch.setattr(module.os, "name", "nt")
    browser, browser_name = module._launch_visible_browser(
        SimpleNamespace(chromium=_Chromium()),
        headless=False,
    )

    assert browser == "browser:msedge"
    assert browser_name == "msedge"
    assert calls == [("msedge", False)]


def test_launch_visible_browser_falls_back_to_plain_chromium(monkeypatch) -> None:
    module = _reload_shafa_main()
    calls: list[tuple[str | None, bool]] = []

    class _Chromium:
        def launch(self, *, headless: bool, channel: str | None = None):
            calls.append((channel, headless))
            if channel is not None:
                raise RuntimeError(f"missing channel {channel}")
            return "browser:chromium"

    monkeypatch.setattr(module.os, "name", "nt")
    browser, browser_name = module._launch_visible_browser(
        SimpleNamespace(chromium=_Chromium()),
        headless=False,
    )

    assert browser == "browser:chromium"
    assert browser_name == "chromium"
    assert calls == [("msedge", False), ("chrome", False), (None, False)]
