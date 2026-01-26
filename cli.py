import json
import random
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


def _read_choice(count: int, prompt: str = "Введите номер: ") -> Optional[int]:
    value = input(prompt).strip().lower()
    if value in {"q", "quit", "exit", "назад", "выход", "й"}:
        return None
    if not value.isdigit():
        return -1
    choice = int(value)
    if 1 <= choice <= count:
        return choice
    return -1


def _prompt_minutes() -> Optional[int]:
    raw = input("Интервал в минутах (>=1): ").strip()
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
            raw = input(f"{question} (д/н): ").strip().lower()
            if raw in {"q", "quit", "выход", "назад", "й"}:
                return None
            if raw in {"y", "yes", "д", "да"}:
                return True
            if raw in {"n", "no", "н", "нет"}:
                return False
        return None

    selection = default
    while True:
        yes = "[Да]" if selection else " Да "
        no = "[Нет]" if not selection else " Нет "
        print(f"\r{question} {yes} {no} ", end="", flush=True)
        key = _read_single_key()
        if key in {"\r", "\n"}:
            print()
            return selection
        if key in {"y", "Y", "д", "Д"}:
            print()
            return True
        if key in {"n", "N", "н", "Н"}:
            print()
            return False
        if key in {"q", "Q", "й", "Й"}:
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
            print("Неверный интервал.")
            continue
        break
    interval = minutes * 60
    print(f"Запуск периодического режима: {label}. Интервал: {minutes} мин.")
    while True:
        try:
            action()
        except Exception as exc:
            print(f"[ОШИБКА] {label} не выполнено: {exc}")
        try:
            percent = random.randint(1, 30)
            sign = random.choice((-1, 1))
            jitter = interval * (percent / 100.0)
            delay = max(1.0, interval + sign * jitter)
            next_at = time.strftime("%H:%M:%S", time.localtime(time.time() + delay))
            direction = "+" if sign > 0 else "-"
            delay_minutes = delay / 60.0
            print(
                "Следующий запуск в "
                f"{next_at}. Пауза: {delay_minutes:.1f} мин ({direction}{percent}%). "
                "Нажмите Ctrl+C для остановки."
            )
            time.sleep(delay)
        except KeyboardInterrupt:
            print()
            return


def _create_product() -> None:
    import main
    import main_no_playwright

    use_gui = _choose_yes_no("С окном браузера?", default=True)
    if use_gui is None:
        return
    if use_gui:
        main.main()
    else:
        main_no_playwright.main()


def _auto_create_product() -> None:
    import main
    import main_no_playwright

    use_gui = _choose_yes_no("С окном браузера?", default=True)
    if use_gui is None:
        return
    if use_gui:
        run_periodic(main.main, "Playwright")
    else:
        run_periodic(main_no_playwright.main, "Без Playwright")


def _bootstrap_project() -> None:
    import bootstrap

    bootstrap.main()


def _print_products(limit: int = 20) -> list[dict]:
    from data.db import list_uploaded_products

    products = list_uploaded_products(limit=limit)
    if not products:
        print("Товары не найдены.")
        return []
    print("Товары:")
    for idx, row in enumerate(products, start=1):
        name = row.get("name") or "нет данных"
        product_id = row.get("product_id") or "нет данных"
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

    raw_id = input("ID Telegram-канала: ").strip()
    if not raw_id:
        print("ID канала обязателен.")
        return
    try:
        channel_id = int(raw_id)
    except ValueError:
        print("ID канала должен быть числом.")
        return
    name = input("Название канала: ").strip()
    if not name:
        print("Название канала обязательно.")
        return
    alias = input("Алиас (необязательно): ").strip() or None
    save_telegram_channels([(channel_id, name, alias)])
    print("Канал сохранен.")


def _list_telegram_channels() -> None:
    from data.db import load_telegram_channels

    channels = load_telegram_channels()
    if not channels:
        print("Telegram-каналы не настроены.")
        return
    print("Telegram-каналы:")
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
    confirm = _choose_yes_no(f"Удалить канал {label}?", default=False)
    if confirm is None or not confirm:
        return
    delete_telegram_channel(channel["channel_id"])
    print("Канал удален.")


def _rename_telegram_channel(channel: dict) -> None:
    from data.db import rename_telegram_channel

    name = channel.get("name") or str(channel.get("channel_id") or "")
    raw = input(f"Новое имя для {name}: ").strip()
    if not raw:
        print("Название канала обязательно.")
        return
    if not rename_telegram_channel(channel["channel_id"], raw):
        print("Переименование не удалось.")
        return
    print("Канал переименован.")


def _change_telegram_channel_alias(channel: dict) -> None:
    from data.db import update_telegram_channel_alias

    name = channel.get("name") or str(channel.get("channel_id") or "")
    current = channel.get("alias") or "-"
    raw = input(
        f"Новый алиас для {name} (пусто - удалить, текущий: {current}): "
    ).strip()
    alias = raw or None
    if not update_telegram_channel_alias(channel["channel_id"], alias):
        print("Не удалось обновить алиас.")
        return
    print("Алиас обновлен.")


def _change_telegram_channel_id(channel: dict) -> None:
    from data.db import update_telegram_channel_id

    name = channel.get("name") or str(channel.get("channel_id") or "")
    current_id = channel.get("channel_id")
    raw = input(f"Новый ID канала для {name} (текущий: {current_id}): ").strip()
    if not raw:
        print("ID канала обязателен.")
        return
    try:
        new_id = int(raw)
    except ValueError:
        print("Неверный ID канала.")
        return
    if new_id == current_id:
        print("ID канала не изменен.")
        return
    if not update_telegram_channel_id(current_id, new_id):
        print("Не удалось обновить ID канала.")
        return
    print("ID канала обновлен.")


def _manage_telegram_channel_actions(channel: dict) -> None:
    labels = [
        "Удалить канал",
        "Переименовать канал",
        "Изменить алиас (например, extra_photos)",
        "Изменить ID",
    ]
    while True:
        _print_menu(labels, title="Что нужно сделать?", quit_label="q. Назад")
        try:
            choice = _read_choice(len(labels))
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice is None:
            return
        if choice == -1:
            print("Неверный выбор.")
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
        labels.append("[ + ] Добавить Telegram-канал")
        _print_menu(labels, title="Управление Telegram-каналами:", quit_label="q. Назад")
        try:
            choice = _read_choice(len(labels))
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice is None:
            return
        if choice == -1:
            print("Неверный выбор.")
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
        "Удалить cookies аккаунта из БД и auth.json?",
        default=False,
    )
    if confirm is None or not confirm:
        return
    removed = delete_all_cookies()
    auth_updated = _clear_storage_state_cookies(STORAGE_STATE_PATH)
    if auth_updated:
        print(f"Удалено cookies: {removed}. auth.json обновлен.")
    else:
        print(f"Удалено cookies: {removed}. auth.json не найден.")


def _deactivate_product() -> None:
    from core import deactivate_product
    from data.db import mark_uploaded_products_deactivated

    products = _print_products()
    if not products:
        return
    raw = input("Введите номер(а) товара для деактивации: ").strip()
    if not raw or raw.lower() in {"q", "quit", "назад", "выход", "й"}:
        return
    indexes = _parse_index_selection(raw, len(products))
    if not indexes:
        print("Нет корректных выборов.")
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
        print("Не переданы корректные ID товаров.")
        return
    result = deactivate_product.deactivate_products(product_ids)
    if not result:
        return
    errors = result.get("errors") or []
    if errors:
        print(f"Ошибки деактивации: {errors}")
        return
    if result.get("isSuccess"):
        mark_uploaded_products_deactivated(product_ids)
        print(f"Деактивировано товаров: {len(product_ids)}.")
        return
    print("Деактивация не удалась.")


def _product_management_menu() -> None:
    labels = [
        "Создать товар",
        "Автосоздание товара",
        "Деактивировать товар",
        "Список товаров",
    ]
    while True:
        _print_menu(labels, title="Управление товарами:", quit_label="q. Назад")
        try:
            choice = _read_choice(len(labels))
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice is None:
            return
        if choice == -1:
            print("Неверный выбор.")
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
        "Инициализация проекта",
        "Управление Telegram-каналами",
        "Удалить cookies аккаунта",
    ]
    while True:
        _print_menu(labels, title="Настройки:", quit_label="q. Назад")
        try:
            choice = _read_choice(len(labels))
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice is None:
            return
        if choice == -1:
            print("Неверный выбор.")
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
        _print_menu(labels, title="Выберите действие:", quit_label="q. Выход")
        try:
            choice = _read_choice(len(actions))
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice is None:
            return
        if choice == -1:
            print("Неверный выбор.")
            continue
        _, action = actions[choice - 1]
        action()


def main_cli(actions: Optional[list[tuple[str, Callable[[], None]]]] = None) -> None:
    if actions:
        _legacy_menu(actions)
        return

    labels = [
        "Управление товарами",
        "Настройки",
    ]
    while True:
        _print_menu(labels, title="Выберите действие:", quit_label="q. Выход")
        try:
            choice = _read_choice(len(labels))
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice is None:
            return
        if choice == -1:
            print("Неверный выбор.")
            continue
        if choice == 1:
            _product_management_menu()
        elif choice == 2:
            _settings_menu()


if __name__ == "__main__":
    main_cli()
