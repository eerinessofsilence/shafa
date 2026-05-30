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

    class _StopEvent:
        def set(self) -> None:
            calls.append("stop")

    class _Thread:
        def join(self, timeout=None) -> None:
            calls.append(("join", timeout))

    monkeypatch.setitem(sys.modules, "inquirer", None)
    monkeypatch.setattr(module, "sync_channels_from_runtime_config", lambda: calls.append("sync"))
    monkeypatch.setattr(module, "_auto_create_product", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(
        module,
        "_start_background_telegram_scanner",
        lambda: (_StopEvent(), _Thread()),
    )
    monkeypatch.setattr(
        module,
        "_start_background_old_product_deactivator",
        lambda: (_StopEvent(), _Thread()),
    )

    module.main(shafa=True)

    assert calls == [
        "sync",
        {"shafa": True},
        "stop",
        ("join", 5),
        "stop",
        ("join", 5),
    ]


def test_shared_worker_skips_old_direct_deactivator(monkeypatch) -> None:
    module = _reload_shafa_main()
    calls: list[object] = []

    class _StopEvent:
        def set(self) -> None:
            calls.append("stop")

    class _Thread:
        def join(self, timeout=None) -> None:
            calls.append(("join", timeout))

    monkeypatch.setenv("SHAFA_SHARED_DEACTIVATION_ENABLED", "1")
    monkeypatch.setenv("SHAFA_SHARED_DEACTIVATION_WORKER_ENABLED", "1")
    monkeypatch.setitem(sys.modules, "inquirer", None)
    monkeypatch.setattr(module, "sync_channels_from_runtime_config", lambda: calls.append("sync"))
    monkeypatch.setattr(module, "_auto_create_product", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(
        module,
        "_start_background_telegram_scanner",
        lambda: (_StopEvent(), _Thread()),
    )
    monkeypatch.setattr(
        module,
        "_start_background_shared_deactivation_worker",
        lambda: (calls.append("shared") or _StopEvent(), _Thread()),
    )
    monkeypatch.setattr(
        module,
        "_start_background_old_product_deactivator",
        lambda: calls.append("old") or (_StopEvent(), _Thread()),
    )

    module.main(shafa=True)

    assert "shared" in calls
    assert "old" not in calls


def test_shared_auto_run_enables_planner_worker_and_real_mode(monkeypatch) -> None:
    module = _reload_shafa_main()

    monkeypatch.setenv("SHAFA_SHARED_DEACTIVATION_AUTO_RUN", "1")
    monkeypatch.delenv("SHAFA_SHARED_DEACTIVATION_ENABLED", raising=False)
    monkeypatch.delenv("SHAFA_SHARED_DEACTIVATION_PLANNER_ENABLED", raising=False)
    monkeypatch.delenv("SHAFA_SHARED_DEACTIVATION_WORKER_ENABLED", raising=False)
    monkeypatch.delenv("SHAFA_SHARED_DEACTIVATION_DRY_RUN", raising=False)

    assert module._shared_deactivation_enabled()
    assert module._shared_deactivation_planner_enabled()
    assert module._shared_deactivation_worker_enabled()
    assert not module._shared_deactivation_dry_run_enabled()


def test_shared_auto_run_respects_explicit_dry_run(monkeypatch) -> None:
    module = _reload_shafa_main()

    monkeypatch.setenv("SHAFA_SHARED_DEACTIVATION_AUTO_RUN", "1")
    monkeypatch.setenv("SHAFA_SHARED_DEACTIVATION_DRY_RUN", "1")

    assert module._shared_deactivation_dry_run_enabled()


def test_shared_auto_run_makes_controller_worker_real_by_default(monkeypatch) -> None:
    _reload_shafa_main()
    sys.modules.pop("controller.data_controller", None)
    data_controller = importlib.import_module("controller.data_controller")

    monkeypatch.setenv("SHAFA_SHARED_DEACTIVATION_AUTO_RUN", "1")
    monkeypatch.delenv("SHAFA_SHARED_DEACTIVATION_DRY_RUN", raising=False)

    assert not data_controller._shared_deactivation_dry_run()

    monkeypatch.setenv("SHAFA_SHARED_DEACTIVATION_DRY_RUN", "1")

    assert data_controller._shared_deactivation_dry_run()


def test_shared_auto_run_starts_shared_worker_and_skips_old_direct(
    monkeypatch,
) -> None:
    module = _reload_shafa_main()
    calls: list[object] = []

    class _StopEvent:
        def set(self) -> None:
            calls.append("stop")

    class _Thread:
        def join(self, timeout=None) -> None:
            calls.append(("join", timeout))

    monkeypatch.setenv("SHAFA_SHARED_DEACTIVATION_AUTO_RUN", "1")
    monkeypatch.setitem(sys.modules, "inquirer", None)
    monkeypatch.setattr(module, "sync_channels_from_runtime_config", lambda: calls.append("sync"))
    monkeypatch.setattr(module, "_auto_create_product", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(
        module,
        "_start_background_telegram_scanner",
        lambda: (_StopEvent(), _Thread()),
    )
    monkeypatch.setattr(
        module,
        "_start_background_shared_deactivation_worker",
        lambda: (calls.append("shared") or _StopEvent(), _Thread()),
    )
    monkeypatch.setattr(
        module,
        "_start_background_old_product_deactivator",
        lambda: calls.append("old") or (_StopEvent(), _Thread()),
    )

    module.main(shafa=True)

    assert "shared" in calls
    assert "old" not in calls


def test_shared_plan_once_refuses_non_dry_run_when_shared_disabled(monkeypatch) -> None:
    module = _reload_shafa_main()

    monkeypatch.delenv("SHAFA_SHARED_DEACTIVATION_ENABLED", raising=False)
    monkeypatch.setenv("SHAFA_SHARED_DEACTIVATION_DRY_RUN", "0")
    monkeypatch.setattr(
        module,
        "_shared_deactivation_plan_once",
        module._shared_deactivation_plan_once,
    )

    try:
        module.main(shared_deactivation_plan_once=True)
    except RuntimeError as exc:
        assert "SHAFA_SHARED_DEACTIVATION_ENABLED" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_old_product_deactivate_interval_defaults_to_one_to_three_minutes(
    monkeypatch,
) -> None:
    module = _reload_shafa_main()
    monkeypatch.delenv("SHAFA_BACKGROUND_OLD_PRODUCT_DEACTIVATE_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv(
        "SHAFA_BACKGROUND_OLD_PRODUCT_DEACTIVATE_MIN_INTERVAL_SECONDS",
        raising=False,
    )
    monkeypatch.delenv(
        "SHAFA_BACKGROUND_OLD_PRODUCT_DEACTIVATE_MAX_INTERVAL_SECONDS",
        raising=False,
    )

    assert module._background_old_product_deactivate_interval_range_seconds() == (60, 180)


def test_old_product_deactivate_fixed_interval_keeps_compatibility(
    monkeypatch,
) -> None:
    module = _reload_shafa_main()
    monkeypatch.setenv("SHAFA_BACKGROUND_OLD_PRODUCT_DEACTIVATE_INTERVAL_SECONDS", "90")

    assert module._background_old_product_deactivate_interval_range_seconds() == (90, 90)


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
