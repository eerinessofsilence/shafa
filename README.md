# Telegram Accounts API

FastAPI backend for managing Telegram accounts stored in `accounts_state.json`, with JSON-based message templates and async Telegram actions via Telethon.

## Features

- `GET /accounts` and `GET /accounts/{account_id}`
- `POST /accounts` and `DELETE /accounts/{account_id}`
- `POST /accounts/{account_id}/start` and `POST /accounts/{account_id}/stop`
- Telegram auth endpoints at `/accounts/{account_id}/auth/telegram/*`
- `GET /accounts/{account_id}/dialogs`
- `GET /accounts/{account_id}/users/{user_ref}`
- `POST /accounts/{account_id}/messages`
- Full CRUD for message templates at `/templates`
- Async JSON-file storage, Pydantic validation, logging, and HTTP error handling

## Project structure

```text
telegram_accounts_api/
├── main.py
├── dependencies.py
├── routers/
├── services/
├── models/
└── utils/
```

## Storage

- Accounts: `accounts_state.json`
- Account session folders: `accounts/<account_id>/`
- Telegram session file: `accounts/<account_id>/telegram.session`
- Telegram API credentials: `accounts/<account_id>/.env`
- Message templates: `message_templates.json`
- Channel templates: `telegram_channel_templates.json`

The API does not create Telegram sessions and does not implement authentication. A valid `telegram.session` file must already exist for Telegram operations.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn telegram_accounts_api.main:app --reload
```

Swagger UI will be available at `http://127.0.0.1:8000/docs`.

## Configuration

Optional environment variables:

- `ACCOUNTS_STATE_FILE` - path to the accounts JSON file
- `MESSAGE_TEMPLATES_FILE` - path to the templates JSON file
- `CHANNEL_TEMPLATES_STATE_FILE` - path to the Telegram channel templates JSON file
- `ACCOUNTS_DIR` - path to the directory with per-account session data
- `TELEGRAM_ACCOUNTS_BASE_DIR` - base directory for fallback paths
- `LOG_LEVEL` - logging level, default `INFO`

Telegram API credentials are loaded from:

1. `accounts/<account_id>/.env`
2. Project root `.env`
3. Process environment variables

Expected keys:

```env
SHAFA_TELEGRAM_API_ID=123456
SHAFA_TELEGRAM_API_HASH=your_api_hash
```

## API overview

### Accounts

- `GET /accounts`
- `GET /accounts/{account_id}`
- `POST /accounts`
- `DELETE /accounts/{account_id}`
- `POST /accounts/{account_id}/start`
- `POST /accounts/{account_id}/stop`

Example create request:

```json
{
  "name": "Account 1",
  "phone": "+380000000000",
  "path": "/home/user/shafa_app/shafa_logic",
  "branch": "main",
  "timer_minutes": 5,
  "channel_links": ["https://t.me/example_channel"]
}
```

`id` при создании передавать не нужно: сервер генерирует его автоматически и возвращает в ответе, а также в `GET /accounts` и `GET /accounts/{account_id}`.

### Templates

- `GET /templates`
- `GET /templates/{template_id}`
- `POST /templates`
- `PUT /templates/{template_id}`
- `DELETE /templates/{template_id}`

Example template:

```json
{
  "name": "promo",
  "content": "Hello {name}, your order is ready.",
  "description": "Generic promo message"
}
```

### Telegram

- `GET /accounts/{account_id}/auth/telegram`
- `POST /accounts/{account_id}/auth/telegram/credentials`
- `POST /accounts/{account_id}/auth/telegram/request-code`
- `POST /accounts/{account_id}/auth/telegram/submit-code`
- `POST /accounts/{account_id}/auth/telegram/submit-password`
- `POST /accounts/{account_id}/auth/telegram/logout`
- `POST /accounts/{account_id}/auth/telegram/copy-session`
- `POST /accounts/{account_id}/messages`
- `GET /accounts/{account_id}/dialogs?limit=20`
- `GET /accounts/{account_id}/users/{user_ref}`

### Channel templates

- `GET /accounts/{account_id}/channel-templates`
- `GET /accounts/{account_id}/channel-templates/{template_name}`
- `POST /accounts/{account_id}/channel-templates`
- `PUT /accounts/{account_id}/channel-templates/{template_name}`
- `DELETE /accounts/{account_id}/channel-templates/{template_name}`

Channel template stores:

- its own `id`
- `account_id`
- user-defined `name`
- raw `links`
- resolved `resolved_channels` items with `channel_id`, `title`, and `alias`

Within one account, template names are unique. Requests for reading, updating, and deleting channel templates now use the template `name` in the URL, while `id` is still returned in API responses as an internal identifier.

Example create request:

```json
{
  "name": "rough",
  "links": ["https://t.me/Fashionista_drop"]
}
```

Example resolved channel item:

```json
{
  "channel_id": -1001160944182,
  "title": "INNA Риночна 1541",
  "alias": "main"
}
```

You can send a direct message with either raw text or a saved template.

Raw text example:

```json
{
  "peer": "@username",
  "text": "Hello from FastAPI"
}
```

Template example:

```json
{
  "peer": "@username",
  "template_id": "promo-template-id",
  "template_variables": {
    "name": "User"
  }
}
```

## curl examples

```bash
curl http://127.0.0.1:8000/health
```

```bash
curl http://127.0.0.1:8000/accounts
```

```bash
curl -X POST http://127.0.0.1:8000/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Account 1",
    "phone": "+380000000000",
    "path": "/home/user/shafa_app/shafa_logic"
  }'
```

```bash
curl -X POST http://127.0.0.1:8000/accounts/acc1/start
```

```bash
curl -X POST http://127.0.0.1:8000/accounts/target-acc/auth/telegram/copy-session \
  -H "Content-Type: application/json" \
  -d '{
    "source_account_id": "source-acc"
  }'
```

```bash
curl -X POST http://127.0.0.1:8000/templates \
  -H "Content-Type: application/json" \
  -d '{
    "name": "promo",
    "content": "Hello {name}, your order is ready."
  }'
```

```bash
curl -X POST http://127.0.0.1:8000/accounts/acc1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "peer": "@username",
    "template_id": "promo-template-id",
    "template_variables": {"name": "User"}
  }'
```

```bash
curl "http://127.0.0.1:8000/accounts/acc1/dialogs?limit=10"
```

```bash
curl http://127.0.0.1:8000/accounts/acc1/users/username
```

```bash
curl -X POST http://127.0.0.1:8000/accounts/acc1/channel-templates \
  -H "Content-Type: application/json" \
  -d '{
    "name": "rough",
    "links": ["https://t.me/Fashionista_drop"]
  }'
```

```bash
curl http://127.0.0.1:8000/accounts/acc1/channel-templates/rough
```

## httpie examples

```bash
http GET :8000/accounts
```

```bash
http POST :8000/templates name=promo content='Hello {name}'
```

```bash
http POST :8000/accounts/acc1/messages peer=@username text='Hello from API'
```

## Notes

- `accounts_state.sample.json` is included as a sample data file.
- Existing `accounts_state.json` data is read as-is; legacy `phone_number` fields are supported.
- Starting and stopping an account updates its status in JSON storage only.
- Telegram endpoints return `400` when the session file or API credentials are missing or invalid.
- Account responses now include `channel_templates` for that account.
- Channel template resolution uses the account's existing Telegram session and does not create a new login.
