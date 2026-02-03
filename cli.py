import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

import inquirer

_ADD_CHANNEL = object()


def _ensure_tty() -> bool:
    if not sys.stdin.isatty():
        print("Нужен интерактивный терминал.")
        return False
    return True


def _print_ascii_banner() -> None:
    path = Path(__file__).resolve().parent / "data" / "ascii.txt"
    if not path.exists():
        return
    try:
        banner = path.read_text(encoding="utf-8")
    except OSError:
        return
    if not banner:
        return
    if banner.endswith("\n"):
        sys.stdout.write(banner)
    else:
        sys.stdout.write(f"{banner}\n")


def _prompt_list(
    message: str, choices: list[tuple[str, Any]], default: Any = None
) -> Optional[Any]:
    if not _ensure_tty():
        return None
    question = inquirer.List(
        "choice",
        message=message,
        choices=choices,
        default=default,
    )
    try:
        answers = inquirer.prompt([question])
    except KeyboardInterrupt:
        print()
        return None
    if not answers:
        return None
    return answers.get("choice")


def _prompt_checkbox(message: str, choices: list[tuple[str, Any]]) -> Optional[list[Any]]:
    if not _ensure_tty():
        return None
    question = inquirer.Checkbox(
        "items",
        message=message,
        choices=choices,
    )
    try:
        answers = inquirer.prompt([question])
    except KeyboardInterrupt:
        print()
        return None
    if not answers:
        return None
    return answers.get("items") or []


def _prompt_text(
    message: str,
    default: Optional[str] = None,
    required: bool = False,
    validator: Optional[Callable[[str], Any]] = None,
) -> Optional[str]:
    if not _ensure_tty():
        return None

    def _validate(_: dict, value: str) -> Any:
        if required and not value:
            return "Поле обязательно."
        if validator is None:
            return True
        return validator(value)

    question = inquirer.Text(
        "value",
        message=message,
        default=default if default is not None else "",
        # When not required and no custom validator, always accept input.
        validate=_validate if required or validator else True,
    )
    try:
        answers = inquirer.prompt([question])
    except KeyboardInterrupt:
        print()
        return None
    if not answers:
        return None
    return str(answers.get("value") or "")


def _prompt_int(
    message: str,
    default: Optional[int] = None,
    min_value: Optional[int] = None,
    required: bool = False,
) -> Optional[int]:
    if not _ensure_tty():
        return None

    def _validate(_: dict, value: str) -> Any:
        if not value:
            if required:
                return "Введите число."
            return True
        if not value.isdigit():
            return "Введите число."
        number = int(value)
        if min_value is not None and number < min_value:
            return f"Минимум {min_value}."
        return True

    question = inquirer.Text(
        "value",
        message=message,
        default=str(default) if default is not None else "",
        validate=_validate if required or min_value is not None else None,
    )
    try:
        answers = inquirer.prompt([question])
    except KeyboardInterrupt:
        print()
        return None
    if not answers:
        return None
    raw = str(answers.get("value") or "").strip()
    if not raw:
        return None
    return int(raw)


def _prompt_minutes() -> Optional[int]:
    return _prompt_int("Интервал в минутах (>=1):", default=10, min_value=1)


def _choose_yes_no(question: str, default: bool = True) -> Optional[bool]:
    if not _ensure_tty():
        return None
    prompt = inquirer.Confirm("confirm", message=question, default=default)
    try:
        answers = inquirer.prompt([prompt])
    except KeyboardInterrupt:
        print()
        return None
    if not answers:
        return None
    return bool(answers.get("confirm"))


def run_periodic(action: Callable[[], None], label: str) -> None:
    minutes = _prompt_minutes()
    if minutes is None:
        return
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


def _prompt_action_menu(
    title: str,
    actions: list[tuple[str, Callable[[], None]]],
    exit_label: str,
) -> Optional[Callable[[], None]]:
    choices: list[tuple[str, Any]] = [(label, action) for label, action in actions]
    if exit_label:
        choices.append((exit_label, None))
    return _prompt_list(title, choices)


def _select_products_for_deactivation(products: list[dict]) -> list[str]:
    choices: list[tuple[str, str]] = []
    for idx, row in enumerate(products, start=1):
        name = row.get("name") or "нет данных"
        product_id = str(row.get("product_id") or "")
        label = f"{idx}. {name} | {product_id or 'нет данных'}"
        choices.append((label, product_id))

    selected = _prompt_checkbox("Выберите товары для деактивации", choices)
    if selected is None:
        return []
    if not selected:
        print("Ничего не выбрано.")
        return []
    return [str(value) for value in selected if value]


def _add_telegram_channel() -> None:
    from data.db import save_telegram_channels

    channel_id = _prompt_int("ID Telegram-канала", required=True)
    if channel_id is None:
        return
    name = _prompt_text("Название канала", required=True)
    if not name:
        return
    alias = _prompt_text("Алиас (необязательно)") or None
    save_telegram_channels([(channel_id, name, alias)])
    print("Канал сохранен.")


def _list_telegram_channels() -> None:
    from data.db import load_telegram_channels

    channels = load_telegram_channels()
    if not channels:
        print("Telegram-каналы не настроены.")
        return
    print("Telegram-канал")
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
    raw = _prompt_text(f"Новое имя для {name}", required=True)
    if not raw:
        return
    if not rename_telegram_channel(channel["channel_id"], raw):
        print("Переименование не удалось.")
        return
    print("Канал переименован.")


def _change_telegram_channel_alias(channel: dict) -> None:
    from data.db import update_telegram_channel_alias

    name = channel.get("name") or str(channel.get("channel_id") or "")
    current = channel.get("alias") or "-"
    raw = _prompt_text(
        f"Новый алиас для {name} (пусто - удалить, текущий: {current}) "
    )
    if raw is None:
        return
    alias = raw or None
    if not update_telegram_channel_alias(channel["channel_id"], alias):
        print("Не удалось обновить алиас.")
        return
    print("Алиас обновлен.")


def _change_telegram_channel_id(channel: dict) -> None:
    from data.db import update_telegram_channel_id

    name = channel.get("name") or str(channel.get("channel_id") or "")
    current_id = channel.get("channel_id")
    new_id = _prompt_int(
        f"Новый ID канала для {name} (текущий: {current_id}) ",
        required=True,
    )
    if new_id is None:
        return
    if new_id == current_id:
        print("ID канала не изменен.")
        return
    if not update_telegram_channel_id(current_id, new_id):
        print("Не удалось обновить ID канала.")
        return
    print("ID канала обновлен.")


def _manage_telegram_channel_actions(channel: dict) -> None:
    actions = [
        ("Удалить канал", lambda: _delete_telegram_channel(channel)),
        ("Переименовать канал", lambda: _rename_telegram_channel(channel)),
        (
            "Изменить алиас (например, extra_photos)",
            lambda: _change_telegram_channel_alias(channel),
        ),
        ("Изменить ID", lambda: _change_telegram_channel_id(channel)),
    ]
    action = _prompt_action_menu("Что нужно сделать?", actions, "Назад")
    if action is None:
        return
    action()


def _manage_telegram_channels() -> None:
    from data.db import load_telegram_channels

    while True:
        channels = load_telegram_channels()
        choices: list[tuple[str, Any]] = [
            (_format_channel_label(row), row) for row in channels
        ]
        choices.append(("[ + ] Добавить Telegram-канал", _ADD_CHANNEL))
        choices.append(("Назад", None))
        selection = _prompt_list("Управление Telegram-каналами", choices)
        if selection is None:
            return
        if selection is _ADD_CHANNEL:
            _add_telegram_channel()
            continue
        _manage_telegram_channel_actions(selection)


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


def _logout_and_reset_products() -> None:
    from data.const import STORAGE_STATE_PATH
    from data.db import delete_all_cookies, reset_telegram_products_created

    confirm = _choose_yes_no(
        "Выйти из аккаунта и вернуть все товары в очередь?",
        default=False,
    )
    if confirm is None or not confirm:
        return
    removed = delete_all_cookies()
    auth_updated = _clear_storage_state_cookies(STORAGE_STATE_PATH)
    reset_count = reset_telegram_products_created()
    if auth_updated:
        print(f"Удалено cookies: {removed}. auth.json обновлен.")
    else:
        print(f"Удалено cookies: {removed}. auth.json не найден.")
    print(f"Сброшено товаров: {reset_count}.")


def _deactivate_product() -> None:
    from core import deactivate_product
    from data.db import mark_uploaded_products_deactivated

    products = _print_products()
    if not products:
        return
    selected_values = _select_products_for_deactivation(products)
    if not selected_values:
        return
    product_ids: list[int] = []
    seen: set[int] = set()
    for value in selected_values:
        for product_id in deactivate_product.parse_product_ids(value):
            if product_id not in seen:
                seen.add(product_id)
                product_ids.append(product_id)
    if not product_ids:
        print("Не переданы корректные ID товаров.")
        return
    successes: list[int] = []
    errors: list[dict] = []
    for product_id in product_ids:
        result = deactivate_product.deactivate_products([product_id])
        if not result:
            errors.append(
                {
                    "product_id": product_id,
                    "error": "Не удалось получить ответ.",
                }
            )
            break
        result_errors = result.get("errors") or []
        if result_errors:
            errors.append(
                {
                    "product_id": product_id,
                    "error": result_errors,
                }
            )
            continue
        if result.get("isSuccess"):
            mark_uploaded_products_deactivated([product_id])
            successes.append(product_id)
            continue
        errors.append(
            {
                "product_id": product_id,
                "error": "Деактивация не удалась.",
            }
        )
    if errors:
        print(f"Ошибки деактивации: {errors}")
    if successes:
        print(f"Деактивировано товаров: {len(successes)}.")
    if not successes and not errors:
        print("Деактивация не удалась.")


def _product_management_menu() -> None:
    actions = [
        ("Создать товар", _create_product),
        ("Автосоздание товара", _auto_create_product),
        ("Деактивировать товары", _deactivate_product),
        ("Список товаров", _print_products),
    ]
    while True:
        action = _prompt_action_menu("Управление товарами", actions, "Назад")
        if action is None:
            return
        action()


def _settings_menu() -> None:
    actions = [
        ("Инициализация проекта", _bootstrap_project),
        ("Управление Telegram-каналами", _manage_telegram_channels),
        ("Удалить cookies аккаунта", _delete_account_cookies),
        ("Выйти и вернуть товары в очередь", _logout_and_reset_products),
    ]
    while True:
        action = _prompt_action_menu("Настройки", actions, "Назад")
        if action is None:
            return
        action()


def _legacy_menu(actions: list[tuple[str, Callable[[], None]]]) -> None:
    while True:
        action = _prompt_action_menu("Выберите действие", actions, "Выход")
        if action is None:
            return
        action()


def main_cli(actions: Optional[list[tuple[str, Callable[[], None]]]] = None) -> None:
    _print_ascii_banner()
    if actions:
        _legacy_menu(actions)
        return

    actions = [
        ("Управление товарами", _product_management_menu),
        ("Настройки", _settings_menu),
    ]
    while True:
        action = _prompt_action_menu("Выберите действие", actions, "Выход")
        if action is None:
            return
        action()


if __name__ == "__main__":
    main_cli()
