import sys
import time
from typing import Callable, Optional

try:
    import termios
    import tty
except ImportError:  # pragma: no cover - non-POSIX
    termios = None
    tty = None


def _print_menu(labels: list[str], title: str, quit_label: str) -> None:
    print(title)
    for idx, label in enumerate(labels, start=1):
        print(f"{idx}. {label}")
    print(quit_label)


def _read_choice(count: int, prompt: str = "Enter choice: ") -> Optional[int]:
    value = input(prompt).strip().lower()
    if value in {"q", "quit", "exit"}:
        return None
    if not value.isdigit():
        return -1
    choice = int(value)
    if 1 <= choice <= count:
        return choice
    return -1


def _prompt_minutes() -> Optional[int]:
    raw = input("Interval in minutes (>=1): ").strip()
    if not raw:
        return None
    if not raw.isdigit():
        return -1
    value = int(raw)
    if value < 1:
        return -1
    return value


def _read_single_key() -> Optional[str]:
    if not sys.stdin.isatty() or termios is None or tty is None:
        return None
    fd = sys.stdin.fileno()
    try:
        old_settings = termios.tcgetattr(fd)
    except termios.error:
        return None
    try:
        tty.setraw(fd)
        key = sys.stdin.read(1)
        if key == "\x1b":
            key += sys.stdin.read(2)
        return key
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _choose_yes_no(question: str, default: bool = True) -> Optional[bool]:
    if not sys.stdin.isatty() or termios is None or tty is None:
        while True:
            raw = input(f"{question} (y/n): ").strip().lower()
            if raw in {"q", "quit"}:
                return None
            if raw in {"y", "yes"}:
                return True
            if raw in {"n", "no"}:
                return False
        return None

    selection = default
    while True:
        yes = "[Yes]" if selection else " Yes "
        no = "[No]" if not selection else " No "
        print(f"\r{question} {yes} {no} ", end="", flush=True)
        key = _read_single_key()
        if key in {"\r", "\n"}:
            print()
            return selection
        if key in {"y", "Y"}:
            print()
            return True
        if key in {"n", "N"}:
            print()
            return False
        if key in {"q", "Q"}:
            print()
            return None
        if key == "\x03":
            raise KeyboardInterrupt
        if key in {"\x1b[D", "\x1b[C"}:
            selection = not selection


def run_periodic(action: Callable[[], None], label: str) -> None:
    while True:
        minutes = _prompt_minutes()
        if minutes is None:
            minutes = 10
        if minutes == -1:
            print("Invalid interval.")
            continue
        break
    interval = minutes * 60
    print(f"Starting periodic mode for: {label}. Interval: {minutes} min.")
    while True:
        try:
            action()
        except Exception as exc:
            print(f"[ERROR] {label} failed: {exc}")
        try:
            next_at = time.strftime("%H:%M:%S", time.localtime(time.time() + interval))
            print(f"Next run at {next_at}. Press Ctrl+C to stop.")
            time.sleep(interval)
        except KeyboardInterrupt:
            print()
            return


def _create_product() -> None:
    import main
    import main_no_playwright

    use_gui = _choose_yes_no("With Browser GUI?", default=True)
    if use_gui is None:
        return
    if use_gui:
        main.main()
    else:
        main_no_playwright.main()


def _auto_create_product() -> None:
    import main
    import main_no_playwright

    use_gui = _choose_yes_no("With Browser GUI?", default=True)
    if use_gui is None:
        return
    if use_gui:
        run_periodic(main.main, "Playwright")
    else:
        run_periodic(main_no_playwright.main, "No Playwright")


def _bootstrap_project() -> None:
    import bootstrap

    bootstrap.main()


def _add_telegram_channel() -> None:
    from data.db import save_telegram_channels

    raw_id = input("Telegram channel id: ").strip()
    if not raw_id:
        print("Channel id is required.")
        return
    try:
        channel_id = int(raw_id)
    except ValueError:
        print("Channel id must be a number.")
        return
    name = input("Channel name: ").strip()
    if not name:
        print("Channel name is required.")
        return
    alias = input("Alias (optional): ").strip() or None
    save_telegram_channels([(channel_id, name, alias)])
    print("Channel saved.")


def _list_telegram_channels() -> None:
    from data.db import load_telegram_channels

    channels = load_telegram_channels()
    if not channels:
        print("No Telegram channels configured.")
        return
    print("Telegram channels:")
    for idx, row in enumerate(channels, start=1):
        alias = row.get("alias") or "-"
        print(f"{idx}. {row['channel_id']} | {row['name']} | {alias}")


def _settings_menu() -> None:
    labels = [
        "Add Telegram channel",
        "List Telegram channels",
    ]
    while True:
        _print_menu(labels, title="Settings:", quit_label="q. Back")
        try:
            choice = _read_choice(len(labels))
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice is None:
            return
        if choice == -1:
            print("Invalid choice.")
            continue
        if choice == 1:
            _add_telegram_channel()
        elif choice == 2:
            _list_telegram_channels()


def _legacy_menu(actions: list[tuple[str, Callable[[], None]]]) -> None:
    labels = [label for label, _ in actions]
    while True:
        _print_menu(labels, title="Select action:", quit_label="q. Quit")
        try:
            choice = _read_choice(len(actions))
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice is None:
            return
        if choice == -1:
            print("Invalid choice.")
            continue
        _, action = actions[choice - 1]
        action()


def main_cli(actions: Optional[list[tuple[str, Callable[[], None]]]] = None) -> None:
    if actions:
        _legacy_menu(actions)
        return

    labels = [
        "Create product",
        "Bootstrap project",
        "Auto create product",
        "Settings",
    ]
    while True:
        _print_menu(labels, title="Select action:", quit_label="q. Quit")
        try:
            choice = _read_choice(len(labels))
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice is None:
            return
        if choice == -1:
            print("Invalid choice.")
            continue
        if choice == 1:
            _create_product()
        elif choice == 2:
            _bootstrap_project()
        elif choice == 3:
            _auto_create_product()
        elif choice == 4:
            _settings_menu()


if __name__ == "__main__":
    main_cli()
