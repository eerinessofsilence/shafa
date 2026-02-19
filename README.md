# Автоматизация товаров Shafa

Проект автоматизирует создание товаров на [shafa.ua](https://shafa.ua) из постов Telegram-каналов.

Проект:
- забирает сообщения из Telegram-каналов,
- парсит данные товара (название, бренд, размер, цвет, цена),
- скачивает фотографии,
- загружает фото и создает товары через Shafa GraphQL API,
- хранит состояние в локальной SQLite-базе.

## Возможности

- Интерактивное CLI-меню (`main.py`) для ежедневной работы.
- Создание товаров через Playwright (`core.with_playwright`).
- Создание товаров без Playwright (`core.no_playwright`).
- Инициализация проекта с синхронизацией размеров и брендов.
- Вход в аккаунт с сохранением cookies (`auth.json` + БД).
- Деактивация уже загруженных товаров.
- Управление Telegram-каналами из CLI (добавление/переименование/удаление/alias/id).
- Локальное хранение распарсенных Telegram-товаров и истории загруженных товаров.

## Требования

- Python 3.9+
- Приложение Telegram API (`api_id` + `api_hash`)
- Аккаунт Shafa
- Установленные зависимости Python из `requirements.txt`
- Chromium для Playwright-сценариев (`playwright install chromium`)

Опционально:
- `Pillow` (рекомендуется для `core.no_playwright`, включает автосжатие слишком больших изображений)

## Установка

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Если нужно автоматическое сжатие изображений в режиме без Playwright:

```bash
pip install pillow
```

## Настройка

Создайте `.env` из `.env.example`:

```bash
cp .env.example .env
```

Обязательные переменные:

| Переменная | Описание |
| --- | --- |
| `SHAFA_TELEGRAM_API_ID` | Telegram API ID (целое число) |
| `SHAFA_TELEGRAM_API_HASH` | Telegram API hash |

Опциональные переменные:

| Переменная | По умолчанию | Описание |
| --- | --- | --- |
| `SHAFA_CHANNEL_IDS` | Каналы из БД/дефолта | ID Telegram-каналов через запятую или пробел |
| `SHAFA_DEBUG_FETCH` | `false` | Вывод статистики получения сообщений из Telegram |
| `SHAFA_DEBUG_FETCH_VERBOSE` | `false` | Подробные причины пропуска Telegram-сообщений |
| `SHAFA_DEBUG_HTTP` | `false` | Вывод превью HTTP-ответов Shafa |
| `SHAFA_VERBOSE_PHOTO_LOGS` | `false` | Подробный лог по каждому фото вместо progress bar |
| `SHAFA_HTTP_RETRIES` | `2` | Количество повторов HTTP-запросов в no-Playwright (`0..5`) |
| `SHAFA_HTTP_RETRY_DELAY` | `2.0` | Базовая задержка между повторами в секундах (`0.1..30`) |
| `SHAFA_DISCUSSION_FALLBACK_LIMIT` | `200` | Лимит fallback-сканирования обсуждений для фото |
| `SHAFA_EXTRA_PHOTOS_WINDOW_MINUTES` | `180` | Временное окно для дополнительных фото из обсуждений |
| `SHAFA_EXTRA_PHOTOS_AGGRESSIVE_LIMIT` | `50` | Лимит агрессивного сканирования дополнительных фото |

## Первый запуск

1. Запустите CLI:

```bash
python main.py
```

2. В разделе `Настройки` выполните:
- `Инициализация проекта` для синхронизации размеров/брендов и сохранения cookies.
- `Войти в аккаунт`, если cookies отсутствуют или устарели.
- `Управление Telegram-каналами` для настройки источников и alias.

3. В разделе `Управление товарами` используйте:
- `Создать товар` для одного цикла загрузки.
- `Автосоздание товара` для периодического режима.

## Обзор CLI-действий

Главное меню содержит две группы:
- `Управление товарами`
- `Настройки`

`Управление товарами` включает:
- создание товара,
- автосоздание с рандомизированным интервалом,
- деактивацию товаров,
- просмотр списка загруженных товаров.

`Настройки` включают:
- инициализацию проекта (размеры/бренды),
- вход через браузер и сохранение cookies,
- управление Telegram-каналами,
- очистку cookies аккаунта,
- выход и возврат товаров в очередь.

## Примечания по режимам

- `with_playwright`: требует запуск браузера и может попросить логин, если cookies отсутствуют.
- `no_playwright`: требует валидные сохраненные cookies, использует прямые HTTP-запросы, может автоматически обновлять размеры и сжимать большие изображения при установленном `Pillow`.

## Данные и локальные файлы

Локально создаются:
- `data/shafa.sqlite3` - SQLite-база данных
- `auth.json` - Playwright storage state
- `session.session` - Telethon session
- `media/` - временные скачанные фотографии

Важные таблицы БД:
- `telegram_products`
- `uploaded_products`
- `telegram_channels`
- `sizes`
- `brands`
- `cookies`

## Запуск тестов

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## Структура проекта

```text
core/         Сценарии работы с Shafa API (с Playwright и без него)
controller/   Получение данных из Telegram, парсинг, сбор фото
data/         Константы, слой SQLite, статические файлы
models/       Dataclass-модели payload'ов товара
utils/        Логирование и вспомогательные функции для медиа
tests/        Unit-тесты для логики парсинга и сбора
main.py       Точка входа интерактивного CLI
```

## Устранение проблем

- `Missing Telegram credentials`: укажите `SHAFA_TELEGRAM_API_ID` и `SHAFA_TELEGRAM_API_HASH` в `.env`.
- `No saved cookies`: запустите `Настройки -> Войти в аккаунт` в `main.py`.
- `Size not resolved`: запустите `Настройки -> Инициализация проекта` для обновления размеров и брендов.
- `Photos skipped due to size`: максимальный размер загрузки 10 MB; установите `Pillow` для сжатия фото в no-Playwright режиме.
