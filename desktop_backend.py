from __future__ import annotations

import errno
import importlib.util
import os
import shutil
import socket
import sys
from pathlib import Path

SEED_FILES = ("accounts_state.json", "telegram_channel_templates.json")
SEED_JSON_PAYLOAD = "[]\n"
DEFAULT_BACKEND_PORT = 8000
ADDRESS_IN_USE_WINERROR = 10048
RUNTIME_PROJECT_DIRNAME = "runtime-project"
SHAFA_LOGIC_DIRNAME = "shafa_logic"
SHAFA_CLI_FLAGS = {
    "--shafa",
    "--login-shafa",
    "--telegram-send-code",
    "--telegram-login-phone",
    "--telegram-login-code",
    "--telegram-login-password",
    "--telegram-session-status",
}


def _bundle_dir() -> Path:
    return Path(__file__).resolve().parent


def _data_dir() -> Path:
    configured = os.getenv("SHAFA_DESKTOP_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return _bundle_dir()


def _copy_runtime_project(bundle_dir: Path, data_dir: Path) -> Path | None:
    configured_runtime_dir = os.getenv("SHAFA_RUNTIME_PROJECT_DIR", "").strip()
    if configured_runtime_dir:
        return Path(configured_runtime_dir).expanduser().resolve()

    source_dir = bundle_dir / SHAFA_LOGIC_DIRNAME
    if not (source_dir / "main.py").is_file():
        return None

    runtime_root = data_dir / RUNTIME_PROJECT_DIRNAME
    target_dir = runtime_root / SHAFA_LOGIC_DIRNAME
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source_dir,
        target_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            ".pytest_cache",
            "tests",
        ),
    )
    return runtime_root


def _bootstrap_environment() -> Path:
    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "accounts").mkdir(parents=True, exist_ok=True)

    bundle_dir = _bundle_dir()
    runtime_project_dir = _copy_runtime_project(bundle_dir, data_dir)
    for filename in SEED_FILES:
        source = bundle_dir / filename
        target = data_dir / filename
        if source.exists() and not target.exists():
            shutil.copyfile(source, target)
        if not target.exists():
            target.write_text(SEED_JSON_PAYLOAD, encoding="utf-8")

    os.environ.setdefault("TELEGRAM_ACCOUNTS_BASE_DIR", str(data_dir))
    os.environ.setdefault("ACCOUNTS_STATE_FILE", str(data_dir / "accounts_state.json"))
    os.environ.setdefault("MESSAGE_TEMPLATES_FILE", str(data_dir / "message_templates.json"))
    os.environ.setdefault(
        "CHANNEL_TEMPLATES_STATE_FILE",
        str(data_dir / "telegram_channel_templates.json"),
    )
    os.environ.setdefault("ACCOUNTS_DIR", str(data_dir / "accounts"))
    if runtime_project_dir is not None:
        os.environ.setdefault("SHAFA_RUNTIME_PROJECT_DIR", str(runtime_project_dir))
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    return data_dir


def _looks_like_shafa_cli_args(args: list[str]) -> bool:
    return bool(args) and (
        Path(args[0]).name == "main.py"
        or any(arg in SHAFA_CLI_FLAGS for arg in args)
    )


def _run_embedded_shafa_cli(argv: list[str]) -> int | None:
    args = list(argv)
    if not _looks_like_shafa_cli_args(args):
        return None
    if args and Path(args[0]).name == "main.py":
        args = args[1:]

    project_dir = Path.cwd()
    if not (project_dir / "main.py").is_file():
        configured_project_dir = os.getenv("SHAFA_RUNTIME_PROJECT_DIR", "").strip()
        if configured_project_dir:
            runtime_root = Path(configured_project_dir).expanduser()
            candidate = runtime_root / SHAFA_LOGIC_DIRNAME
            project_dir = candidate if (candidate / "main.py").is_file() else runtime_root

    if not (project_dir / "main.py").is_file():
        print(f"main.py не найден по пути {project_dir}", file=sys.stderr)
        return 1

    project_path = str(project_dir)
    sys.path.insert(0, project_path)
    original_argv = sys.argv
    try:
        sys.argv = ["main.py", *args]
        spec = importlib.util.spec_from_file_location(
            "_shafa_runtime_main",
            project_dir / "main.py",
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Не удалось загрузить main.py из {project_dir}")
        shafa_main = importlib.util.module_from_spec(spec)
        sys.modules["_shafa_runtime_main"] = shafa_main
        spec.loader.exec_module(shafa_main)
        parsed_args = shafa_main.parse_args()
        shafa_main.main(
            shafa=parsed_args.shafa,
            login_shafa=parsed_args.login_shafa,
            mode=parsed_args.mode,
            telegram_send_code_phone=parsed_args.telegram_send_code,
            telegram_login_phone=parsed_args.telegram_login_phone,
            telegram_login_code=parsed_args.telegram_login_code,
            telegram_login_password=parsed_args.telegram_login_password,
            telegram_session_status=parsed_args.telegram_session_status,
        )
    except Exception as exc:
        print(str(exc) or exc.__class__.__name__, file=sys.stderr)
        return 1
    finally:
        sys.argv = original_argv
        sys.modules.pop("_shafa_runtime_main", None)
        if sys.path and sys.path[0] == project_path:
            sys.path.pop(0)
    return 0


def _reserve_port(host: str, port: int) -> int:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        probe.bind((host, port))
        probe.listen(1)
        return int(probe.getsockname()[1])


def _resolve_backend_port(host: str, preferred_port: int = DEFAULT_BACKEND_PORT) -> tuple[int, bool]:
    configured_port = os.getenv("SHAFA_BACKEND_PORT", "").strip()
    if configured_port:
        return int(configured_port), False

    return preferred_port, False


DATA_DIR = _bootstrap_environment()


def _is_address_in_use_error(error: OSError) -> bool:
    if error.errno == errno.EADDRINUSE:
        return True
    if getattr(error, "winerror", None) == ADDRESS_IN_USE_WINERROR:
        return True
    return False


def main() -> None:
    import uvicorn
    from telegram_accounts_api.main import app

    host = os.getenv("SHAFA_BACKEND_HOST", "127.0.0.1").strip() or "127.0.0.1"
    configured_port = os.getenv("SHAFA_BACKEND_PORT", "").strip()
    port, used_fallback_port = _resolve_backend_port(host)
    log_level = os.getenv("LOG_LEVEL", "info").lower()

    while True:
        os.environ["SHAFA_BACKEND_PORT"] = str(port)
        if used_fallback_port:
            print(
                f"Port {DEFAULT_BACKEND_PORT} is busy on {host}; using available port {port}. "
                "Set SHAFA_BACKEND_PORT to override.",
                flush=True,
            )
        print(f"Starting desktop backend on {host}:{port} with data dir {DATA_DIR}", flush=True)

        try:
            uvicorn.run(app, host=host, port=port, log_level=log_level, access_log=False)
            return
        except OSError as error:
            if configured_port or not _is_address_in_use_error(error):
                raise

            port = _reserve_port(host, 0)
            used_fallback_port = True


if __name__ == "__main__":
    cli_exit_code = _run_embedded_shafa_cli(sys.argv[1:])
    if cli_exit_code is not None:
        raise SystemExit(cli_exit_code)
    main()
