import time
from typing import Callable, Optional


def _print_menu(labels: list[str]) -> None:
    print("Select action:")
    for idx, label in enumerate(labels, start=1):
        print(f"{idx}. {label}")
    print("q. Quit")


def _read_choice(count: int) -> Optional[int]:
    value = input("Enter choice: ").strip().lower()
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


def _load_actions() -> list[tuple[str, Callable[[], None]]]:
    import bootstrap
    import main
    import main_no_playwright

    return [
        ("Create product (no Playwright)", main_no_playwright.main),
        ("Create product (Playwright)", main.main),
        ("Bootstrap sizes/brands", bootstrap.main),
        (
            "Auto create product every N minutes (no Playwright)",
            lambda: run_periodic(main_no_playwright.main, "No Playwright"),
        ),
        (
            "Auto create product every N minutes (Playwright)",
            lambda: run_periodic(main.main, "Playwright"),
        ),
    ]


def main_cli(actions: Optional[list[tuple[str, Callable[[], None]]]] = None) -> None:
    actions = actions or _load_actions()
    labels = [label for label, _ in actions]

    while True:
        _print_menu(labels)
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


if __name__ == "__main__":
    main_cli()
