import json
import re
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


def _print_products(limit: int = 20) -> list[dict]:
    from data.db import list_uploaded_products

    products = list_uploaded_products(limit=limit)
    if not products:
        print("No products found.")
        return []
    print("Products:")
    for idx, row in enumerate(products, start=1):
        name = row.get("name") or "N/A"
        product_id = row.get("product_id") or "N/A"
        print(f"{idx}. {name} | {product_id}")
    return products


def _parse_index_selection(value: str, count: int) -> list[int]:
    tokens = re.findall(r"\d+", value)
    if not tokens:
        return []
    indexes: list[int] = []
    seen: set[int] = set()
    for token in tokens:
        idx = int(token)
        if not (1 <= idx <= count):
            return []
        if idx not in seen:
            seen.add(idx)
            indexes.append(idx)
    return indexes


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


def _format_channel_label(channel: dict) -> str:
    name = channel.get("name") or str(channel.get("channel_id") or "")
    alias = channel.get("alias")
    if alias:
        return f"{name} ({alias}) | {channel['channel_id']}"
    return f"{name} | {channel['channel_id']}"


def _delete_telegram_channel(channel: dict) -> None:
    from data.db import delete_telegram_channel

    label = _format_channel_label(channel)
    confirm = _choose_yes_no(f"Delete channel {label}?", default=False)
    if confirm is None or not confirm:
        return
    delete_telegram_channel(channel["channel_id"])
    print("Channel deleted.")


def _rename_telegram_channel(channel: dict) -> None:
    from data.db import rename_telegram_channel

    name = channel.get("name") or str(channel.get("channel_id") or "")
    raw = input(f"New name for {name}: ").strip()
    if not raw:
        print("Channel name is required.")
        return
    if not rename_telegram_channel(channel["channel_id"], raw):
        print("Rename failed.")
        return
    print("Channel renamed.")


def _change_telegram_channel_alias(channel: dict) -> None:
    from data.db import update_telegram_channel_alias

    name = channel.get("name") or str(channel.get("channel_id") or "")
    current = channel.get("alias") or "-"
    raw = input(f"New alias for {name} (blank to clear, current: {current}): ").strip()
    alias = raw or None
    if not update_telegram_channel_alias(channel["channel_id"], alias):
        print("Alias update failed.")
        return
    print("Alias updated.")


def _change_telegram_channel_id(channel: dict) -> None:
    from data.db import update_telegram_channel_id

    name = channel.get("name") or str(channel.get("channel_id") or "")
    current_id = channel.get("channel_id")
    raw = input(f"New channel ID for {name} (current: {current_id}): ").strip()
    if not raw:
        print("Channel ID is required.")
        return
    try:
        new_id = int(raw)
    except ValueError:
        print("Invalid channel ID.")
        return
    if new_id == current_id:
        print("Channel ID unchanged.")
        return
    if not update_telegram_channel_id(current_id, new_id):
        print("Channel ID update failed.")
        return
    print("Channel ID updated.")


def _manage_telegram_channel_actions(channel: dict) -> None:
    labels = [
        "Delete channel",
        "Rename channel",
        "Change alias (e.g. extra_photos)",
        "Change ID",
    ]
    while True:
        _print_menu(labels, title="What we need to do?", quit_label="q. Back")
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
            _delete_telegram_channel(channel)
            return
        if choice == 2:
            _rename_telegram_channel(channel)
            return
        if choice == 3:
            _change_telegram_channel_alias(channel)
            return
        if choice == 4:
            _change_telegram_channel_id(channel)
            return


def _manage_telegram_channels() -> None:
    from data.db import load_telegram_channels

    while True:
        channels = load_telegram_channels()
        labels = [_format_channel_label(row) for row in channels]
        labels.append("[ + ] Add Telegram channel")
        _print_menu(labels, title="Manage Telegram channels:", quit_label="q. Back")
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
        if choice == len(labels):
            _add_telegram_channel()
            continue
        channel = channels[choice - 1]
        _manage_telegram_channel_actions(channel)


def _clear_storage_state_cookies(path) -> bool:
    if not path.exists():
        return False
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return True
    if not isinstance(data, dict):
        data = {}
    data["cookies"] = []
    path.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    return True


def _delete_account_cookies() -> None:
    from data.const import STORAGE_STATE_PATH
    from data.db import delete_all_cookies

    confirm = _choose_yes_no(
        "Delete account cookies from DB and auth.json?",
        default=False,
    )
    if confirm is None or not confirm:
        return
    removed = delete_all_cookies()
    auth_updated = _clear_storage_state_cookies(STORAGE_STATE_PATH)
    if auth_updated:
        print(f"Deleted {removed} cookie(s). auth.json updated.")
    else:
        print(f"Deleted {removed} cookie(s). auth.json not found.")


def _deactivate_product() -> None:
    from core import deactivate_product
    from data.db import mark_uploaded_products_deactivated

    products = _print_products()
    if not products:
        return
    raw = input("Select product number(s) to deactivate: ").strip()
    if not raw or raw.lower() in {"q", "quit"}:
        return
    indexes = _parse_index_selection(raw, len(products))
    if not indexes:
        print("No valid selections.")
        return
    product_ids: list[int] = []
    seen: set[int] = set()
    for idx in indexes:
        product_id_raw = str(products[idx - 1].get("product_id") or "")
        for product_id in deactivate_product.parse_product_ids(product_id_raw):
            if product_id not in seen:
                seen.add(product_id)
                product_ids.append(product_id)
    if not product_ids:
        print("No valid product ids provided.")
        return
    result = deactivate_product.deactivate_products(product_ids)
    if not result:
        return
    errors = result.get("errors") or []
    if errors:
        print(f"Deactivation errors: {errors}")
        return
    if result.get("isSuccess"):
        mark_uploaded_products_deactivated(product_ids)
        print(f"Deactivated {len(product_ids)} product(s).")
        return
    print("Deactivation failed.")


def _product_management_menu() -> None:
    labels = [
        "Create Product",
        "Auto create product",
        "Deactivate product",
        "List of products",
    ]
    while True:
        _print_menu(labels, title="Product management:", quit_label="q. Back")
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
            _auto_create_product()
        elif choice == 3:
            _deactivate_product()
        elif choice == 4:
            _print_products()


def _settings_menu() -> None:
    labels = [
        "Bootstrap project",
        "Manage Telegram channels",
        "Delete account cookies",
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
            _bootstrap_project()
        elif choice == 2:
            _manage_telegram_channels()
        elif choice == 3:
            _delete_account_cookies()


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
        "Product management",
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
            _product_management_menu()
        elif choice == 2:
            _settings_menu()


if __name__ == "__main__":
    main_cli()
