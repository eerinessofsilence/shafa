from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
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
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "Shafa Control"


@dataclass
class Account:
    name: str
    path: str
    status: str = "stopped"
    last_run: str = "—"
    errors: int = 0
    process: Optional[subprocess.Popen] = None


class Worker(QObject):
    log = Signal(str)
    status = Signal(int, str)
    finished = Signal(int, bool, str)

    def __init__(self, row: int, account_path: str) -> None:
        super().__init__()
        self.row = row
        self.account_path = Path(account_path)
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def _run_cmd(self, cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
        self.log.emit(f"$ {' '.join(cmd)}")
        return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)

    def run(self) -> None:
        try:
            if not self.account_path.exists():
                raise FileNotFoundError(f"Path not found: {self.account_path}")

            self.status.emit(self.row, "updating")
            self.log.emit(f"[{self.row}] Updating repository...")

            checkout = self._run_cmd(["git", "checkout", "main"], self.account_path)
            if checkout.returncode != 0:
                raise RuntimeError(checkout.stderr.strip() or checkout.stdout.strip() or "git checkout failed")
            if self._stop_requested:
                raise RuntimeError("Stopped by user")

            pull = self._run_cmd(["git", "pull"], self.account_path)
            if pull.returncode != 0:
                raise RuntimeError(pull.stderr.strip() or pull.stdout.strip() or "git pull failed")
            if self._stop_requested:
                raise RuntimeError("Stopped by user")

            venv_dir = self.account_path / ".venv"
            if venv_dir.exists():
                self.log.emit(f"[{self.row}] Removing existing .venv...")
                shutil.rmtree(venv_dir)

            self.status.emit(self.row, "creating venv")
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

            if self._stop_requested:
                raise RuntimeError("Stopped by user")

            # The main process is started in the GUI thread so it can be tracked and stopped later.
            self.status.emit(self.row, "ready")
            self.finished.emit(self.row, True, str(py_bin))
        except Exception as exc:
            self.finished.emit(self.row, False, str(exc))


class StatCard(QFrame):
    def __init__(self, title: str, value: str, subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("StatCard")
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
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.addWidget(QLabel("Активность"))
        activity = QFrame()
        activity.setObjectName("ChartPlaceholder")
        activity.setMinimumHeight(240)
        left_layout.addWidget(activity)

        right = QFrame()
        right.setObjectName("PanelCard")
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
    run_requested = Signal(int)
    stop_requested = Signal(int)

    def __init__(self, accounts: List[Account]) -> None:
        super().__init__()
        self.accounts = accounts

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        title = QLabel("Аккаунты")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Управление папками аккаунтов, запуском и остановкой процессов")
        subtitle.setObjectName("MutedLabel")
        root.addWidget(title)
        root.addWidget(subtitle)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.add_btn = QPushButton("Добавить папку")
        self.run_btn = QPushButton("Запустить")
        self.stop_btn = QPushButton("Остановить")
        for btn in [self.add_btn, self.run_btn, self.stop_btn]:
            btn.setCursor(Qt.PointingHandCursor)
            toolbar.addWidget(btn)
        toolbar.addStretch()
        root.addLayout(toolbar)

        self.table = QTableWidget(0, 5)
        self.table.setObjectName("DataTable")
        self.table.setHorizontalHeaderLabels(["Имя", "Путь", "Статус", "Последний запуск", "Ошибки"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._emit_selection)
        root.addWidget(self.table)

        self.add_btn.clicked.connect(self.add_account)
        self.run_btn.clicked.connect(self._run_selected)
        self.stop_btn.clicked.connect(self._stop_selected)

        self.refresh()

    def refresh(self) -> None:
        self.table.setRowCount(0)
        for acc in self.accounts:
            row = self.table.rowCount()
            self.table.insertRow(row)
            data = [acc.name, acc.path, acc.status, acc.last_run, str(acc.errors)]
            for col, value in enumerate(data):
                item = QTableWidgetItem(value)
                self.table.setItem(row, col, item)
            self._paint_status(row, acc.status)

    def _paint_status(self, row: int, status: str) -> None:
        item = self.table.item(row, 2)
        if not item:
            return
        if status == "running":
            item.setForeground(QColor("#4ade80"))
        elif status == "error":
            item.setForeground(QColor("#f87171"))
        elif status == "updating" or status == "creating venv" or status == "installing deps" or status == "ready":
            item.setForeground(QColor("#fbbf24"))
        else:
            item.setForeground(QColor("#94a3b8"))

    def selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def add_account(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Выберите папку аккаунта")
        if not path:
            return
        name = Path(path).name
        self.accounts.append(Account(name=name, path=path))
        self.refresh()
        self.log.emit(f"[ADD] Added account folder: {name}")

    def _run_selected(self) -> None:
        row = self.selected_row()
        if row < 0:
            QMessageBox.information(self, "Запуск", "Выберите аккаунт в таблице.")
            return
        self.run_requested.emit(row)

    def _stop_selected(self) -> None:
        row = self.selected_row()
        if row < 0:
            QMessageBox.information(self, "Остановка", "Выберите аккаунт в таблице.")
            return
        self.stop_requested.emit(row)

    def _emit_selection(self) -> None:
        row = self.selected_row()
        if row >= 0:
            self.selection_changed.emit(row)


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
        for t, v, s in [("Скорость", "42/min", "средняя"), ("Обработано", "9 531", "за всё время"), ("Баны", "2", "за неделю"), ("Таймауты", "14", "за 24 часа")]:
            cards.addWidget(StatCard(t, v, s))
        root.addLayout(cards)

        panel = QFrame()
        panel.setObjectName("PanelCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(QLabel("Графики и тренды"))
        chart = QFrame()
        chart.setObjectName("ChartPlaceholder")
        chart.setMinimumHeight(280)
        layout.addWidget(chart)
        root.addWidget(panel)
        root.addStretch()


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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1440, 880)

        self.accounts: List[Account] = []
        self.workers: dict[int, Worker] = {}
        self.threads: dict[int, QThread] = {}

        self._setup_palette()
        self._build_ui()
        self._apply_styles()
        self._setup_timer()

    def _setup_palette(self) -> None:
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor("#0b0f14"))
        pal.setColor(QPalette.Base, QColor("#111827"))
        pal.setColor(QPalette.AlternateBase, QColor("#0f172a"))
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
        self.accounts_page.run_requested.connect(self.run_account)
        self.accounts_page.stop_requested.connect(self.stop_account)

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
            QMainWindow, QWidget { background: #0b0f14; }
            #Sidebar {
                background: #0f172a;
                border: 1px solid #1f2937;
                border-radius: 24px;
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
                color: #94a3b8;
            }
            #Avatar {
                min-width: 52px;
                max-width: 52px;
                min-height: 52px;
                max-height: 52px;
                border-radius: 16px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8b5cf6, stop:1 #06b6d4);
                color: white;
                font-weight: 800;
            }
            #StatCard, #PanelCard {
                background: #111827;
                border: 1px solid #223042;
                border-radius: 20px;
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
                border: 1px solid #2b3647;
                background: #111827;
                color: #e5e7eb;
                font-weight: 600;
            }
            QPushButton:hover { background: #172033; }
            QPushButton:checked {
                background: rgba(59, 130, 246, 0.20);
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
            QLineEdit, QComboBox, QTextEdit, QTableWidget {
                background: #0f172a;
                border: 1px solid #223042;
                border-radius: 14px;
                padding: 10px 12px;
                selection-background-color: #2563eb;
            }
            QHeaderView::section {
                background: #0f172a;
                color: #cbd5e1;
                padding: 10px;
                border: none;
                border-bottom: 1px solid #223042;
                font-weight: 700;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(148, 163, 184, 0.35);
                border-radius: 5px;
                min-height: 30px;
            }
            """
        )

    def _setup_timer(self) -> None:
        self.ticks = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._demo_tick)
        self.timer.start(5000)

    def _demo_tick(self) -> None:
        self.ticks += 1
        total = len(self.accounts)
        active = sum(1 for a in self.accounts if a.status == "running")
        self.dashboard_page.total_accounts.set_value(str(total))
        self.dashboard_page.active_accounts.set_value(str(active))
        self.dashboard_page.items_found.set_value(f"{1248 + self.ticks * 17:,}".replace(",", " "))
        self.dashboard_page.errors_today.set_value(str(sum(a.errors for a in self.accounts)))
        self.dashboard_page.queue_state.setText(f"Очередь: {self.ticks} задач")
        self.logs_page.append("Автообновление статистики")

    def log(self, text: str) -> None:
        self.logs_page.append(text)

    def _set_page(self, index: int) -> None:
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        self.pages.setCurrentIndex(index)
        if index == 4:
            self.log("Открыта страница логов")

    def _sync_dashboard(self, _row: int) -> None:
        self._demo_tick()

    def run_account(self, row: int) -> None:
        if row < 0 or row >= len(self.accounts):
            return
        acc = self.accounts[row]

        if acc.process is not None and acc.process.poll() is None:
            self.log(f"[RUN] {acc.name} already running")
            return

        self.log(f"[RUN] Starting {acc.name}")
        worker = Worker(row, acc.path)
        thread = QThread(self)
        worker.moveToThread(thread)

        def on_status(r: int, status: str) -> None:
            if 0 <= r < len(self.accounts):
                self.accounts[r].status = status
                self.accounts_page.refresh()
                self._demo_tick()

        def on_finished(r: int, ok: bool, info: str) -> None:
            # IMPORTANT: no thread.wait() here. The signal may be delivered in the same thread context.
            if 0 <= r < len(self.accounts):
                if ok:
                    py_bin = info
                    try:
                        proc = subprocess.Popen([py_bin, "main.py"], cwd=self.accounts[r].path)
                        self.accounts[r].process = proc
                        self.accounts[r].status = "running"
                        self.accounts[r].last_run = datetime.now().strftime("%Y-%m-%d %H:%M")
                        self.log(f"[OK] {self.accounts[r].name} started (pid={proc.pid})")
                    except Exception as exc:
                        self.accounts[r].status = "error"
                        self.accounts[r].errors += 1
                        self.log(f"[ERROR] Failed to start {self.accounts[r].name}: {exc}")
                else:
                    self.accounts[r].status = "error"
                    self.accounts[r].errors += 1
                    self.log(f"[ERROR] {self.accounts[r].name}: {info}")
                self.accounts_page.refresh()
                self._demo_tick()

            thread.quit()
            thread.finished.connect(thread.deleteLater)
            worker.deleteLater()
            self.workers.pop(r, None)
            self.threads.pop(r, None)

        worker.log.connect(self.log)
        worker.status.connect(on_status)
        worker.finished.connect(on_finished)
        thread.started.connect(worker.run)

        self.workers[row] = worker
        self.threads[row] = thread
        thread.start()

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
        self._demo_tick()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Segoe UI", 10))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
