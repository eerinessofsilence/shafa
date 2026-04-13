from __future__ import annotations

import time
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread
from PySide6.QtGui import QColor, QFont, QPalette, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QInputDialog,
    QPushButton,
    QListWidget,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from account_store import AccountStore
from shafa_control import (
    Account,
    AccountSessionStore,
    LogRecord,
    LogStore,
    ShafaAuthService,
    TelegramAuthService,
)
from telegram_channels import export_runtime_config, sanitize_channel_links

APP_NAME = "Shafa Control"
BRANCHES = ["main", "clothes-feature"]
BASE_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "accounts_state.json"
RUNTIME_DIR = BASE_DIR / "runtime"
ACCOUNTS_DIR = BASE_DIR / "accounts"
DEFAULT_PROJECT_DIR = BASE_DIR / "shafa"


class Worker(QObject):
    log = Signal(str)
    status = Signal(int, str)
    finished = Signal(int, bool, str)

    def __init__(self, row: int, account_path: str, branch: str) -> None:
        super().__init__()
        self.row = row
        self.account_path = Path(account_path)
        self.branch = branch
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def _run_cmd(self, cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
        self.log.emit(f"$ {' '.join(cmd)}")
        return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)

    def _git_current_commit(self) -> str:
        result = self._run_cmd(["git", "rev-parse", "HEAD"], self.account_path)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git rev-parse HEAD failed")
        return result.stdout.strip()

    def _git_remote_commit(self) -> str:
        result = self._run_cmd(["git", "fetch", "origin", self.branch], self.account_path)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git fetch failed")

        remote_ref = f"origin/{self.branch}"
        result = self._run_cmd(["git", "rev-parse", remote_ref], self.account_path)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"git rev-parse {remote_ref} failed")
        return result.stdout.strip()

    def _switch_to_branch(self) -> None:
        """Switch to the target branch, handling local changes and branch creation"""
        # First, fetch latest changes to ensure we have all branches
        self.log.emit(f"[{self.row}] Fetching latest changes...")
        fetch = self._run_cmd(["git", "fetch", "--all"], self.account_path)
        if fetch.returncode != 0:
            self.log.emit(f"[{self.row}] Warning: git fetch failed: {fetch.stderr.strip()}")

        # Check if branch exists
        branch_check = self._run_cmd(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{self.branch}"], self.account_path)
        if branch_check.returncode != 0:
            # Try remote branch
            remote_branch_check = self._run_cmd(["git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{self.branch}"], self.account_path)
            if remote_branch_check.returncode != 0:
                raise RuntimeError(f"Branch '{self.branch}' does not exist locally or remotely")
            # Create local branch tracking remote
            self.log.emit(f"[{self.row}] Creating local branch {self.branch}...")
            create_branch = self._run_cmd(["git", "checkout", "-b", self.branch, f"origin/{self.branch}"], self.account_path)
            if create_branch.returncode != 0:
                raise RuntimeError(f"Failed to create local branch {self.branch}: {create_branch.stderr.strip()}")
            self.log.emit(f"[{self.row}] Local branch {self.branch} created")
        else:
            # Check for local changes and stash them if needed
            status = self._run_cmd(["git", "status", "--porcelain"], self.account_path)
            has_changes = bool(status.stdout.strip())
            self.log.emit(f"[{self.row}] Git status result: {status.stdout.strip()[:100]}... has_changes={has_changes}")
            
            if has_changes:
                self.log.emit(f"[{self.row}] Stashing local changes...")
                stash = self._run_cmd(["git", "stash", "push", "--include-untracked", "-m", "auto-stash-before-branch-switch"], self.account_path)
                if stash.returncode != 0:
                    self.log.emit(f"[{self.row}] Stash failed: {stash.stderr.strip()}")
                    raise RuntimeError(stash.stderr.strip() or stash.stdout.strip() or "git stash failed")
                self.log.emit(f"[{self.row}] Stash successful")

            checkout = self._run_cmd(["git", "checkout", self.branch], self.account_path)
            if checkout.returncode != 0:
                self.log.emit(f"[{self.row}] Checkout failed: {checkout.stderr.strip()}")
                # If checkout failed and we stashed changes, we need to restore them
                if has_changes:
                    self.log.emit(f"[{self.row}] Restoring stashed changes...")
                    pop = self._run_cmd(["git", "stash", "pop"], self.account_path)
                    if pop.returncode != 0:
                        self.log.emit(f"[{self.row}] Failed to restore stash: {pop.stderr.strip()}")
                raise RuntimeError(checkout.stderr.strip() or checkout.stdout.strip() or "git checkout failed")

            # Restore stashed changes after successful checkout
            if has_changes:
                self.log.emit(f"[{self.row}] Restoring local changes...")
                pop = self._run_cmd(["git", "stash", "pop"], self.account_path)
                if pop.returncode != 0:
                    self.log.emit(f"[{self.row}] Warning: failed to restore stashed changes: {pop.stderr.strip()}")
                else:
                    self.log.emit(f"[{self.row}] Stashed changes restored")

    def run(self) -> None:
        try:
            if not self.account_path.exists():
                raise FileNotFoundError(f"Path not found: {self.account_path}")

            self.status.emit(self.row, "checking")
            self.log.emit(f"[{self.row}] Checking branch {self.branch} for updates...")

            # Check current branch
            current_branch_cmd = self._run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], self.account_path)
            if current_branch_cmd.returncode == 0:
                current_branch = current_branch_cmd.stdout.strip()
                self.log.emit(f"[{self.row}] Current branch: {current_branch}, target branch: {self.branch}")
                if current_branch == self.branch:
                    self.log.emit(f"[{self.row}] Already on branch {self.branch}, skipping checkout")
                else:
                    # Need to switch branch
                    self._switch_to_branch()
            else:
                self.log.emit(f"[{self.row}] Failed to get current branch, proceeding with checkout")
                self._switch_to_branch()

            local_commit = self._git_current_commit()
            remote_commit = self._git_remote_commit()
            repo_changed = local_commit != remote_commit
            self.log.emit(f"[{self.row}] local={local_commit[:7]} remote={remote_commit[:7]} changed={repo_changed}")

            if repo_changed:
                self.status.emit(self.row, "updating")
                pull = self._run_cmd(["git", "pull", "--ff-only"], self.account_path)
                if pull.returncode != 0:
                    raise RuntimeError(pull.stderr.strip() or pull.stdout.strip() or "git pull failed")
            else:
                self.log.emit(f"[{self.row}] No git changes detected, skipping pull and venv rebuild")

            if self._stop_requested:
                raise RuntimeError("Stopped by user")

            venv_dir = self.account_path / ".venv"
            need_recreate_venv = repo_changed or not venv_dir.exists()

            if need_recreate_venv:
                self.status.emit(self.row, "creating venv")
                if venv_dir.exists():
                    self.log.emit(f"[{self.row}] Removing existing .venv...")
                    shutil.rmtree(venv_dir)

                self.log.emit(f"[{self.row}] Creating .venv...")
                venv_result = self._run_cmd([sys.executable, "-m", "venv", ".venv"], self.account_path)
                if venv_result.returncode != 0:
                    raise RuntimeError(venv_result.stderr.strip() or venv_result.stdout.strip() or "venv creation failed")

                if os.name == "nt":
                    py_bin = venv_dir / "Scripts" / "python.exe"
                    pip_bin = venv_dir / "Scripts" / "pip.exe"
                else:
                    py_bin = venv_dir / "bin" / "python"
                    pip_bin = venv_dir / "bin" / "pip"

                if not py_bin.exists() or not pip_bin.exists():
                    raise FileNotFoundError("Python or pip not found inside .venv")

                requirements = self.account_path / "requirements.txt"
                if requirements.exists():
                    self.status.emit(self.row, "installing deps")
                    self.log.emit(f"[{self.row}] Installing dependencies...")
                    pip_result = self._run_cmd([str(pip_bin), "install", "-r", "requirements.txt"], self.account_path)
                    if pip_result.returncode != 0:
                        raise RuntimeError(pip_result.stderr.strip() or pip_result.stdout.strip() or "pip install failed")
                else:
                    self.log.emit(f"[{self.row}] requirements.txt not found, skipping install")
            else:
                if os.name == "nt":
                    py_bin = venv_dir / "Scripts" / "python.exe"
                else:
                    py_bin = venv_dir / "bin" / "python"
                if not py_bin.exists():
                    raise FileNotFoundError(f"Missing python in existing venv: {py_bin}")

            if self._stop_requested:
                raise RuntimeError("Stopped by user")

            self.status.emit(self.row, "ready")
            self.finished.emit(self.row, True, str(py_bin))
        except Exception as exc:
            self.finished.emit(self.row, False, str(exc))


class StatCard(QFrame):
    def __init__(self, title: str, value: str, subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("StatCard")
        self.setGraphicsEffect(_make_shadow())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)

        self.title = QLabel(title)
        self.title.setObjectName("CardTitle")
        self.value = QLabel(value)
        self.value.setObjectName("CardValue")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("MutedLabel")

        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.subtitle)
        layout.addStretch()

    def set_value(self, value: str) -> None:
        self.value.setText(value)


class DashboardPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Общий контроль проекта и быстрый доступ к метрикам")
        subtitle.setObjectName("MutedLabel")
        root.addWidget(title)
        root.addWidget(subtitle)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.total_accounts = StatCard("Аккаунты", "0", "всего")
        self.active_accounts = StatCard("Активные", "0", "запущено")
        self.items_found = StatCard("Товары", "0", "собрано")
        self.errors_today = StatCard("Ошибки", "0", "за сегодня")
        for card in [self.total_accounts, self.active_accounts, self.items_found, self.errors_today]:
            stats.addWidget(card)
        root.addLayout(stats)

        middle = QHBoxLayout()
        middle.setSpacing(14)

        left = QFrame()
        left.setObjectName("PanelCard")
        left.setGraphicsEffect(_make_shadow())
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.addWidget(QLabel("Активность"))
        activity = QFrame()
        activity.setObjectName("ChartPlaceholder")
        activity.setMinimumHeight(240)
        left_layout.addWidget(activity)

        right = QFrame()
        right.setObjectName("PanelCard")
        right.setGraphicsEffect(_make_shadow())
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.addWidget(QLabel("Состояние системы"))
        self.system_status = QLabel("Работает")
        self.system_status.setObjectName("StatusGood")
        self.last_run = QLabel("Последний запуск: —")
        self.last_run.setObjectName("MutedLabel")
        self.queue_state = QLabel("Очередь: 0 задач")
        self.queue_state.setObjectName("MutedLabel")
        right_layout.addWidget(self.system_status)
        right_layout.addWidget(self.last_run)
        right_layout.addWidget(self.queue_state)
        right_layout.addStretch()

        middle.addWidget(left, 2)
        middle.addWidget(right, 1)
        root.addLayout(middle)
        root.addStretch()


class AccountsPage(QWidget):
    selection_changed = Signal(int)
    log = Signal(str)
    run_requested = Signal(list)
    stop_requested = Signal(list)
    delete_requested = Signal(list)
    accounts_changed = Signal()
    shafa_auth_requested = Signal(int)
    shafa_session_delete_requested = Signal(int)
    telegram_code_requested = Signal(int)
    telegram_login_requested = Signal(int, str)
    telegram_session_clone_requested = Signal(int)
    telegram_session_export_requested = Signal(int)
    telegram_session_import_requested = Signal(int)
    telegram_session_delete_requested = Signal(int)

    def __init__(self, accounts: List[Account]) -> None:
        super().__init__()
        self.accounts = accounts

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        title = QLabel("Аккаунты")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Выбор ветки, браузера и таймера для каждого аккаунта")
        subtitle.setObjectName("MutedLabel")
        root.addWidget(title)
        root.addWidget(subtitle)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.select_all = QCheckBox("Выбрать все")
        self.select_all.setCursor(Qt.PointingHandCursor)
        self.add_btn = QPushButton("Добавить")
        self.delete_btn = QPushButton("Удалить")
        self.run_btn = QPushButton("Запустить")
        self.stop_btn = QPushButton("Остановить")
        toolbar.addWidget(self.select_all)
        toolbar.addStretch()
        for btn in [self.add_btn, self.delete_btn, self.run_btn, self.stop_btn]:
            btn.setCursor(Qt.PointingHandCursor)
            toolbar.addWidget(btn)
        root.addLayout(toolbar)

        content = QHBoxLayout()
        content.setSpacing(16)

        table_panel = QFrame()
        table_panel.setObjectName("PanelCard")
        table_panel.setGraphicsEffect(_make_shadow())
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(16, 16, 16, 16)

        self.table = QTableWidget(0, 9)
        self.table.setObjectName("DataTable")
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setHorizontalHeaderLabels(
            ["", "Имя", "Проект", "Ветка", "Браузер", "Таймер", "Каналы", "Статус", "Ошибки"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._load_selected_to_form)
        self.table.itemChanged.connect(self._handle_item_changed)
        self.table.setColumnWidth(0, 36)
        table_layout.addWidget(self.table)

        config_panel = QFrame()
        config_panel.setObjectName("PanelCard")
        config_panel.setGraphicsEffect(_make_shadow())
        config_panel.setFixedWidth(380)
        config_layout = QVBoxLayout(config_panel)
        config_layout.setContentsMargins(16, 16, 16, 16)
        config_layout.setSpacing(12)

        config_title = QLabel("Конфигурация аккаунта")
        config_title.setObjectName("FieldLabel")
        self.selected_account_label = QLabel("Выберите аккаунт")
        self.selected_account_label.setObjectName("MutedLabel")
        config_layout.addWidget(config_title)
        config_layout.addWidget(self.selected_account_label)

        self.branch_combo = QComboBox()
        self.branch_combo.addItems(BRANCHES)
        self.branch_combo.setMinimumWidth(180)

        self.project_path_edit = QLineEdit()
        self.project_path_edit.setReadOnly(True)
        self.project_path_edit.setPlaceholderText("Выберите корень проекта Shafa Soft")
        self.project_browse_btn = QPushButton("Выбрать проект")
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("+380...")
        self.telegram_code_input = QLineEdit()
        self.telegram_code_input.setPlaceholderText("Код подтверждения")

        self.browser_toggle = QCheckBox("Открывать с браузером")
        self.browser_toggle.setCursor(Qt.PointingHandCursor)
        self.browser_state = QLabel("Нет")
        self.browser_state.setObjectName("ToggleStateOff")
        self.browser_toggle.stateChanged.connect(self._sync_browser_state)

        self.timer_spin = QSpinBox()
        self.timer_spin.setRange(1, 120)
        self.timer_spin.setSuffix(" мин")

        config_layout.addWidget(QLabel("Корень проекта"))
        config_layout.addWidget(self.project_path_edit)
        config_layout.addWidget(self.project_browse_btn)
        config_layout.addWidget(QLabel("Ветка"))
        config_layout.addWidget(self.branch_combo)
        config_layout.addWidget(self.browser_toggle)
        config_layout.addWidget(self.browser_state)
        config_layout.addWidget(QLabel("Таймер"))
        config_layout.addWidget(self.timer_spin)

        channels_label = QLabel("Telegram-каналы")
        channels_label.setObjectName("FieldLabel")
        config_layout.addWidget(channels_label)

        self.channel_links = QListWidget()
        self.channel_links.setMinimumHeight(180)
        config_layout.addWidget(self.channel_links)

        self.channel_input = QLineEdit()
        self.channel_input.setPlaceholderText("https://t.me/example_channel")
        config_layout.addWidget(self.channel_input)

        channel_actions = QHBoxLayout()
        self.add_channel_btn = QPushButton("Добавить ссылку")
        self.remove_channel_btn = QPushButton("Удалить ссылку")
        channel_actions.addWidget(self.add_channel_btn)
        channel_actions.addWidget(self.remove_channel_btn)
        config_layout.addLayout(channel_actions)

        self.apply_btn = QPushButton("Сохранить аккаунт")
        self.apply_btn.setObjectName("PrimaryButton")
        self.apply_btn.setCursor(Qt.PointingHandCursor)
        self.shafa_auth_btn = QPushButton("Войти в Shafa")
        self.telegram_auth_btn = QPushButton("Запросить код Telegram")
        self.telegram_login_btn = QPushButton("Подтвердить TG сессию")
        self.clone_session_btn = QPushButton("Копировать TG сессию")
        self.export_tg_session_btn = QPushButton("Экспортировать TG сессию")
        self.import_tg_session_btn = QPushButton("Импортировать TG сессию")
        self.delete_tg_session_btn = QPushButton("Удалить TG сессию")
        self.delete_shafa_session_btn = QPushButton("Удалить Shafa сессию")
        self.shafa_auth_status = QLabel("Shafa auth: отсутствует")
        self.shafa_auth_status.setObjectName("MutedLabel")
        self.telegram_auth_status = QLabel("Telegram session: отсутствует")
        self.telegram_auth_status.setObjectName("MutedLabel")
        config_layout.addWidget(self.apply_btn)
        config_layout.addWidget(QLabel("Телефон Telegram"))
        config_layout.addWidget(self.phone_input)
        config_layout.addWidget(QLabel("Код Telegram"))
        config_layout.addWidget(self.telegram_code_input)
        config_layout.addWidget(self.shafa_auth_btn)
        config_layout.addWidget(self.delete_shafa_session_btn)
        config_layout.addWidget(self.telegram_auth_btn)
        config_layout.addWidget(self.telegram_login_btn)
        config_layout.addWidget(self.clone_session_btn)
        config_layout.addWidget(self.export_tg_session_btn)
        config_layout.addWidget(self.import_tg_session_btn)
        config_layout.addWidget(self.delete_tg_session_btn)
        config_layout.addWidget(self.shafa_auth_status)
        config_layout.addWidget(self.telegram_auth_status)
        config_layout.addStretch()

        content.addWidget(table_panel, 1)
        config_scroll = QScrollArea()
        config_scroll.setWidgetResizable(True)
        config_scroll.setFrameShape(QFrame.NoFrame)
        config_scroll.setMinimumWidth(420)
        config_scroll.setWidget(config_panel)
        content.addWidget(config_scroll)
        root.addLayout(content)

        self.add_btn.clicked.connect(self.add_account)
        self.delete_btn.clicked.connect(self.delete_selected_accounts)
        self.run_btn.clicked.connect(self._run_selected)
        self.stop_btn.clicked.connect(self._stop_selected)
        self.apply_btn.clicked.connect(self.apply_settings)
        self.add_channel_btn.clicked.connect(self.add_channel_link)
        self.remove_channel_btn.clicked.connect(self.remove_selected_channel_link)
        self.project_browse_btn.clicked.connect(self.select_project_directory)
        self.phone_input.textChanged.connect(self._sync_telegram_button_state)
        self.telegram_code_input.textChanged.connect(self._sync_telegram_button_state)
        self.shafa_auth_btn.clicked.connect(self._request_shafa_auth)
        self.delete_shafa_session_btn.clicked.connect(self._request_delete_shafa_session)
        self.telegram_auth_btn.clicked.connect(self._request_telegram_code)
        self.telegram_login_btn.clicked.connect(self._request_telegram_login)
        self.clone_session_btn.clicked.connect(self._request_clone_session)
        self.export_tg_session_btn.clicked.connect(self._request_export_session)
        self.import_tg_session_btn.clicked.connect(self._request_import_session)
        self.delete_tg_session_btn.clicked.connect(self._request_delete_tg_session)
        self.select_all.stateChanged.connect(self._toggle_all)

        self.refresh()

    def _sync_browser_state(self) -> None:
        enabled = self.browser_toggle.isChecked()
        self.browser_state.setText("Да" if enabled else "Нет")
        self.browser_state.setObjectName("ToggleStateOn" if enabled else "ToggleStateOff")
        self.browser_state.style().unpolish(self.browser_state)
        self.browser_state.style().polish(self.browser_state)
        self.browser_state.update()

    def _toggle_all(self, state: int) -> None:
        checked = state == Qt.Checked
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.table.blockSignals(False)

    def _handle_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        checked_count = 0
        for row in range(self.table.rowCount()):
            row_item = self.table.item(row, 0)
            if row_item is not None and row_item.checkState() == Qt.Checked:
                checked_count += 1
        self.select_all.blockSignals(True)
        self.select_all.setChecked(checked_count > 0 and checked_count == self.table.rowCount())
        self.select_all.blockSignals(False)

    def refresh(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for acc in self.accounts:
            row = self.table.rowCount()
            self.table.insertRow(row)

            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            check_item.setCheckState(Qt.Unchecked)
            self.table.setItem(row, 0, check_item)

            data = [
                acc.name,
                acc.path,
                acc.branch,
                "Да" if acc.open_browser else "Нет",
                str(acc.timer_minutes),
                str(len(acc.channel_links)),
                acc.status,
                str(acc.errors),
            ]
            for col, value in enumerate(data, start=1):
                item = QTableWidgetItem(value)
                self.table.setItem(row, col, item)
            self._paint_status(row, acc.status)
        self.table.blockSignals(False)

    def _paint_status(self, row: int, status: str) -> None:
        item = self.table.item(row, 7)
        if not item:
            return
        if status == "running":
            item.setForeground(QColor("#8be28b"))
        elif status == "error":
            item.setForeground(QColor("#ff9a9a"))
        elif status in {"checking", "updating", "creating venv", "installing deps", "ready"}:
            item.setForeground(QColor("#ffd36b"))
        else:
            item.setForeground(QColor("#a7b0bf"))

    def selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def selected_account(self) -> Optional[Account]:
        row = self.selected_row()
        if row < 0 or row >= len(self.accounts):
            return None
        return self.accounts[row]

    def checked_rows(self) -> List[int]:
        rows: List[int] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.checkState() == Qt.Checked:
                rows.append(row)
        return rows

    def _load_selected_to_form(self) -> None:
        acc = self.selected_account()
        if not acc:
            self.selected_account_label.setText("Выберите аккаунт")
            self.project_path_edit.clear()
            self.phone_input.clear()
            self.telegram_code_input.clear()
            self.channel_links.clear()
            self.update_auth_status(False, False, False)
            self._sync_telegram_button_state()
            return
        self.selected_account_label.setText(acc.name)
        self.project_path_edit.setText(acc.path)
        self.phone_input.setText(acc.phone_number)
        self.telegram_code_input.clear()
        self.branch_combo.setCurrentText(acc.branch)
        self.browser_toggle.setChecked(acc.open_browser)
        self.timer_spin.setValue(acc.timer_minutes)
        self.channel_input.clear()
        self.channel_links.clear()
        self.channel_links.addItems(acc.channel_links)
        self._sync_browser_state()
        self._sync_telegram_button_state()
        self.selection_changed.emit(self.selected_row())

    def apply_settings(self) -> None:
        acc = self.selected_account()
        if not acc:
            QMessageBox.information(self, "Настройки", "Выберите аккаунт в таблице.")
            return
        acc.branch = self.branch_combo.currentText()
        acc.path = self.project_path_edit.text().strip() or acc.path
        acc.phone_number = self.phone_input.text().strip()
        acc.open_browser = self.browser_toggle.isChecked()
        acc.timer_minutes = int(self.timer_spin.value())
        acc.channel_links = sanitize_channel_links(
            self.channel_links.item(index).text()
            for index in range(self.channel_links.count())
        )
        self.refresh()
        self._select_account(acc)
        self.log.emit(
            f"[SETTINGS] {acc.name}: project={acc.path}, branch={acc.branch}, "
            f"browser={acc.open_browser}, timer={acc.timer_minutes}m, channels={len(acc.channel_links)}"
        )
        self.accounts_changed.emit()

    def add_account(self) -> None:
        name, ok = QInputDialog.getText(self, "Новый аккаунт", "Название аккаунта")
        if not ok:
            return
        clean_name = name.strip() or f"Account {len(self.accounts) + 1}"
        default_path = str(DEFAULT_PROJECT_DIR if DEFAULT_PROJECT_DIR.exists() else BASE_DIR)
        self.accounts.append(Account(id=uuid.uuid4().hex, name=clean_name, path=default_path))
        self.refresh()
        self._select_row(len(self.accounts) - 1)
        self.log.emit(f"[ADD] Added account: {clean_name}")
        self.accounts_changed.emit()

    def delete_selected_accounts(self) -> None:
        rows = self.checked_rows()
        if not rows:
            row = self.selected_row()
            if row < 0:
                QMessageBox.information(self, "Удаление", "Выберите аккаунт или отметьте несколько чекбоксами.")
                return
            rows = [row]
        self.delete_requested.emit(rows)

    def _run_selected(self) -> None:
        rows = self.checked_rows()
        if not rows:
            row = self.selected_row()
            if row < 0:
                QMessageBox.information(self, "Запуск", "Выберите аккаунт в таблице.")
                return
            rows = [row]
        self.run_requested.emit(rows)

    def _stop_selected(self) -> None:
        rows = self.checked_rows()
        if not rows:
            row = self.selected_row()
            if row < 0:
                QMessageBox.information(self, "Остановка", "Выберите аккаунт в таблице.")
                return
            rows = [row]
        self.stop_requested.emit(rows)

    def select_project_directory(self) -> None:
        acc = self.selected_account()
        if not acc:
            QMessageBox.information(self, "Проект", "Сначала выберите аккаунт.")
            return
        path = QFileDialog.getExistingDirectory(
            self,
            "Выберите корень проекта Shafa Soft",
            self.project_path_edit.text().strip() or acc.path,
        )
        if not path:
            return
        self.project_path_edit.setText(path)
        self.apply_settings()

    def add_channel_link(self) -> None:
        acc = self.selected_account()
        if not acc:
            QMessageBox.information(self, "Telegram-каналы", "Сначала выберите аккаунт.")
            return
        raw_link = self.channel_input.text().strip()
        if not raw_link:
            QMessageBox.information(self, "Telegram-каналы", "Введите ссылку на канал.")
            return
        try:
            link = sanitize_channel_links([raw_link])[0]
        except (IndexError, ValueError) as exc:
            QMessageBox.warning(self, "Telegram-каналы", str(exc))
            return
        existing = {self.channel_links.item(i).text().casefold() for i in range(self.channel_links.count())}
        if link.casefold() in existing:
            self.channel_input.clear()
            return
        self.channel_links.addItem(link)
        self.channel_input.clear()
        self.apply_settings()

    def remove_selected_channel_link(self) -> None:
        acc = self.selected_account()
        if not acc:
            QMessageBox.information(self, "Telegram-каналы", "Сначала выберите аккаунт.")
            return
        current_row = self.channel_links.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "Telegram-каналы", "Выберите ссылку для удаления.")
            return
        self.channel_links.takeItem(current_row)
        self.apply_settings()

    def _select_account(self, account: Account) -> None:
        for row, current in enumerate(self.accounts):
            if current is account:
                self._select_row(row)
                return

    def _select_row(self, row: int) -> None:
        if row < 0 or row >= self.table.rowCount():
            return
        self.table.selectRow(row)

    def update_auth_status(self, shafa_ready: bool, telegram_ready: bool, telegram_pending: bool) -> None:
        self.shafa_auth_status.setText(
            "Shafa auth: готово" if shafa_ready else "Shafa auth: отсутствует"
        )
        if telegram_ready:
            telegram_text = "Telegram session: готово"
        elif telegram_pending:
            telegram_text = "Telegram session: ожидает код"
        else:
            telegram_text = "Telegram session: отсутствует"
        self.telegram_auth_status.setText(telegram_text)

    def _sync_telegram_button_state(self) -> None:
        has_phone = bool(self.phone_input.text().strip())
        self.telegram_auth_btn.setEnabled(has_phone)
        self.telegram_login_btn.setEnabled(has_phone and bool(self.telegram_code_input.text().strip()))

    def _request_shafa_auth(self) -> None:
        row = self.selected_row()
        if row < 0:
            QMessageBox.information(self, "Shafa auth", "Сначала выберите аккаунт.")
            return
        self.apply_settings()
        self.shafa_auth_requested.emit(row)

    def _request_delete_shafa_session(self) -> None:
        row = self.selected_row()
        if row < 0:
            QMessageBox.information(self, "Shafa session", "Сначала выберите аккаунт.")
            return
        self.shafa_session_delete_requested.emit(row)

    def _request_telegram_code(self) -> None:
        row = self.selected_row()
        if row < 0:
            QMessageBox.information(self, "Telegram auth", "Сначала выберите аккаунт.")
            return
        if not self.phone_input.text().strip():
            QMessageBox.information(self, "Telegram auth", "Заполните номер телефона.")
            return
        self.apply_settings()
        self.telegram_code_requested.emit(row)

    def _request_telegram_login(self) -> None:
        row = self.selected_row()
        if row < 0:
            QMessageBox.information(self, "Telegram auth", "Сначала выберите аккаунт.")
            return
        code = self.telegram_code_input.text().strip()
        if not code:
            QMessageBox.information(self, "Telegram auth", "Введите код подтверждения.")
            return
        self.apply_settings()
        self.telegram_login_requested.emit(row, code)

    def _request_clone_session(self) -> None:
        row = self.selected_row()
        if row < 0:
            QMessageBox.information(self, "Telegram session", "Сначала выберите аккаунт.")
            return
        self.telegram_session_clone_requested.emit(row)

    def _request_delete_tg_session(self) -> None:
        row = self.selected_row()
        if row < 0:
            QMessageBox.information(self, "Telegram session", "Сначала выберите аккаунт.")
            return
        self.telegram_session_delete_requested.emit(row)

    def _request_import_session(self) -> None:
        row = self.selected_row()
        if row < 0:
            QMessageBox.information(self, "Telegram session", "Сначала выберите аккаунт.")
            return
        self.telegram_session_import_requested.emit(row)

    def _request_export_session(self) -> None:
        row = self.selected_row()
        if row < 0:
            QMessageBox.information(self, "Telegram session", "Сначала выберите аккаунт.")
            return
        self.telegram_session_export_requested.emit(row)


class ParsingPage(QWidget):
    def __init__(self, log_sink) -> None:
        super().__init__()
        self.log_sink = log_sink
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        title = QLabel("Парсинг")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Настройки сбора данных и быстрый запуск задачи")
        subtitle.setObjectName("MutedLabel")
        root.addWidget(title)
        root.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("PanelCard")
        card.setGraphicsEffect(_make_shadow())
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        form = QVBoxLayout()
        self.category = QComboBox()
        self.category.addItems(["Женская одежда", "Мужская одежда", "Обувь", "Аксессуары"])
        self.pages = QLineEdit("10")
        self.delay = QLineEdit("2.5")

        for text, widget in [("Категория", self.category), ("Страниц", self.pages), ("Задержка, сек", self.delay)]:
            box = QVBoxLayout()
            label = QLabel(text)
            label.setObjectName("FieldLabel")
            box.addWidget(label)
            box.addWidget(widget)
            form.addLayout(box)

        flags = QVBoxLayout()
        self.use_proxy = QCheckBox("Использовать прокси")
        self.random_delay = QCheckBox("Случайная задержка")
        self.save_raw = QCheckBox("Сохранять raw JSON")
        self.use_proxy.setChecked(True)
        self.random_delay.setChecked(True)
        for cb in [self.use_proxy, self.random_delay, self.save_raw]:
            flags.addWidget(cb)
        flags.addStretch()

        controls = QVBoxLayout()
        start = QPushButton("Старт")
        stop = QPushButton("Стоп")
        start.setObjectName("PrimaryButton")
        stop.setObjectName("DangerButton")
        start.clicked.connect(lambda: self.log_sink("[PARSER] start requested"))
        stop.clicked.connect(lambda: self.log_sink("[PARSER] stop requested"))
        controls.addWidget(start)
        controls.addWidget(stop)
        controls.addStretch()

        layout.addLayout(form, 2)
        layout.addLayout(flags, 1)
        layout.addLayout(controls, 1)
        root.addWidget(card)

        result = QFrame()
        result.setObjectName("PanelCard")
        result.setGraphicsEffect(_make_shadow())
        r_layout = QVBoxLayout(result)
        r_layout.setContentsMargins(16, 16, 16, 16)
        r_layout.addWidget(QLabel("Результаты"))
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Здесь будет список найденных товаров, статусы и ошибки...")
        r_layout.addWidget(self.output)
        root.addWidget(result)
        root.addStretch()


class TrendChart(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ChartPlaceholder")
        self.history: list[tuple[datetime, int, int]] = []
        self.max_points = 1000
        
        # Добавляем селектор периода
        self.period_selector = QComboBox()
        self.period_selector.addItems(["1 час", "6 часов", "1 день", "1 неделя", "Все время"])
        self.period_selector.setCurrentText("Все время")  # По умолчанию показываем все данные
        self.period_selector.currentTextChanged.connect(self._on_period_changed)
        
        # Создаём отдельный виджет для рисования графика
        self.chart_widget = ChartWidget(self)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.period_selector, alignment=Qt.AlignTop | Qt.AlignRight)
        layout.addWidget(self.chart_widget, 1)
        
        self.load_history()

    def _on_period_changed(self) -> None:
        """Обработчик изменения периода"""
        self.chart_widget.repaint()
        self.update()

    def add_data_point(self, items: int, errors: int) -> None:
        print(f"[DEBUG] Adding data point: items={items}, errors={errors}")
        self.history.append((datetime.now(), items, errors))
        week_ago = datetime.now() - timedelta(days=7)
        self.history = [(ts, i, e) for ts, i, e in self.history if ts > week_ago]
        self.chart_widget.repaint()
        self.update()
        print(f"[DEBUG] History now has {len(self.history)} points")

    def save_history(self) -> None:
        """Сохраняет историю в файл"""
        try:
            history_file = BASE_DIR / "chart_history.json"
            data = [
                {
                    "timestamp": ts.isoformat(),
                    "items": items,
                    "errors": errors
                }
                for ts, items, errors in self.history
            ]
            history_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[ERROR] Failed to save chart history: {e}")

    def load_history(self) -> None:
        """Загружает историю из файла"""
        try:
            history_file = BASE_DIR / "chart_history.json"
            if history_file.exists():
                data = json.loads(history_file.read_text(encoding="utf-8"))
                week_ago = datetime.now() - timedelta(days=7)
                self.history = [
                    (datetime.fromisoformat(item["timestamp"]), item["items"], item["errors"])
                    for item in data
                    if datetime.fromisoformat(item["timestamp"]) > week_ago
                ]
                print(f"[DEBUG] Loaded {len(self.history)} history points")
                self.chart_widget.repaint()  # Обновляем виджет после загрузки
                self.update()
        except Exception as e:
            print(f"[ERROR] Failed to load chart history: {e}")
            self.history = []

    def _smooth_data(self, data: list[tuple[datetime, int, int]]) -> list[tuple[datetime, int, int]]:
        """Сглаживает данные, группируя по временным интервалам"""
        if len(data) <= 20:
            return data
            
        period = self.period_selector.currentText()
        if period == "1 час":
            interval_minutes = 5
        elif period == "6 часов":
            interval_minutes = 30
        elif period == "1 день":
            interval_minutes = 60
        elif period == "1 неделя":
            interval_minutes = 360
        else:
            return data
            
        smoothed = []
        current_group = []
        current_time = data[0][0]
        
        for ts, items, errors in data:
            if (ts - current_time).total_seconds() / 60 < interval_minutes:
                current_group.append((ts, items, errors))
            else:
                if current_group:
                    avg_items = sum(i for _, i, _ in current_group) // len(current_group)
                    avg_errors = sum(e for _, _, e in current_group) // len(current_group)
                    smoothed.append((current_time, avg_items, avg_errors))
                current_group = [(ts, items, errors)]
                current_time = ts
                
        if current_group:
            avg_items = sum(i for _, i, _ in current_group) // len(current_group)
            avg_errors = sum(e for _, _, e in current_group) // len(current_group)
            smoothed.append((current_time, avg_items, avg_errors))
            
        return smoothed

    def get_filtered_data(self) -> list[tuple[datetime, int, int]]:
        """Возвращает данные за выбранный период"""
        now = datetime.now()
        period = self.period_selector.currentText()
        
        if period == "1 час":
            cutoff = now - timedelta(hours=1)
        elif period == "6 часов":
            cutoff = now - timedelta(hours=6)
        elif period == "1 день":
            cutoff = now - timedelta(days=1)
        elif period == "1 неделя":
            cutoff = now - timedelta(days=7)
        else:  # Все время
            cutoff = datetime.min
            
        return [(ts, items, errors) for ts, items, errors in self.history if ts > cutoff]




class ChartWidget(QWidget):
    """Отдельный виджет для рисования графика"""
    def __init__(self, parent_chart: TrendChart) -> None:
        super().__init__()
        self.parent_chart = parent_chart
        self.setMinimumHeight(200)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.contentsRect().adjusted(12, 12, -12, -12)
        painter.fillRect(rect, QColor("#11161f"))

        data = self.parent_chart.get_filtered_data()
        if not data:
            painter.setPen(QPen(QColor("#cbd5e1")))
            painter.drawText(rect, Qt.AlignCenter, "Нет данных")
            return

        smoothed_data = self.parent_chart._smooth_data(data)
        
        values = [items for _, items, _ in smoothed_data] + [errors for _, _, errors in smoothed_data]
        max_value = max(values) if values else 1
        max_value = max(max_value, 1)

        pen_axis = QPen(QColor("#445166"))
        painter.setPen(pen_axis)
        painter.drawLine(rect.bottomLeft(), rect.topLeft())
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        point_count = len(smoothed_data)
        if point_count < 1:
            return

        def point_at(index: int, value: int) -> tuple[int, int]:
            x = rect.left() + (rect.width() - 1) * index / max(point_count - 1, 1)
            y = rect.bottom() - (rect.height() - 1) * value / max_value
            return int(x), int(y)

        success_pen = QPen(QColor("#4ade80"), 2)
        error_pen = QPen(QColor("#f87171"), 2)

        painter.setPen(success_pen)
        prev = None
        for i, (_, items, _) in enumerate(smoothed_data):
            pt = point_at(i, items)
            if prev:
                painter.drawLine(prev[0], prev[1], pt[0], pt[1])
            painter.drawEllipse(pt[0] - 2, pt[1] - 2, 4, 4)
            prev = pt

        painter.setPen(error_pen)
        prev = None
        for i, (_, _, errors) in enumerate(smoothed_data):
            pt = point_at(i, errors)
            if prev:
                painter.drawLine(prev[0], prev[1], pt[0], pt[1])
            painter.drawEllipse(pt[0] - 2, pt[1] - 2, 4, 4)
            prev = pt

        painter.setPen(QPen(QColor("#cbd5e1"), 1, Qt.DotLine))
        for step in range(1, 4):
            y = rect.bottom() - step * rect.height() / 4
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))

        if smoothed_data:
            painter.setPen(QPen(QColor("#f8fafc")))
            painter.drawText(rect.left() + 6, rect.top() + 18, f"Items: {smoothed_data[-1][1]}")
            painter.drawText(rect.left() + 6, rect.top() + 36, f"Errors: {smoothed_data[-1][2]}")


class StatsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        title = QLabel("Статистика")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Метрики по аккаунтам, скорости и ошибкам")
        subtitle.setObjectName("MutedLabel")
        root.addWidget(title)
        root.addWidget(subtitle)

        cards = QHBoxLayout()
        cards.setSpacing(14)
        self.card_speed = StatCard("Скорость", "0/min", "средняя")
        self.card_total = StatCard("Обработано", "0", "за всё время")
        self.card_bans = StatCard("Баны", "0", "константа")
        self.card_timeouts = StatCard("Таймауты", "0", "константа")
        for card in [self.card_speed, self.card_total, self.card_bans, self.card_timeouts]:
            cards.addWidget(card)
        root.addLayout(cards)

        panel = QFrame()
        panel.setObjectName("PanelCard")
        panel.setGraphicsEffect(_make_shadow())
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(QLabel("Графики и тренды"))
        self.chart = TrendChart()
        self.chart.setMinimumHeight(280)
        layout.addWidget(self.chart)
        root.addWidget(panel)
        root.addStretch()

    def update_stats(self, speed: float, total: int, errors: int, bans: int = 0, timeouts: int = 0) -> None:
        self.card_speed.set_value(f"{speed:.1f}/min")
        self.card_total.set_value(str(total))
        self.card_bans.set_value(str(bans))
        self.card_timeouts.set_value(str(timeouts))


class LogsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        title = QLabel("Логи")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Живая лента событий и ошибок")
        subtitle.setObjectName("MutedLabel")
        root.addWidget(title)
        root.addWidget(subtitle)

        filters = QHBoxLayout()
        self.account_filter = QComboBox()
        self.account_filter.addItem("Все аккаунты", None)
        self.level = QComboBox()
        self.level.addItem("Все", "ALL")
        self.level.addItem("Ошибки", "ERROR")
        self.level.addItem("Успех", "SUCCESS")
        self.level.addItem("Инфо", "INFO")
        filters.addWidget(self.account_filter)
        filters.addWidget(self.level)
        root.addLayout(filters)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(500)
        root.addWidget(self.output)

    def set_accounts(self, accounts: list[Account]) -> None:
        current_id = self.account_filter.currentData()
        self.account_filter.blockSignals(True)
        self.account_filter.clear()
        self.account_filter.addItem("Все аккаунты", None)
        for account in accounts:
            self.account_filter.addItem(account.name, account.id)
        index = self.account_filter.findData(current_id)
        self.account_filter.setCurrentIndex(max(index, 0))
        self.account_filter.blockSignals(False)

    def render_records(self, records: list[LogRecord]) -> None:
        self.output.setPlainText("\n".join(record.render() for record in records))

    def selected_account_id(self) -> str | None:
        return self.account_filter.currentData()

    def selected_level(self) -> str:
        return self.level.currentData() or "ALL"


class SettingsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        title = QLabel("Настройки")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Прокси, пути сохранения, тема и общие параметры")
        subtitle.setObjectName("MutedLabel")
        root.addWidget(title)
        root.addWidget(subtitle)

        panel = QFrame()
        panel.setObjectName("PanelCard")
        panel.setGraphicsEffect(_make_shadow())
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        for label_text, default in [
            ("Папка сохранения", "/home/user/shafa/data"),
            ("Файл прокси", "/home/user/shafa/proxy.txt"),
            ("Интервал обновления, сек", "30"),
        ]:
            box = QVBoxLayout()
            lab = QLabel(label_text)
            lab.setObjectName("FieldLabel")
            edit = QLineEdit(default)
            box.addWidget(lab)
            box.addWidget(edit)
            layout.addLayout(box)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Тема"))
        combo = QComboBox()
        combo.addItems(["Dark", "Light"])
        theme_row.addWidget(combo)
        theme_row.addStretch()
        layout.addLayout(theme_row)

        save = QPushButton("Сохранить настройки")
        save.setObjectName("PrimaryButton")
        layout.addWidget(save, alignment=Qt.AlignLeft)

        root.addWidget(panel)
        root.addStretch()


def _make_shadow() -> QGraphicsDropShadowEffect:
    # Упрощённая версия без shadow для диагностики
    return QGraphicsDropShadowEffect()


class MainWindow(QMainWindow):
    DEBUG_PROCESS = False  # Toggle console logging here
    background_log_signal = Signal(str, object)
    telegram_auth_finalize_signal = Signal(int, object)

    def __init__(self) -> None:
        try:
            super().__init__()
            self.setWindowTitle(APP_NAME)
            self.resize(1440, 900)

            self.account_store = AccountStore(STATE_FILE, Account.from_json)
            self.session_store = AccountSessionStore(BASE_DIR, ACCOUNTS_DIR, STATE_FILE)
            self.accounts: List[Account] = self._load_accounts()
            self.log_store = LogStore(RUNTIME_DIR / "logs")
            self.shafa_auth_service = ShafaAuthService(self.session_store)
            self.telegram_auth_service = TelegramAuthService(self.session_store, self._run_account_command)
            self.workers: dict[int, Worker] = {}
            self.threads: dict[int, QThread] = {}
            self.process_log_threads: dict[int, threading.Thread] = {}
            self.telegram_auth_processes: dict[int, subprocess.Popen] = {}
            self.telegram_auth_states: dict[int, str] = {}
            self.session_started = datetime.now()
            self.success_count = 0
            self.product_count = 0
            self.error_count = 0
            self.last_log_ts: Optional[datetime] = None
            self.prev_product_count = 0
            self.prev_error_count = 0

            self._setup_palette()
            self.background_log_signal.connect(self.log)
            self.telegram_auth_finalize_signal.connect(self._finalize_telegram_auth_process)
            self._build_ui()
            self.stop_all_accounts()
            self._apply_styles()
            self._setup_timer()
            self._refresh_all()
        except Exception as e:
            print(f"[ERROR] MainWindow init failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            raise

    def _load_accounts(self) -> List[Account]:
        try:
            return self.account_store.load()
        except Exception:
            return []

    def _save_accounts(self) -> None:
        try:
            self.account_store.save(self.accounts)
            self.logs_page.set_accounts(self.accounts)
        except Exception as exc:
            self.log(f"[ERROR] Failed to save accounts state: {exc}")

    def closeEvent(self, event) -> None:
        # Останавливаем все аккаунты перед закрытием
        self.stop_all_accounts()
            
        # Ждём завершения процессов
        time.sleep(2)
        
        # Сохраняем состояние всех аккаунтов как stopped
        for acc in self.accounts:
            acc.status = "stopped"
            acc.process = None
            
        self.stats_page.chart.save_history()  # Сохраняем историю графика
        self._save_accounts()
        super().closeEvent(event)

    def _setup_palette(self) -> None:
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#0d1117"))
        pal.setColor(QPalette.Base, QColor("#141824"))
        pal.setColor(QPalette.AlternateBase, QColor("#101521"))
        self.setPalette(pal)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(270)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(16, 16, 16, 16)
        side.setSpacing(12)

        brand = QFrame()
        b = QVBoxLayout(brand)
        b.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Shafa Control")
        title.setObjectName("BrandTitle")
        subtitle = QLabel("Production UI")
        subtitle.setObjectName("MutedLabel")
        b.addWidget(title)
        b.addWidget(subtitle)
        side.addWidget(brand)

        user = QFrame()
        user.setObjectName("PanelCard")
        user.setGraphicsEffect(_make_shadow())
        u = QHBoxLayout(user)
        u.setContentsMargins(12, 12, 12, 12)
        avatar = QLabel("SN")
        avatar.setObjectName("Avatar")
        avatar.setAlignment(Qt.AlignCenter)
        info = QVBoxLayout()
        info.addWidget(QLabel("Святослав Непейцев"))
        role = QLabel("Admin")
        role.setObjectName("MutedLabel")
        info.addWidget(role)
        u.addWidget(avatar)
        u.addLayout(info)
        side.addWidget(user)

        self.nav_buttons: list[QPushButton] = []
        nav_items = ["Dashboard", "Аккаунты", "Парсинг", "Статистика", "Логи", "Настройки"]
        for index, text in enumerate(nav_items):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, i=index: self._set_page(i))
            self.nav_buttons.append(btn)
            side.addWidget(btn)

        side.addStretch()

        actions = QFrame()
        a = QVBoxLayout(actions)
        a.setContentsMargins(0, 0, 0, 0)
        export_btn = QPushButton("Экспорт отчёта")
        export_btn.setObjectName("ActionButton")
        export_btn.clicked.connect(lambda: self.log("[UI] export requested"))
        quit_btn = QPushButton("Выход")
        quit_btn.setObjectName("DangerButton")
        quit_btn.clicked.connect(self.close)
        a.addWidget(export_btn)
        a.addWidget(quit_btn)
        side.addWidget(actions)

        self.pages = QStackedWidget()
        self.pages.setObjectName("Pages")
        self.dashboard_page = DashboardPage()
        self.accounts_page = AccountsPage(self.accounts)
        self.parsing_page = ParsingPage(self.log)
        self.stats_page = StatsPage()
        self.logs_page = LogsPage()
        self.settings_page = SettingsPage()

        self.pages.addWidget(self.dashboard_page)
        self.pages.addWidget(self.accounts_page)
        self.pages.addWidget(self.parsing_page)
        self.pages.addWidget(self.stats_page)
        self.pages.addWidget(self.logs_page)
        self.pages.addWidget(self.settings_page)

        self.accounts_page.log.connect(self.log)
        self.accounts_page.selection_changed.connect(self._sync_dashboard)
        self.accounts_page.selection_changed.connect(self._sync_account_auth_status)
        self.accounts_page.delete_requested.connect(self.delete_accounts)
        self.accounts_page.run_requested.connect(self.run_accounts)
        self.accounts_page.stop_requested.connect(self.stop_accounts)
        self.accounts_page.accounts_changed.connect(self._save_accounts)
        self.accounts_page.shafa_auth_requested.connect(self.authenticate_shafa_account)
        self.accounts_page.shafa_session_delete_requested.connect(self.delete_shafa_session)
        self.accounts_page.telegram_code_requested.connect(self.request_telegram_code)
        self.accounts_page.telegram_login_requested.connect(self.complete_telegram_login)
        self.accounts_page.telegram_session_clone_requested.connect(self.clone_telegram_session)
        self.accounts_page.telegram_session_export_requested.connect(self.export_telegram_session)
        self.accounts_page.telegram_session_import_requested.connect(self.import_telegram_session)
        self.accounts_page.telegram_session_delete_requested.connect(self.delete_telegram_session)
        self.logs_page.account_filter.currentIndexChanged.connect(self._refresh_logs)
        self.logs_page.level.currentIndexChanged.connect(self._refresh_logs)

        root.addWidget(self.sidebar)
        root.addWidget(self.pages, 1)

        self.logs_page.set_accounts(self.accounts)
        self._set_page(0)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            * {
                font-family: Arial, sans-serif;
                font-size: 14px;
                color: #e5e7eb;
            }
            QMainWindow, QWidget { background: #0d1117; }
            #Sidebar {
                background: #11151d;
                border: 1px solid #242c38;
                border-radius: 10px;
            }
            #BrandTitle { font-size: 22px; font-weight: bold; color: #f8fafc; }
            #PageTitle { font-size: 28px; font-weight: bold; color: #f8fafc; }
            #MutedLabel { color: #98a2b3; }
            #FieldLabel { color: #cbd5e1; font-weight: bold; }
            #StatCard, #PanelCard {
                background: #141924;
                border: 1px solid #262f3c;
                border-radius: 10px;
            }
            #CardTitle { color: #cbd5e1; }
            #CardValue { font-size: 28px; font-weight: bold; color: #f8fafc; }
            #StatusGood { color: #4ade80; font-weight: bold; }
            QPushButton {
                padding: 10px 12px;
                border-radius: 6px;
                border: 1px solid #2d3745;
                background: #151b24;
                color: #e5e7eb;
                font-weight: bold;
            }
            QPushButton:hover { background: #1b2230; }
            QPushButton#PrimaryButton { background: #2563eb; border: none; }
            QPushButton#PrimaryButton:hover { background: #1d4ed8; }
            QPushButton#DangerButton { background: #7f1d1d; border: 1px solid #991b1b; color: #fca5a5; }
            QPushButton#DangerButton:hover { background: #991b1b; }
            QLineEdit, QComboBox, QTextEdit, QTableWidget, QSpinBox {
                background: #11161f;
                border: 1px solid #263241;
                border-radius: 6px;
                padding: 8px;
            }
            QTableWidget {
                alternate-background-color: #141b26;
                selection-background-color: rgba(37, 99, 235, 0.28);
            }
            QHeaderView::section {
                background: #11161f;
                color: #cbd5e1;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #263241;
                font-weight: bold;
            }
            """
        )

    def _setup_timer(self) -> None:
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_stats)
        self.timer.start(3000)

    def _refresh_stats(self) -> None:
        total = len(self.accounts)
        active = sum(1 for a in self.accounts if a.status == "running")
        elapsed_min = max((datetime.now() - self.session_started).total_seconds() / 60.0, 1 / 60)
        speed = self.success_count / elapsed_min
        self.dashboard_page.total_accounts.set_value(str(total))
        self.dashboard_page.active_accounts.set_value(str(active))
        self.dashboard_page.items_found.set_value(str(self.product_count))
        self.dashboard_page.errors_today.set_value(str(self.error_count))
        self.dashboard_page.queue_state.setText(f"Очередь: {active} запущено")
        self.dashboard_page.last_run.setText(f"Последний запуск: {self._last_run_text()}")
        self.stats_page.update_stats(speed=speed, total=self.product_count, errors=self.error_count, bans=0, timeouts=0)
        
        # Добавляем точку в график только если значения изменились
        if self.product_count != self.prev_product_count or self.error_count != self.prev_error_count:
            self.stats_page.chart.add_data_point(self.product_count, self.error_count)
            self.prev_product_count = self.product_count
            self.prev_error_count = self.error_count

    def _last_run_text(self) -> str:
        runs = [a.last_run for a in self.accounts if a.last_run != "—"]
        return max(runs) if runs else "—"

    def log(self, text: str, account: Optional[Account] = None) -> None:
        record = LogRecord(
            timestamp=datetime.now(),
            message=text,
            level=LogStore.detect_level(text),
            account_id=account.id if account else None,
            account_name=account.name if account else None,
        )
        account_log = self.session_store.account_log_file(account) if account else None
        self.log_store.append(record, account_log_file=account_log)
        self._refresh_logs()
        self.last_log_ts = datetime.now()
        lower = text.lower()
        is_error = any(token in lower for token in ["[error]", "error", "не удалось", "ошибка"])
        is_success = any(token in lower for token in ["[ok]", "успеш", "success"]) and not is_error
        is_product = lower.startswith("saved") or any(token in lower for token in ["[OK]", "успешно"])

        if is_success:
            self.success_count += 1
        if is_error:
            self.error_count += 1
        if is_product and not is_error:
            self.product_count += 1
            if self.DEBUG_PROCESS:
                print(f"[DEBUG] Product count incremented to {self.product_count} for: {text}")

        # Обновляем график при обнаружении продукта или ошибки
        if is_product or is_error:
            self._refresh_stats()

    def _refresh_logs(self) -> None:
        self.logs_page.render_records(
            self.log_store.filtered(
                account_id=self.logs_page.selected_account_id(),
                level=self.logs_page.selected_level(),
            )
        )

    def _set_page(self, index: int) -> None:
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        self.pages.setCurrentIndex(index)
        if index == 4:
            self.log("Открыта страница логов")

    def _sync_dashboard(self, _row: int) -> None:
        self._refresh_stats()

    def _sync_account_auth_status(self, row: int) -> None:
        if row < 0 or row >= len(self.accounts):
            self.accounts_page.update_auth_status(False, False, False)
            return
        account = self.accounts[row]
        self.accounts_page.update_auth_status(
            shafa_ready=self.session_store.is_valid_shafa_session(account),
            telegram_ready=self.session_store.is_valid_telegram_session(account),
            telegram_pending=self.session_store.has_pending_telegram_code(account),
        )

    def delete_accounts(self, rows: List[int]) -> None:
        rows = sorted(set(rows), reverse=True)
        if not rows:
            return
        for row in rows:
            if 0 <= row < len(self.accounts):
                acc = self.accounts[row]
                proc = acc.process
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=3)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                self.session_store.delete_account_data(acc)
                del self.accounts[row]
        self.accounts_page.refresh()
        self._refresh_stats()
        self._save_accounts()
        self._sync_account_auth_status(self.accounts_page.selected_row())
        self.log(f"[DELETE] Removed {len(rows)} account(s)")

    def run_accounts(self, rows: List[int]) -> None:
        for row in rows:
            self.run_account(row)

    def _read_process_output(self, row: int, proc: subprocess.Popen, account_name: str) -> None:
        try:
            account = self._account_by_row(row)
            if proc.stdout is None:
                if self.DEBUG_PROCESS:
                    print(f"[DEBUG] proc.stdout is None for {account_name}")
                return
            
            if self.DEBUG_PROCESS:
                print(f"[DEBUG] Starting to read output from {account_name} (pid={proc.pid})")
            
            line_count = 0
            for raw_line in proc.stdout:
                line = raw_line.rstrip("\n")
                if not line:
                    continue
                line_count += 1
                if self.DEBUG_PROCESS and line_count <= 5:  # Показываем первые 5 строк
                    print(f"[PROC:{account_name}] {line}")
                self.background_log_signal.emit(line, account)
            
            if self.DEBUG_PROCESS:
                print(f"[DEBUG] Finished reading output from {account_name}, total lines: {line_count}")
                if proc.poll() is not None:
                    print(f"[DEBUG] Process {account_name} exited with code {proc.returncode}")
                    
        except Exception as exc:
            if self.DEBUG_PROCESS:
                print(f"[PROC:ERROR] log reader failed for {account_name}: {exc}")
            self.background_log_signal.emit(f"[ERROR] log reader failed for {account_name}: {exc}", account)

    # def _run_bootstrap(self, py_bin: str, account_path: Path, account_name: str) -> None:
    #     self.log(f"[BOOTSTRAP] {account_name}: bootstrap.py")
    #     result = subprocess.run(
    #         [py_bin, "bootstrap.py"],
    #         cwd=str(account_path),
    #         capture_output=True,
    #         text=True,
    #     )
    #     if result.stdout:
    #        for line in result.stdout.splitlines():
    #            self.log(f"[{account_name}] {line}")
    #     if result.returncode != 0:
    #         err = (result.stderr or result.stdout or "bootstrap failed").strip()
    #        raise RuntimeError(err)

    def run_account(self, row: int) -> None:
        if row < 0 or row >= len(self.accounts):
            return
        acc = self.accounts[row]

        if acc.process is not None and acc.process.poll() is None:
            if self.DEBUG_PROCESS:
                print(f"[DEBUG] {acc.name} already running")
            self.log("[RUN] already running", account=acc)
            return
        if self._account_auth_file(acc).exists() and not self.session_store.is_valid_shafa_session(acc):
            self.log("[ERROR] Shafa session is corrupted. Re-login is required.", account=acc)
            return
        if self._account_telegram_session_file(acc).exists() and not self.session_store.is_valid_telegram_session(acc):
            self.log("[ERROR] Telegram session is corrupted. Re-authentication is required.", account=acc)
            return

        if self.DEBUG_PROCESS:
            print(f"[DEBUG] Starting {acc.name} on branch {acc.branch}")
        self.log(f"[RUN] Starting on branch {acc.branch}", account=acc)
        worker = Worker(row, acc.path, acc.branch)
        thread = QThread(self)
        worker.moveToThread(thread)

        def on_status(r: int, status: str) -> None:
            if 0 <= r < len(self.accounts):
                self.accounts[r].status = status
                self.accounts_page.refresh()
                self._refresh_stats()

        def on_finished(r: int, ok: bool, info: str) -> None:
            if 0 <= r < len(self.accounts):
                account = self.accounts[r]
                if ok:
                    py_bin = info
                    try:
                        env = self._account_env(account)
                        channels_file = export_runtime_config(
                            account_name=account.name,
                            account_path=account.path,
                            links=account.channel_links,
                            output_dir=self._account_state_dir(account),
                        )
                        env["SHAFA_TELEGRAM_CHANNEL_LINKS_FILE"] = str(channels_file)

                        # bootstrap.py first, then main.py
                        # self._run_bootstrap(py_bin, Path(account.path), account.name)

                        # Проверяем, что main.py существует
                        main_py_path = Path(account.path) / "main.py"
                        if not main_py_path.exists():
                            raise FileNotFoundError(f"main.py not found at {main_py_path}")

                        if self.DEBUG_PROCESS:
                            print(f"[DEBUG] main.py found at {main_py_path}")
                            print(f"[DEBUG] Creating Popen for {account.name}: {py_bin} main.py")
                        proc = subprocess.Popen(
                            [py_bin, "main.py", "--shafa"],
                            cwd=account.path,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=0,
                            env=env,
                        )
                        if self.DEBUG_PROCESS:
                            print(f"[DEBUG] Popen created, pid={proc.pid}")
                        
                        # Проверяем, что процесс действительно запустился
                        time.sleep(0.1)  # Даём процессу время запуститься
                        if proc.poll() is not None:
                            # Процесс уже завершился
                            stdout, stderr = proc.communicate()
                            if self.DEBUG_PROCESS:
                                print(f"[DEBUG] Process exited immediately with code {proc.returncode}")
                                if stdout:
                                    print(f"[DEBUG] stdout: {stdout}")
                                if stderr:
                                    print(f"[DEBUG] stderr: {stderr}")
                            raise RuntimeError(f"main.py exited immediately with code {proc.returncode}: {stdout or stderr}")
                        
                        if self.DEBUG_PROCESS:
                            print(f"[DEBUG] Process is running, starting log thread")
                        
                        # Добавляем проверку статуса процесса через 5 секунд
                        def check_process_status():
                            time.sleep(5)
                            if proc.poll() is not None:
                                if self.DEBUG_PROCESS:
                                    print(f"[DEBUG] Process {account.name} (pid={proc.pid}) exited with code {proc.returncode}")
                                    # Пытаемся прочитать оставшийся вывод
                                    try:
                                        remaining = proc.stdout.read()
                                        if remaining:
                                            print(f"[DEBUG] Remaining output: {remaining}")
                                    except:
                                        pass
                            else:
                                if self.DEBUG_PROCESS:
                                    print(f"[DEBUG] Process {account.name} (pid={proc.pid}) still running after 5 seconds")
                        
                        status_thread = threading.Thread(target=check_process_status, daemon=True)
                        status_thread.start()
                        account.process = proc
                        account.status = "running"
                        account.last_run = datetime.now().strftime("%Y-%m-%d %H:%M")

                        log_thread = threading.Thread(
                            target=self._read_process_output,
                            args=(r, proc, account.name),
                            daemon=True,
                        )
                        log_thread.start()
                        self.process_log_threads[r] = log_thread

                        if proc.stdin is not None:
                            browser_answer = "y" if account.open_browser else "n"
                            timer_answer = str(account.timer_minutes)
                            proc.stdin.write(f"{browser_answer}\n{timer_answer}\n")
                            proc.stdin.flush()
                            proc.stdin.close()
                            self.log(
                                f"[OK] started on {account.branch} with browser={browser_answer}, timer={timer_answer}m (pid={proc.pid})",
                                account=account,
                            )
                            if account.channel_links:
                                self.log(
                                    f"[CHANNELS] exported {len(account.channel_links)} link(s) to {channels_file.name}",
                                    account=account,
                                )
                        else:
                            self.log(f"[OK] started on {account.branch} (pid={proc.pid})", account=account)
                    except Exception as exc:
                        account.status = "error"
                        account.errors += 1
                        self.log(f"[ERROR] Failed to start {account.name}: {exc}", account=account)
                else:
                    account.status = "error"
                    account.errors += 1
                    self.log(f"[ERROR] {info}", account=account)
                self.accounts_page.refresh()
                self._refresh_stats()
                self._sync_account_auth_status(r)

            thread.quit()
            worker.deleteLater()
            thread.finished.connect(thread.deleteLater)
            self.workers.pop(r, None)
            self.threads.pop(r, None)
            self._save_accounts()

        worker.log.connect(self.log)
        worker.status.connect(on_status)
        worker.finished.connect(on_finished)
        thread.started.connect(worker.run)

        self.workers[row] = worker
        self.threads[row] = thread
        thread.start()

    def stop_accounts(self, rows: List[int]) -> None:
        for row in rows:
            self.stop_account(row)

    def stop_all_accounts(self) -> None:
        """Останавливает все аккаунты"""
        running_rows = [i for i, acc in enumerate(self.accounts) if acc.status == "running"]
        if running_rows:
            self.log("[STOP] Stopping all accounts...")
            self.stop_accounts(running_rows)

    def stop_account(self, row: int) -> None:
        if row < 0 or row >= len(self.accounts):
            return
        acc = self.accounts[row]
        self.log(f"[STOP] Stopping {acc.name}", account=acc)

        if row in self.workers:
            self.workers[row].request_stop()

        proc = acc.process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
                self.log(f"[STOP] Process terminated", account=acc)
            except Exception:
                try:
                    proc.kill()
                    self.log(f"[STOP] Process killed", account=acc)
                except Exception as exc:
                    self.log(f"[ERROR] stop failed: {exc}", account=acc)
        acc.process = None
        acc.status = "stopped"
        self.accounts_page.refresh()
        self._refresh_stats()
        self._save_accounts()

    def authenticate_shafa_account(self, row: int) -> None:
        account = self._account_by_row(row)
        if account is None:
            return
        env, context = self.shafa_auth_service.create_login_context(account, self._account_env(account))
        proc = subprocess.Popen(
            [self._account_python(account), "main.py", "--login-shafa"],
            cwd=account.path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            env=env,
        )
        prompt = QMessageBox(self)
        prompt.setWindowTitle("Shafa auth")
        prompt.setText("Выполните вход в открывшемся окне Shafa, затем нажмите OK для сохранения сессии.")
        prompt.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        choice = prompt.exec()
        if choice != QMessageBox.Ok:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
            self.shafa_auth_service.cancel_login(context)
            self.log("[AUTH] Shafa auth cancelled", account=account)
            self._sync_account_auth_status(row)
            return

        self.shafa_auth_service.confirm_login(context)
        try:
            output, _ = proc.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate()
        self.shafa_auth_service.clear_context(context)
        if proc.returncode == 0 and self.session_store.is_valid_shafa_session(account):
            self.log("[AUTH] Shafa auth saved", account=account)
        else:
            message = output.strip() or f"exit code {proc.returncode}"
            self.log(f"[ERROR] Shafa auth failed: {message}", account=account)
        self._save_accounts()
        self._sync_account_auth_status(row)

    def request_telegram_code(self, row: int) -> None:
        account = self._account_by_row(row)
        if account is None:
            return
        phone = account.phone_number.strip()
        if not phone:
            self.log("[ERROR] Telegram auth requires phone number.", account=account)
            return
        existing = self.telegram_auth_processes.get(row)
        if existing and existing.poll() is None:
            self.log("[AUTH] Telegram auth already in progress", account=account)
            return
        proc = subprocess.Popen(
            [self._account_python(account), *self.telegram_auth_service.interactive_command()],
            cwd=account.path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=self._account_env(account),
        )
        self.telegram_auth_processes[row] = proc
        self.telegram_auth_states[row] = "starting"
        threading.Thread(
            target=self._read_telegram_auth_output,
            args=(row, proc, account),
            daemon=True,
        ).start()
        self.log("[AUTH] Telegram session start", account=account)
        self._save_accounts()
        self._sync_account_auth_status(row)

    def complete_telegram_login(self, row: int, code: str) -> None:
        account = self._account_by_row(row)
        if account is None:
            return
        proc = self.telegram_auth_processes.get(row)
        if proc is None or proc.poll() is not None:
            self.log("[ERROR] Telegram auth process is not running.", account=account)
            return
        if self.telegram_auth_states.get(row) != "awaiting_code":
            self.log("[ERROR] Telegram code cannot be sent before code request.", account=account)
            return
        if proc.stdin is None:
            self.log("[ERROR] Telegram auth input channel is unavailable.", account=account)
            return
        proc.stdin.write(f"{code.strip()}\n")
        proc.stdin.flush()
        self.telegram_auth_states[row] = "verifying_code"
        self.accounts_page.telegram_code_input.clear()
        self.log("[AUTH] Telegram code input received", account=account)

    def clone_telegram_session(self, row: int) -> None:
        target_account = self._account_by_row(row)
        if target_account is None:
            return
        sources = [
            account
            for index, account in enumerate(self.accounts)
            if index != row and self.session_store.is_valid_telegram_session(account)
        ]
        if not sources:
            QMessageBox.information(self, "Telegram session", "Нет доступных аккаунтов с Telegram сессией.")
            return
        labels = [source.name for source in sources]
        source_name, ok = QInputDialog.getItem(
            self,
            "Копировать Telegram сессию",
            "Источник сессии",
            labels,
            0,
            False,
        )
        if not ok or not source_name:
            return
        source_account = next(account for account in sources if account.name == source_name)
        self.telegram_auth_service.copy_session(source_account, target_account)
        self._save_accounts()
        self.log(f"[AUTH] Telegram session copied from {source_account.name}", account=target_account)
        self._sync_account_auth_status(row)

    def import_telegram_session(self, row: int) -> None:
        account = self._account_by_row(row)
        if account is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Импортировать TG сессию",
            str(BASE_DIR),
            "Telegram Session (*.session);;All Files (*)",
        )
        if not path:
            return
        try:
            self.telegram_auth_service.import_session(account, Path(path))
        except Exception as exc:
            self.log(f"[ERROR] Telegram session import failed: {exc}", account=account)
            return
        self._save_accounts()
        self.log("[AUTH] Telegram session imported", account=account)
        self._sync_account_auth_status(row)

    def export_telegram_session(self, row: int) -> None:
        account = self._account_by_row(row)
        if account is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспортировать TG сессию",
            str(BASE_DIR / f"{account.name}.session"),
            "Telegram Session (*.session)",
        )
        if not path:
            return
        try:
            self.telegram_auth_service.export_session(account, Path(path))
        except Exception as exc:
            self.log(f"[ERROR] Telegram session export failed: {exc}", account=account)
            return
        self.log(f"[AUTH] Telegram session exported to {Path(path).name}", account=account)

    def delete_telegram_session(self, row: int) -> None:
        account = self._account_by_row(row)
        if account is None:
            return
        if QMessageBox.question(
            self,
            "Удалить TG сессию",
            f"Удалить Telegram сессию для {account.name}?",
        ) != QMessageBox.Yes:
            return
        self.session_store.delete_telegram_session(account)
        self._save_accounts()
        self.log("[AUTH] Telegram session deleted", account=account)
        self._sync_account_auth_status(row)

    def delete_shafa_session(self, row: int) -> None:
        account = self._account_by_row(row)
        if account is None:
            return
        if QMessageBox.question(
            self,
            "Удалить Shafa сессию",
            f"Удалить Shafa сессию для {account.name}?",
        ) != QMessageBox.Yes:
            return
        self.session_store.delete_shafa_session(account)
        self._save_accounts()
        self.log("[AUTH] Shafa session deleted", account=account)
        self._sync_account_auth_status(row)

    def _account_by_row(self, row: int) -> Optional[Account]:
        if row < 0 or row >= len(self.accounts):
            return None
        return self.accounts[row]

    def _account_state_dir(self, account: Account) -> Path:
        return self.session_store.account_dir(account)

    def _account_auth_file(self, account: Account) -> Path:
        return self.session_store.auth_file(account)

    def _account_db_file(self, account: Account) -> Path:
        return self.session_store.db_file(account)

    def _account_telegram_session_file(self, account: Account) -> Path:
        return self.session_store.telegram_session_file(account)

    def _account_telegram_login_state_file(self, account: Account) -> Path:
        return self.session_store.telegram_login_state_file(account)

    def _account_channels_file(self, account: Account) -> Path:
        return self.session_store.channels_file(account)

    def _account_env(self, account: Account) -> dict[str, str]:
        env = os.environ.copy()
        state_dir = self._account_state_dir(account)
        env.setdefault("PYTHONUNBUFFERED", "1")
        env["SHAFA_ACCOUNT_STATE_DIR"] = str(state_dir)
        env["SHAFA_STORAGE_STATE_PATH"] = str(self._account_auth_file(account))
        env["SHAFA_DB_PATH"] = str(self._account_db_file(account))
        env["SHAFA_TELEGRAM_SESSION_PATH"] = str(self._account_telegram_session_file(account))
        env["SHAFA_TELEGRAM_LOGIN_STATE_PATH"] = str(self._account_telegram_login_state_file(account))
        env["SHAFA_TELEGRAM_CHANNELS_PATH"] = str(self._account_channels_file(account))
        return env

    def _account_python(self, account: Account) -> str:
        if os.name == "nt":
            candidate = Path(account.path) / ".venv" / "Scripts" / "python.exe"
        else:
            candidate = Path(account.path) / ".venv" / "bin" / "python"
        return str(candidate if candidate.exists() else Path(sys.executable))

    def _run_account_command(self, account: Account, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self._account_python(account), *args],
            cwd=account.path,
            capture_output=True,
            text=True,
            env=self._account_env(account),
        )

    def _command_error(self, result: subprocess.CompletedProcess) -> str:
        return (result.stderr or result.stdout or f"exit code {result.returncode}").strip()

    def _copy_telegram_session(self, source: Account, target: Account) -> None:
        source_file = self._account_telegram_session_file(source)
        target_file = self._account_telegram_session_file(target)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)
        source_journal = Path(f"{source_file}-journal")
        if source_journal.exists():
            shutil.copy2(source_journal, Path(f"{target_file}-journal"))

    def _read_telegram_auth_output(self, row: int, proc: subprocess.Popen, account: Account) -> None:
        if proc.stdout is None:
            self.background_log_signal.emit("[ERROR] Telegram auth output channel is unavailable.", account)
            return
        try:
            for raw_line in proc.stdout:
                line = raw_line.rstrip("\n")
                if not line:
                    continue
                if line == "TG_AUTH:PHONE_REQUEST":
                    self.telegram_auth_states[row] = "awaiting_phone"
                    if proc.stdin is not None:
                        proc.stdin.write(f"{account.phone_number.strip()}\n")
                        proc.stdin.flush()
                        self.background_log_signal.emit("[AUTH] Phone submission sent", account)
                    continue
                if line == "TG_AUTH:PHONE_RECEIVED":
                    self.telegram_auth_states[row] = "phone_submitted"
                    self.background_log_signal.emit("[AUTH] Phone submission acknowledged", account)
                    continue
                if line == "TG_AUTH:CODE_REQUESTED":
                    self.telegram_auth_states[row] = "awaiting_code"
                    self.background_log_signal.emit("[AUTH] Code request sent", account)
                    continue
                if line == "TG_AUTH:CODE_RECEIVED":
                    self.background_log_signal.emit("[AUTH] Code received by terminal session", account)
                    continue
                if line == "TG_AUTH:SUCCESS":
                    self.telegram_auth_states[row] = "completed"
                    self.background_log_signal.emit("[AUTH] Telegram session saved", account)
                    self.telegram_auth_finalize_signal.emit(row, account)
                    continue
                if line.startswith("TG_AUTH:ERROR:"):
                    self.telegram_auth_states[row] = "error"
                    details = line.split("TG_AUTH:ERROR:", 1)[1]
                    self.background_log_signal.emit(f"[ERROR] Telegram auth failed: {details}", account)
                    self.telegram_auth_finalize_signal.emit(row, account)
                    continue
                self.background_log_signal.emit(line, account)
        except Exception as exc:
            self.background_log_signal.emit(f"[ERROR] Telegram auth crashed: {exc}", account)
        finally:
            if proc.poll() is not None:
                if self.telegram_auth_states.get(row) not in {"completed", "error"}:
                    self.background_log_signal.emit(
                        f"[ERROR] Telegram auth process exited unexpectedly with code {proc.returncode}",
                        account,
                    )
                self.telegram_auth_finalize_signal.emit(row, account)

    def _finalize_telegram_auth_process(self, row: int, account: Account) -> None:
        proc = self.telegram_auth_processes.pop(row, None)
        self.telegram_auth_states.pop(row, None)
        if proc and proc.stdin:
            try:
                proc.stdin.close()
            except Exception:
                pass
        self._save_accounts()
        self._sync_account_auth_status(row)

    def _refresh_all(self) -> None:
        self.accounts_page.refresh()
        self._refresh_stats()
        self._sync_account_auth_status(self.accounts_page.selected_row())
        self._save_accounts()


def enable_debug_logging() -> None:
    """Enable console debug logging for process activity. Call this in Python REPL to toggle."""
    MainWindow.DEBUG_PROCESS = not MainWindow.DEBUG_PROCESS
    status = "ENABLED" if MainWindow.DEBUG_PROCESS else "DISABLED"
    print(f"[DEBUG] Process logging {status}")


def main() -> None:
    try:
        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)

        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
