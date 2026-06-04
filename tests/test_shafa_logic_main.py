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
    monkeypatch.setenv("SHAFA_ENABLE_ACCOUNT_OLD_PRODUCT_DEACTIVATOR", "1")
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


def test_account_startup_old_direct_deactivator_is_opt_in(monkeypatch) -> None:
    module = _reload_shafa_main()
    calls: list[object] = []

    class _StopEvent:
        def set(self) -> None:
            calls.append("stop")

    class _Thread:
        def join(self, timeout=None) -> None:
            calls.append(("join", timeout))

    monkeypatch.setenv("SHAFA_ENABLE_ACCOUNT_OLD_PRODUCT_DEACTIVATOR", "1")
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
        lambda: (calls.append("old") or _StopEvent(), _Thread()),
    )

    module.main(shafa=True)

    assert "old" in calls


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
    monkeypatch.setenv("SHAFA_ENABLE_ACCOUNT_OLD_PRODUCT_DEACTIVATOR", "1")
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


def test_save_shafa_login_requires_confirmed_viewer(monkeypatch, tmp_path: Path) -> None:
    module = _reload_shafa_main()
    storage_path = tmp_path / "auth.json"
    confirmation_file = tmp_path / "shafa_login.confirm"
    saved_cookies: list[list[dict]] = []
    storage_writes: list[str] = []

    class _Context:
        def cookies(self):
            return [{"name": "csrftoken", "value": "token", "domain": ".shafa.ua"}]

        def storage_state(self, *, path: str) -> None:
            storage_writes.append(path)

    monkeypatch.setattr(
        module,
        "_fetch_shafa_viewer_identity",
        lambda cookies: {"id": "42", "firstName": "A"},
    )
    monkeypatch.setattr(module, "_saved_session_matches_local_account", lambda viewer: True)

    assert module._save_shafa_login_if_authenticated(
        _Context(),
        storage_path,
        confirmation_file,
        saved_cookies.append,
    )

    assert storage_writes == [str(storage_path)]
    assert saved_cookies == [[{"name": "csrftoken", "value": "token", "domain": ".shafa.ua"}]]
    assert confirmation_file.read_text(encoding="utf-8") == "ok\n"


def test_save_shafa_login_ignores_directory_confirmation_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _reload_shafa_main()
    storage_path = tmp_path / "auth.json"
    saved_cookies: list[list[dict]] = []
    storage_writes: list[str] = []

    class _Context:
        def cookies(self):
            return [{"name": "csrftoken", "value": "token", "domain": ".shafa.ua"}]

        def storage_state(self, *, path: str) -> None:
            storage_writes.append(path)

    monkeypatch.setattr(
        module,
        "_fetch_shafa_viewer_identity",
        lambda cookies: {"id": "42", "firstName": "A"},
    )
    monkeypatch.setattr(module, "_saved_session_matches_local_account", lambda viewer: True)

    assert module._save_shafa_login_if_authenticated(
        _Context(),
        storage_path,
        tmp_path,
        saved_cookies.append,
    )

    assert storage_writes == [str(storage_path)]
    assert saved_cookies == [[{"name": "csrftoken", "value": "token", "domain": ".shafa.ua"}]]


def test_login_account_closes_context_and_browser(monkeypatch) -> None:
    module = _reload_shafa_main()
    closed: list[str] = []

    class _Page:
        url = "https://shafa.ua/uk/register"

        def set_default_timeout(self, timeout: int) -> None:
            pass

        def goto(self, *args, **kwargs) -> None:
            pass

        def wait_for_load_state(self, *args, **kwargs) -> None:
            pass

    class _Context:
        def new_page(self):
            return _Page()

        def close(self) -> None:
            closed.append("context")

    class _Browser:
        def new_context(self):
            return _Context()

        def close(self) -> None:
            closed.append("browser")

    class _PlaywrightManager:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            pass

    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.TimeoutError = TimeoutError
    sync_api.sync_playwright = lambda: _PlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)

    core_context = types.ModuleType("core.context")
    core_context.new_context_with_storage = lambda browser: browser.new_context()
    core_core = types.ModuleType("core.core")
    core_core.get_csrftoken_from_context = lambda ctx: "token"
    data_db = types.ModuleType("data.db")
    data_db.init_db = lambda: None
    data_db.save_cookies = lambda cookies: None
    monkeypatch.setitem(sys.modules, "core.context", core_context)
    monkeypatch.setitem(sys.modules, "core.core", core_core)
    monkeypatch.setitem(sys.modules, "data.db", data_db)

    times = iter([100.0, 104.0, 104.0, 108.0])
    monkeypatch.setattr(module.time, "time", lambda: next(times, 108.0))
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(module, "_launch_visible_browser", lambda p, headless: (_Browser(), "chromium"))
    monkeypatch.setattr(module, "_login_fresh_context_enabled", lambda: True)
    monkeypatch.setattr(module, "_save_shafa_login_if_authenticated", lambda *args: True)

    module._login_account()

    assert closed == ["context", "browser"]


def test_login_account_closes_after_auth_page_disappears(monkeypatch) -> None:
    module = _reload_shafa_main()
    closed: list[str] = []
    saved_cookies: list[list[dict]] = []
    storage_writes: list[str] = []

    class _Page:
        def __init__(self) -> None:
            self._urls = iter(
                [
                    "https://shafa.ua/uk/login",
                    "https://shafa.ua/uk/",
                ]
            )
            self.url = "https://shafa.ua/uk/login"

        def set_default_timeout(self, timeout: int) -> None:
            pass

        def goto(self, *args, **kwargs) -> None:
            pass

        def wait_for_load_state(self, *args, **kwargs) -> None:
            pass

        @property
        def url(self) -> str:
            try:
                self._current_url = next(self._urls)
            except StopIteration:
                pass
            return self._current_url

        @url.setter
        def url(self, value: str) -> None:
            self._current_url = value

    class _Context:
        def new_page(self):
            return _Page()

        def cookies(self):
            return [{"name": "csrftoken", "value": "token", "domain": ".shafa.ua"}]

        def storage_state(self, *, path: str) -> None:
            storage_writes.append(path)

        def close(self) -> None:
            closed.append("context")

    class _Browser:
        def new_context(self):
            return _Context()

        def close(self) -> None:
            closed.append("browser")

    class _PlaywrightManager:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            pass

    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.TimeoutError = TimeoutError
    sync_api.sync_playwright = lambda: _PlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)

    core_context = types.ModuleType("core.context")
    core_context.new_context_with_storage = lambda browser: browser.new_context()
    core_core = types.ModuleType("core.core")
    core_core.get_csrftoken_from_context = lambda ctx: ""
    data_db = types.ModuleType("data.db")
    data_db.init_db = lambda: None
    data_db.save_cookies = saved_cookies.append
    data_const = types.ModuleType("data.const")
    data_const.STORAGE_STATE_PATH = Path("/tmp/auth.json")
    monkeypatch.setitem(sys.modules, "core.context", core_context)
    monkeypatch.setitem(sys.modules, "core.core", core_core)
    monkeypatch.setitem(sys.modules, "data.db", data_db)
    monkeypatch.setitem(sys.modules, "data.const", data_const)

    times = iter([100.0, 101.0, 101.0, 101.0, 109.5])
    monkeypatch.setattr(module.time, "time", lambda: next(times, 109.5))
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(module, "_launch_visible_browser", lambda p, headless: (_Browser(), "chromium"))
    monkeypatch.setattr(module, "_login_fresh_context_enabled", lambda: True)
    monkeypatch.setattr(module, "_save_shafa_login_if_authenticated", lambda *args: False)

    module._login_account()

    assert closed == ["context", "browser"]
    assert storage_writes == []
    assert saved_cookies == []
