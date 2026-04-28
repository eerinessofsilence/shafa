# Shafa Control

Shafa Control is a local desktop-oriented system for managing Telegram accounts and automating product publishing to [shafa.ua](https://shafa.ua).

The repository combines three parts:

- `telegram_accounts_api` - FastAPI backend for accounts, auth, dashboard, templates, logs, and Telegram actions
- `desktop-ui` - Electron + React desktop client that starts the backend automatically
- `shafa_logic` / `shafa_control` - domain logic for Telegram ingestion, Shafa auth/session handling, and product publishing flows

## What the project does

- stores and manages multiple work accounts
- keeps per-account Telegram sessions and Shafa cookies
- supports Telegram authentication flows from the API/UI
- resolves and stores Telegram channel templates per account
- shows dashboard metrics and account logs
- runs local Shafa automation logic for product publishing
- packages the backend and desktop app for Windows distribution

## Repository layout

```text
.
├── telegram_accounts_api/   FastAPI app, routers, services, models, utils
├── desktop-ui/              Electron main process + React/Vite renderer
├── shafa_control/           Account runtime, auth/session helpers, app config
├── shafa_logic/             Shafa automation logic and CLI-oriented flows
├── tests/                   Backend/API test suite
├── requirements/            runtime/test/build Python dependency sets
├── desktop_backend.py       Desktop backend bootstrap entrypoint
├── build_backend.py         PyInstaller build script for backend binary
└── main.py                  Alias entrypoint for `telegram_accounts_api.main:app`
```

## Core architecture

### 1. Backend API

The FastAPI app lives in `telegram_accounts_api/main.py`.

Main route groups:

- `/health`
- `/dashboard/summary`
- `/accounts`
- `/accounts/{account_id}/auth/telegram/*`
- `/accounts/{account_id}/auth/shafa/*`
- `/accounts/{account_id}/channel-templates`
- `/accounts/{account_id}/logs`
- `/templates`
- `/ws/logs/{account_id}`

The backend stores state in local JSON/filesystem storage instead of an external DB.

### 2. Desktop app

The Electron app in `desktop-ui` starts a local backend process on a free `127.0.0.1` port, waits for `/health`, and then loads the React UI.

The desktop UI currently includes:

- dashboard
- accounts management
- auth/session management
- logs view
- settings

### 3. Shafa automation logic

`shafa_logic` contains the lower-level Shafa workflows: Telegram message parsing, photo collection, size/brand sync, and product creation with Playwright or without Playwright.

There is also a dedicated README in [shafa_logic/README.md](/home/slava/shafa_app/shafa_logic/README.md) for details specific to those flows.

## Requirements

### Python

- Python 3.9+
- `pip`
- virtual environment recommended

### Node / desktop UI

- Node.js 18+ recommended
- npm

### Optional but commonly needed

- Playwright Chromium for browser-based Shafa flows
- Windows environment if you want packaged `.exe` builds exactly as configured

## Installation

### Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Dependency sets:

- `requirements.txt` - runtime dependencies
- `requirements/test.txt` - runtime + test/manual UI dependencies
- `requirements/build.txt` - runtime + packaging/build tooling

If you use browser-based Shafa auth or product flows:

```bash
playwright install chromium
```

### Frontend dependencies

```bash
cd desktop-ui
npm install
```

## Running the project

### Option 1. Run the backend API only

```bash
source .venv/bin/activate
uvicorn telegram_accounts_api.main:app --reload
```

API docs:

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

### Option 2. Run the desktop app in development

In one shell, activate the Python environment if needed so Electron can find a working Python interpreter. Then:

```bash
cd desktop-ui
npm run dev
```

This starts:

- Vite dev server
- Electron TypeScript build watcher
- Electron desktop app

The Electron main process launches `desktop_backend.py`, which starts the FastAPI backend automatically.

### Option 3. Run the desktop app from a local production build

```bash
cd desktop-ui
npm run start
```

## Backend storage and runtime data

By default, the backend works with local files.

Primary files/directories:

- `accounts_state.json` - accounts list/state
- `message_templates.json` - reusable text templates
- `telegram_channel_templates.json` - per-account Telegram channel templates
- `accounts/<account_id>/` - per-account directory
- `accounts/<account_id>/telegram.session` - Telethon session
- `accounts/<account_id>/auth.json` - Shafa cookies/storage state
- `accounts/<account_id>/logs/app.log` - persisted account logs

When the desktop app launches the backend, it sets `SHAFA_DESKTOP_DATA_DIR` and stores runtime data under the Electron user data directory:

- `<electron userData>/backend-data/`

So desktop mode does not need to write state back into the repository itself.

## Configuration

### Backend environment variables

Important variables supported by the backend/bootstrap:

| Variable | Purpose |
| --- | --- |
| `TELEGRAM_ACCOUNTS_BASE_DIR` | Base directory for local JSON/files |
| `ACCOUNTS_STATE_FILE` | Path to accounts JSON |
| `MESSAGE_TEMPLATES_FILE` | Path to message templates JSON |
| `CHANNEL_TEMPLATES_STATE_FILE` | Path to channel templates JSON |
| `ACCOUNTS_DIR` | Directory with per-account session data |
| `LOG_LEVEL` | Backend log level |
| `SHAFA_BACKEND_HOST` | Host for desktop backend bootstrap |
| `SHAFA_BACKEND_PORT` | Port for desktop/backend startup |
| `SHAFA_DESKTOP_DATA_DIR` | Data dir used by packaged/dev desktop mode |
| `SHAFA_RUNTIME_PROJECT_DIR` | Runtime copy of `shafa_logic` used by packaged desktop account launches |

### Telegram credentials

Telegram API credentials are resolved from:

1. `accounts/<account_id>/.env`
2. project root `.env`
3. process environment

Expected keys:

```env
SHAFA_TELEGRAM_API_ID=123456
SHAFA_TELEGRAM_API_HASH=your_api_hash
```

### Shafa automation variables

`shafa_logic` supports additional automation-related variables such as fetch debug flags, retry tuning, and channel configuration. See [shafa_logic/README.md](/home/slava/shafa_app/shafa_logic/README.md) and `shafa_logic/.env.example`.

## Main user flows

### Account management

The API/UI can:

- list accounts
- create, update, delete accounts
- start and stop account runtimes
- inspect per-account status and session availability

### Authentication

Supported flows include:

- saving Telegram API credentials
- requesting and submitting Telegram login code
- submitting Telegram 2FA password
- logging out Telegram
- copying or importing Telegram session files
- saving Shafa cookies/storage state
- starting Shafa browser login flow
- logging out Shafa

### Templates and channels

- CRUD for reusable message templates
- CRUD for per-account Telegram channel templates
- resolution of channel links into saved channel metadata

### Monitoring

- dashboard summary by `all`, `week`, `month`, `quarter`, or `custom` range
- account log history endpoint
- websocket log streaming
- log clearing endpoint

## Testing

The test suite is primarily `unittest`-based.

Run commands below from the repository root and with the Python virtual environment activated.

Install test dependencies:

```bash
pip install -r requirements/test.txt
```

Run all root backend tests:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Run `shafa_logic` tests:

```bash
python -m unittest discover -s shafa_logic/tests -p "test_*.py"
```

Notes:

- some suites import optional runtime dependencies such as `fastapi`, `telethon`, and `playwright`
- depending on the current branch state, parts of the legacy/integration-oriented test surface may require additional local setup or may expose existing application regressions

Frontend type checks:

```bash
cd desktop-ui
npm run typecheck
```

## Packaging and builds

### Build backend executable

```bash
pip install -r requirements/build.txt
python build_backend.py
```

This produces a PyInstaller build under:

- `dist/backend/`

### Desktop packaging

From the project root:

```bash
python build_desktop.py
```

This produces a single portable Windows executable that starts the desktop app and launches the bundled backend automatically.

You can also build directly from `desktop-ui/`:

```bash
npm run dist:portable
```

If you also want an installer build:

```bash
cd desktop-ui
npm run dist:installer
```

Useful scripts:

- `npm run build:backend` - triggers backend build helper for desktop packaging
- `npm run build` - renderer + Electron production build
- `python build_desktop.py` - root-level helper to build one portable Windows `.exe`
- `npm run dist:portable` - single portable Windows `.exe` for end users
- `npm run dist:installer` - Windows installer build only
- `npm run pack:win` - unpacked Windows app
- `npm run dist:win` - alias for the portable one-file Windows build

### Desktop development

From the project root:

```bash
python run_desktop.py
```

This starts the full desktop app in development mode by running `npm run dev` inside `desktop-ui/`.
You do not need to start `dist/backend/ShafaControlBackend.exe` separately for local desktop development.

## Notes for contributors

- prefer `rg`/`rg --files` for codebase search
- avoid committing real sessions, cookies, or secrets
- the working tree may contain generated runtime JSON files; check carefully before committing
- desktop mode and API-only mode use the same backend code, so backend changes should be verified in both contexts when relevant

## Troubleshooting

### Backend starts but desktop app cannot connect

- check that `/health` responds on the port printed by `desktop_backend.py`
- make sure another process is not blocking localhost access

### Telegram actions fail immediately

- verify `SHAFA_TELEGRAM_API_ID` and `SHAFA_TELEGRAM_API_HASH`
- verify the account has a valid `telegram.session`

### Shafa actions fail

- verify the account has valid Shafa cookies/storage state in `auth.json`
- install Playwright Chromium if the flow opens a browser

### Desktop backend uses unexpected data directory

- check `SHAFA_DESKTOP_DATA_DIR`
- in packaged/dev Electron mode, data is intentionally redirected into Electron user data
