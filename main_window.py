import sys
import time
import json
from datetime import datetime
from collections import deque

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QProgressBar, QTextEdit, QCheckBox, QGroupBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
import psutil

class MainWindow(QMainWindow):
    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance
        self.setWindowTitle("DevCleaner Pro - NEURAL_ARCHTECT_PREMIUM++ v8.3")
        self.setMinimumSize(900, 600)
        self.setup_ui()
        self.setup_timer()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        info_layout = QHBoxLayout()
        self.cpu_label = QLabel("CPU: --%")
        self.ram_label = QLabel("RAM: --/-- GB (--%)")
        self.api_label = QLabel("API: OFF")
        self.user_label = QLabel("Пользователь: --")
        for lbl in (self.cpu_label, self.ram_label, self.api_label, self.user_label):
            lbl.setStyleSheet("font-weight: bold; margin: 5px;")
            info_layout.addWidget(lbl)
        main_layout.addLayout(info_layout)

        tabs = QTabWidget()
        main_layout.addWidget(tabs)

        self.process_table = QTableWidget()
        self.process_table.setColumnCount(5)
        self.process_table.setHorizontalHeaderLabels(["PID", "Имя", "Память (MB)", "CPU %", "Действие"])
        self.process_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.process_table.setSelectionBehavior(QTableWidget.SelectRows)
        tabs.addTab(self.process_table, "Процессы")

        stats_widget = QWidget()
        stats_layout = QVBoxLayout(stats_widget)
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        stats_layout.addWidget(self.stats_text)
        tabs.addTab(stats_widget, "Статистика")

        ctrl_widget = QWidget()
        ctrl_layout = QVBoxLayout(ctrl_widget)

        cache_group = QGroupBox("Очистка кэша")
        cache_btn = QPushButton("Очистить кэш разработки")
        cache_btn.clicked.connect(self.clean_cache)
        cache_layout = QVBoxLayout(cache_group)
        cache_layout.addWidget(cache_btn)
        ctrl_layout.addWidget(cache_group)

        report_group = QGroupBox("Отчёты")
        report_btn = QPushButton("Создать PDF-отчёт (daily)")
        report_btn.clicked.connect(self.generate_report)
        report_layout = QVBoxLayout(report_group)
        report_layout.addWidget(report_btn)
        ctrl_layout.addWidget(report_group)

        settings_group = QGroupBox("Настройки")
        self.auto_kill_cb = QCheckBox("Авто-завершение тяжёлых процессов")
        self.auto_kill_cb.setChecked(self.app.config.get("auto_kill", False))
        self.auto_kill_cb.stateChanged.connect(self.toggle_auto_kill)
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.addWidget(self.auto_kill_cb)
        ctrl_layout.addWidget(settings_group)

        ctrl_layout.addStretch()
        tabs.addTab(ctrl_widget, "Управление")

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        tabs.addTab(self.log_text, "Логи")

    def setup_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_all)
        self.timer.start(2000)

    def update_all(self):
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        self.cpu_label.setText(f"CPU: {cpu:.0f}%")
        self.ram_label.setText(f"RAM: {mem.used/1024**3:.1f}/{mem.total/1024**3:.1f} GB ({mem.percent:.0f}%)")
        self.api_label.setText(f"API: {'ON' if self.app.api_server._running else 'OFF'}")
        user = self.app.current_user.get("username", "не авторизован") if self.app.current_user else "не авторизован"
        self.user_label.setText(f"Пользователь: {user}")

        try:
            processes = self.app.monitor.scan_processes()
            self.process_table.setRowCount(len(processes))
            for i, proc in enumerate(processes):
                self.process_table.setItem(i, 0, QTableWidgetItem(str(proc["pid"])))
                self.process_table.setItem(i, 1, QTableWidgetItem(proc["name"]))
                self.process_table.setItem(i, 2, QTableWidgetItem(f"{proc['memory_mb']:.1f}"))
                self.process_table.setItem(i, 3, QTableWidgetItem(f"{proc.get('cpu_percent', 0):.1f}"))
                btn = QPushButton("Kill")
                btn.clicked.connect(lambda checked, pid=proc["pid"]: self.kill_process(pid))
                self.process_table.setCellWidget(i, 4, btn)
        except Exception as e:
            pass

        self.stats_text.setPlainText(json.dumps({
            "system": self.app._get_system_stats(),
            "app": self.app.stats,
            "ml": self.app.analyzer.get_model_stats()
        }, indent=2, ensure_ascii=False))

        self.log_text.setPlainText(json.dumps(self.app.stats.get("history", [])[-20:], indent=2, ensure_ascii=False))

    def kill_process(self, pid):
        ok, msg = self.app.monitor.kill_process(pid)
        QMessageBox.information(self, "Результат", msg)

    def clean_cache(self):
        total, details = self.app.clean_all_caches()
        QMessageBox.information(self, "Очистка кэша", f"Освобождено {total:.1f} МБ")

    def generate_report(self):
        path = self.app.generate_report()
        if path:
            QMessageBox.information(self, "Отчёт", f"Отчёт сохранён:\n{path}")

    def toggle_auto_kill(self, state):
        self.app.config["auto_kill"] = (state == Qt.Checked)
        self.app._save_config()
