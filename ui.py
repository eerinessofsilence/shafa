from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "Shafa Control"
BRANCHES = ["main", "clothes-feature"]
BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "accounts_state.json"


@dataclass
class Account:
    name: str
    path: str
    branch: str = "clothes-feature"
    open_browser: bool = False
    timer_minutes: int = 5
    status: str = "stopped"
    last_run: str = "—"
    errors: int = 0
    process: Optional[subprocess.Popen] = None

    def to_json(self) -> dict:
        data = asdict(self)
        data.pop("process", None)
        return data

    @staticmethod
    def from_json(data: dict) -> "Account":
        return Account(
            name=data.get("name", "unknown"),
            path=data.get("path", ""),
            branch=data.get("branch", "clothes-feature"),
            open_browser=bool(data.get("open_browser", False)),
            timer_minutes=int(data.get("timer_minutes", 5)),
            status=data.get("status", "stopped"),
            last_run=data.get("last_run", "—"),
            errors=int(data.get("errors", 0)),
        )


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

    def run(self) -> None:
        try:
            if not self.account_path.exists():
                raise FileNotFoundError(f"Path not found: {self.account_path}")

            self.status.emit(self.row, "checking")
            self.log.emit(f"[{self.row}] Checking branch {self.branch} for updates...")

            checkout = self._run_cmd(["git", "checkout", self.branch], self.account_path)
            if checkout.returncode != 0:
                raise RuntimeError(checkout.stderr.strip() or checkout.stdout.strip() or "git checkout failed")

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

    def __init__(self, accounts: List[Account]) -> None:
        super().__init__()
        self.accounts = accounts

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        title = QLabel("Аккаунты")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Выбор ветки, браузера и таймера для каждого аккаунта")
        subtitle.setObjectName("MutedLabel")
        root.addWidget(title)
        root.addWidget(subtitle)

        config = QFrame()
        config.setObjectName("PanelCard")
        config.setGraphicsEffect(_make_shadow())
        grid = QHBoxLayout(config)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setSpacing(20)

        self.branch_combo = QComboBox()
        self.branch_combo.addItems(BRANCHES)
        self.branch_combo.setMinimumWidth(180)

        self.browser_toggle = QCheckBox("Открывать с браузером")
        self.browser_toggle.setCursor(Qt.PointingHandCursor)

        self.timer_spin = QSpinBox()
        self.timer_spin.setRange(5, 10)
        self.timer_spin.setValue(5)
        self.timer_spin.setSuffix(" мин")

        left_col = QVBoxLayout()
        left_col.setSpacing(10)
        left_col.addWidget(QLabel("Ветка"))
        left_col.addWidget(self.branch_combo)
        left_col.addWidget(self.browser_toggle)

        right_col = QVBoxLayout()
        right_col.setSpacing(10)
        right_col.addWidget(QLabel("Таймер"))
        right_col.addWidget(self.timer_spin)

        self.apply_btn = QPushButton("ОК")
        self.apply_btn.setObjectName("PrimaryButton")
        self.apply_btn.setCursor(Qt.PointingHandCursor)
        right_col.addWidget(self.apply_btn, alignment=Qt.AlignLeft)

        grid.addLayout(left_col, 3)
        grid.addLayout(right_col, 1)
        root.addWidget(config)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.select_all = QCheckBox("Выбрать все")
        self.select_all.setCursor(Qt.PointingHandCursor)
        self.add_btn = QPushButton("Добавить папку")
        self.run_btn = QPushButton("Запустить")
        self.stop_btn = QPushButton("Остановить")
        toolbar.addWidget(self.select_all)
        toolbar.addStretch()
        for btn in [self.add_btn, self.run_btn, self.stop_btn]:
            btn.setCursor(Qt.PointingHandCursor)
            toolbar.addWidget(btn)
        root.addLayout(toolbar)

        self.table = QTableWidget(0, 8)
        self.table.setObjectName("DataTable")
        self.table.setHorizontalHeaderLabels(["", "Имя", "Путь", "Ветка", "Браузер", "Таймер", "Статус", "Ошибки"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._load_selected_to_form)
        self.table.itemChanged.connect(self._handle_item_changed)
        root.addWidget(self.table)

        self.add_btn.clicked.connect(self.add_account)
        self.run_btn.clicked.connect(self._run_selected)
        self.stop_btn.clicked.connect(self._stop_selected)
        self.apply_btn.clicked.connect(self.apply_settings)
        self.select_all.stateChanged.connect(self._toggle_all)

        self.refresh()

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
        all_checked = True
        any_checked = False
        for row in range(self.table.rowCount()):
            row_item = self.table.item(row, 0)
            if row_item is not None and row_item.checkState() == Qt.Checked:
                any_checked = True
            else:
                all_checked = False
        self.select_all.blockSignals(True)
        self.select_all.setTristate(False)
        self.select_all.setChecked(all_checked and any_checked)
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
                acc.status,
                str(acc.errors),
            ]
            for col, value in enumerate(data, start=1):
                item = QTableWidgetItem(value)
                self.table.setItem(row, col, item)
            self._paint_status(row, acc.status)
        self.table.blockSignals(False)

    def _paint_status(self, row: int, status: str) -> None:
        item = self.table.item(row, 6)
        if not item:
            return
        if status == "running":
            item.setForeground(QColor("#86efac"))
        elif status == "error":
            item.setForeground(QColor("#fca5a5"))
        elif status in {"checking", "updating", "creating venv", "installing deps", "ready"}:
            item.setForeground(QColor("#fbbf24"))
        else:
            item.setForeground(QColor("#94a3b8"))

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
            return
        self.branch_combo.setCurrentText(acc.branch)
        self.browser_toggle.setChecked(acc.open_browser)
        self.timer_spin.setValue(acc.timer_minutes)

    def apply_settings(self) -> None:
        acc = self.selected_account()
        if not acc:
            QMessageBox.information(self, "Настройки", "Выберите аккаунт в таблице.")
            return
        acc.branch = self.branch_combo.currentText()
        acc.open_browser = self.browser_toggle.isChecked()
        acc.timer_minutes = int(self.timer_spin.value())
        self.refresh()
        self.log.emit(f"[SETTINGS] {acc.name}: branch={acc.branch}, browser={acc.open_browser}, timer={acc.timer_minutes}m")

    def add_account(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Выберите папку аккаунта")
        if not path:
            return
        name = Path(path).name
        self.accounts.append(Account(name=name, path=path))
        self.refresh()
        self.log.emit(f"[ADD] Added account folder: {name}")

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
        self.chart = QFrame()
        self.chart.setObjectName("ChartPlaceholder")
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

        self.level = QComboBox()
        self.level.addItems(["Все", "Ошибки", "Успех", "Инфо"])
        root.addWidget(self.level)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(500)
        root.addWidget(self.output)

    def append(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.output.append(f"[{ts}] {text}")


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
    effect = QGraphicsDropShadowEffect()
    effect.setBlurRadius(30)
    effect.setOffset(0, 10)
    effect.setColor(QColor(0, 0, 0, 120))
    return effect


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1440, 900)

        self.accounts: List[Account] = self._load_accounts()
        self.workers: dict[int, Worker] = {}
        self.threads: dict[int, QThread] = {}
        self.session_started = datetime.now()
        self.success_count = 0
        self.error_count = 0
        self.last_log_ts: Optional[datetime] = None

        self._setup_palette()
        self._build_ui()
        self._apply_styles()
        self._setup_timer()
        self._refresh_all()

    def _load_accounts(self) -> List[Account]:
        if not STATE_FILE.exists():
            return []
        try:
            raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return [Account.from_json(item) for item in raw if item.get("path")]
        except Exception:
            return []

    def _save_accounts(self) -> None:
        try:
            STATE_FILE.write_text(
                json.dumps([acc.to_json() for acc in self.accounts], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            self.log(f"[ERROR] Failed to save accounts state: {exc}")

    def closeEvent(self, event) -> None:
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
        avatar = QLabel("Ivan")
        avatar.setObjectName("Avatar")
        avatar.setAlignment(Qt.AlignCenter)
        info = QVBoxLayout()
        info.addWidget(QLabel("Ivan"))
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
        self.accounts_page.run_requested.connect(self.run_accounts)
        self.accounts_page.stop_requested.connect(self.stop_accounts)

        root.addWidget(self.sidebar)
        root.addWidget(self.pages, 1)

        self._set_page(0)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            * {
                font-family: Inter, Segoe UI, Arial, sans-serif;
                font-size: 14px;
                color: #e5e7eb;
            }
            QMainWindow, QWidget { background: #0d1117; }
            #Sidebar {
                background: #11151d;
                border: 1px solid #242c38;
                border-radius: 26px;
            }
            #BrandTitle {
                font-size: 22px;
                font-weight: 800;
                color: #f8fafc;
            }
            #PageTitle {
                font-size: 28px;
                font-weight: 800;
                color: #f8fafc;
            }
            #MutedLabel {
                color: #98a2b3;
            }
            #FieldLabel {
                color: #cbd5e1;
                font-weight: 600;
            }
            #Avatar {
                min-width: 52px;
                max-width: 52px;
                min-height: 52px;
                max-height: 52px;
                border-radius: 16px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6d28d9, stop:1 #0ea5e9);
                color: white;
                font-weight: 800;
            }
            #StatCard, #PanelCard {
                background: #141924;
                border: 1px solid #262f3c;
                border-radius: 22px;
            }
            #CardTitle { color: #cbd5e1; }
            #CardValue {
                font-size: 28px;
                font-weight: 800;
                color: #f8fafc;
            }
            #StatusGood { color: #4ade80; font-weight: 700; }
            #ChartPlaceholder {
                background: rgba(148, 163, 184, 0.08);
                border: 1px dashed rgba(148, 163, 184, 0.28);
                border-radius: 16px;
            }
            QPushButton {
                padding: 11px 14px;
                border-radius: 14px;
                border: 1px solid #2d3745;
                background: #151b24;
                color: #e5e7eb;
                font-weight: 600;
            }
            QPushButton:hover { background: #1b2230; }
            QPushButton:checked {
                background: rgba(59, 130, 246, 0.18);
                border-color: rgba(59, 130, 246, 0.45);
                color: white;
            }
            QPushButton#PrimaryButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #7c3aed);
                border: none;
            }
            QPushButton#PrimaryButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #6d28d9);
            }
            QPushButton#DangerButton {
                background: #2a1212;
                border: 1px solid #5b1f1f;
                color: #fca5a5;
            }
            QPushButton#DangerButton:hover { background: #3a1515; }
            QLineEdit, QComboBox, QTextEdit, QTableWidget, QSpinBox {
                background: #11161f;
                border: 1px solid #263241;
                border-radius: 14px;
                padding: 10px 12px;
                selection-background-color: #2563eb;
            }
            QHeaderView::section {
                background: #11161f;
                color: #cbd5e1;
                padding: 10px;
                border: none;
                border-bottom: 1px solid #263241;
                font-weight: 700;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(148, 163, 184, 0.28);
                border-radius: 5px;
                min-height: 30px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 6px;
                border: 1px solid #3b4657;
                background: #11161f;
            }
            QCheckBox::indicator:checked {
                background: #2563eb;
                border-color: #2563eb;
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
        speed = 0.0
        elapsed_min = max((datetime.now() - self.session_started).total_seconds() / 60.0, 1 / 60)
        speed = self.success_count / elapsed_min
        self.dashboard_page.total_accounts.set_value(str(total))
        self.dashboard_page.active_accounts.set_value(str(active))
        self.dashboard_page.items_found.set_value(str(self.success_count))
        self.dashboard_page.errors_today.set_value(str(self.error_count))
        self.dashboard_page.queue_state.setText(f"Очередь: {active} запущено")
        self.dashboard_page.last_run.setText(f"Последний запуск: {self._last_run_text()}")
        self.stats_page.update_stats(speed=speed, total=self.success_count, errors=self.error_count, bans=0, timeouts=0)

    def _last_run_text(self) -> str:
        runs = [a.last_run for a in self.accounts if a.last_run != "—"]
        return max(runs) if runs else "—"

    def log(self, text: str) -> None:
        self.logs_page.append(text)
        self.last_log_ts = datetime.now()
        upper = text.lower()
        if any(key in upper for key in ["[ok]", "created", "success", "started on"]):
            self.success_count += 1
        if "[error]" in upper or "error" in upper:
            self.error_count += 1

    def _set_page(self, index: int) -> None:
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        self.pages.setCurrentIndex(index)
        if index == 4:
            self.log("Открыта страница логов")

    def _sync_dashboard(self, _row: int) -> None:
        self._refresh_stats()

    def _update_account_view(self, row: int, status: str) -> None:
        if 0 <= row < len(self.accounts):
            self.accounts[row].status = status
            self.accounts_page.refresh()
            self._refresh_stats()

    def run_accounts(self, rows: List[int]) -> None:
        for row in rows:
            self.run_account(row)

    def run_account(self, row: int) -> None:
        if row < 0 or row >= len(self.accounts):
            return
        acc = self.accounts[row]

        if acc.process is not None and acc.process.poll() is None:
            self.log(f"[RUN] {acc.name} already running")
            return

        self.log(f"[RUN] Starting {acc.name} on branch {acc.branch}")
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
                        env = os.environ.copy()
                        env.setdefault("QT_QPA_PLATFORM", "xcb")

                        proc = subprocess.Popen(
                            [py_bin, "main.py"],
                            cwd=account.path,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1,
                            env=env,
                        )
                        account.process = proc
                        account.status = "running"
                        account.last_run = datetime.now().strftime("%Y-%m-%d %H:%M")

                        if account.branch == "main" and proc.stdin is not None:
                            browser_answer = "y" if account.open_browser else "n"
                            timer_answer = str(account.timer_minutes)
                            proc.stdin.write(f"{browser_answer}\n{timer_answer}\n")
                            proc.stdin.flush()
                            self.log(
                                f"[OK] {account.name} started on main with browser={browser_answer}, timer={timer_answer}m (pid={proc.pid})"
                            )
                        else:
                            self.log(f"[OK] {account.name} started on {account.branch} (pid={proc.pid})")
                    except Exception as exc:
                        account.status = "error"
                        account.errors += 1
                        self.log(f"[ERROR] Failed to start {account.name}: {exc}")
                else:
                    account.status = "error"
                    account.errors += 1
                    self.log(f"[ERROR] {account.name}: {info}")
                self.accounts_page.refresh()
                self._refresh_stats()

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

    def stop_account(self, row: int) -> None:
        if row < 0 or row >= len(self.accounts):
            return
        acc = self.accounts[row]
        self.log(f"[STOP] Stopping {acc.name}")

        if row in self.workers:
            self.workers[row].request_stop()

        proc = acc.process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
                self.log(f"[STOP] Process terminated for {acc.name}")
            except Exception:
                try:
                    proc.kill()
                    self.log(f"[STOP] Process killed for {acc.name}")
                except Exception as exc:
                    self.log(f"[ERROR] stop failed: {exc}")
        acc.process = None
        acc.status = "stopped"
        self.accounts_page.refresh()
        self._refresh_stats()
        self._save_accounts()

    def _refresh_all(self) -> None:
        self.accounts_page.refresh()
        self._refresh_stats()
        self._save_accounts()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Segoe UI", 10))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
