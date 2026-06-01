"""
DevCleaner Pro – Основное приложение (v8.3 NEURAL_ARCHTECT_PREMIUM++)
Белый список, улучшенный помощник, логирование, ML‑анализ.
"""
import sys, os, json, time, threading, subprocess, glob
from pathlib import Path
from datetime import datetime
from typing import Optional

import psutil
from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QScrollArea, QWidget
from PyQt5.QtCore import QObject, pyqtSignal
import pystray
from pystray import MenuItem, Menu
from PIL import Image, ImageDraw
import winreg
import win32event
import win32api
import winerror
import ctypes

from auth_system import AuthSystem
from ml_analyzer import ProcessAnalyzer, ProcessMonitor
from pdf_reporter import PDFReporter
from main_window import MainWindow
from api_server import APIServer

# Пути
CONFIG_DIR = Path.home() / ".devcleaner_pro"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = CONFIG_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
LOGS_DIR = CONFIG_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
CONFIG_PATH = CONFIG_DIR / "config.json"
LOG_PATH = CONFIG_DIR / "app_log.json"
ERROR_LOG_DIR = CONFIG_DIR / "error_logs"
ERROR_LOG_DIR.mkdir(exist_ok=True)


class RotatingLogger:
    """Потокобезопасный логгер с ротацией (1000 строк на файл, макс 100 МБ)."""
    def __init__(self, log_dir: Path, max_total_size_mb=100, max_lines_per_file=1000):
        self.log_dir = log_dir
        self.max_total_size = max_total_size_mb * 1024 * 1024
        self.max_lines = max_lines_per_file
        self.current_file = None
        self.current_lines = 0
        self._lock = threading.Lock()
        self._init_current_file()

    def _init_current_file(self):
        files = sorted(glob.glob(str(self.log_dir / "devcleaner_*.log")))
        if files:
            last_file = Path(files[-1])
            try:
                with open(last_file, 'r', encoding='utf-8') as f:
                    self.current_lines = sum(1 for _ in f)
            except:
                self.current_lines = 0
            if self.current_lines >= self.max_lines:
                self._rotate()
            else:
                self.current_file = last_file
        else:
            self._rotate()

    def _rotate(self):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        new_file = self.log_dir / f"devcleaner_{timestamp}.log"
        self.current_file = new_file
        self.current_lines = 0
        total_size = sum(f.stat().st_size for f in self.log_dir.glob("devcleaner_*.log") if f.is_file())
        files = sorted(self.log_dir.glob("devcleaner_*.log"), key=lambda f: f.stat().st_mtime)
        while total_size > self.max_total_size and len(files) > 1:
            oldest = files.pop(0)
            total_size -= oldest.stat().st_size
            oldest.unlink()

    def log(self, level: str, message: str):
        with self._lock:
            if self.current_lines >= self.max_lines:
                self._rotate()
            timestamp = datetime.now().isoformat()
            line = f"{timestamp} [{level}] {message}\n"
            try:
                with open(self.current_file, 'a', encoding='utf-8') as f:
                    f.write(line)
                    f.flush()
                self.current_lines += 1
            except:
                pass


logger = None


class CPUMonitor:
    def __init__(self, app):
        self.app = app
        self.high_load = False

    def start(self):
        def loop():
            while self.app.running:
                try:
                    cpu = psutil.cpu_percent(interval=1)
                    self.high_load = cpu > 80
                    if self.high_load:
                        self.app.config['scan_interval_seconds'] = 180
                    else:
                        self.app.config['scan_interval_seconds'] = 30
                except:
                    pass
                time.sleep(5)
        threading.Thread(target=loop, daemon=True).start()


class GuiDispatcher(QObject):
    show_main_window_signal = pyqtSignal()
    show_process_alert_signal = pyqtSignal(list)


class DevCleanerPro:
    def __init__(self):
        self.config = self._load_config()
        self.stats = self._load_stats()
        self.running = True
        self.icon = None

        self.auth_system = AuthSystem(CONFIG_DIR)
        self.analyzer = ProcessAnalyzer(CONFIG_DIR)
        self.monitor = ProcessMonitor(self.analyzer)
        self.reporter = PDFReporter(REPORTS_DIR)

        self.session_token: Optional[str] = None
        self.current_user: Optional[dict] = None
        self.hud_process = None
        self.main_window = None
        self.gui_dispatcher = None

        self.monitor_thread = None
        self.report_thread = None

        self.api_server = APIServer(self, host='127.0.0.1', port=5050)
        self.api_enabled = self.config.get('api_enabled', False)

        self.lock = threading.Lock()
        self.qt_app = None
        self.light_mode = False

        self.cpu_monitor = CPUMonitor(self)

        self.last_alert_time = 0
        self.alert_cooldown = 300

    def _load_config(self) -> dict:
        defaults = {
            'memory_threshold_mb': 500,
            'cpu_threshold_percent': 50,
            'scan_interval_seconds': 30,
            'auto_kill': False,
            'auto_report_interval_hours': 24,
            'clear_cache_on_startup': False,
            'notifications': True,
            'hud_enabled': False,
            'ml_enabled': True,
            'api_enabled': False,
            'alert_memory_mb': 300,
            'alert_cpu_percent': 50,
            'process_whitelist': []
        }
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                defaults.update(config)
            except:
                pass
        return defaults

    def _save_config(self):
        with open(CONFIG_PATH, 'w') as f:
            json.dump(self.config, f, indent=2)

    def _load_stats(self) -> dict:
        if LOG_PATH.exists():
            try:
                with open(LOG_PATH, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            'processes_killed': 0,
            'memory_freed_mb': 0,
            'cache_cleaned_mb': 0,
            'reports_generated': 0,
            'history': []
        }

    def _save_stats(self):
        with self.lock:
            with open(LOG_PATH, 'w') as f:
                json.dump(self.stats, f, indent=2)

    def login(self, username, password):
        token = self.auth_system.login(username, password)
        if token:
            self.session_token = token
            self.current_user = self.auth_system.get_user_info(token)
            return True
        return False

    def logout(self):
        if self.session_token:
            self.auth_system.logout(self.session_token)
            self.session_token = None
            self.current_user = None

    def create_icon_image(self):
        width = 64
        height = 64
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.ellipse([4, 4, width-4, height-4], fill=(46, 204, 113, 255))
        dc.ellipse([12, 12, width-12, height-12], fill=(39, 174, 96, 255))
        dc.ellipse([20, 20, width-20, height-20], fill=(255, 255, 255, 200))
        return image

    def send_notification(self, title, message):
        if self.config['notifications'] and self.icon:
            self.icon.notify(message, title)

    def _get_system_stats(self):
        return {
            'cpu_total': psutil.cpu_percent(),
            'memory_total': psutil.virtual_memory().percent,
            'memory_used_gb': psutil.virtual_memory().used / 1024**3,
            'memory_total_gb': psutil.virtual_memory().total / 1024**3,
        }

    def generate_report(self, report_type="daily"):
        try:
            processes = self.monitor.scan_processes()
            ml_stats = self.analyzer.get_model_stats()
            stats = {**self._get_system_stats(), **self.stats}
            user_info = self.current_user or {'username': 'System', 'role': 'admin'}
            pdf_path = self.reporter.generate_report(stats, processes, ml_stats, user_info, report_type)
            with self.lock:
                self.stats['reports_generated'] += 1
                self.stats['history'].append({
                    'timestamp': datetime.now().isoformat(),
                    'action': 'report_generated',
                    'path': str(pdf_path),
                })
            self._save_stats()
            self.send_notification("Отчет создан", f"PDF отчет сохранен:\n{pdf_path}")
            os.startfile(REPORTS_DIR)
            if logger:
                logger.log("INFO", f"Отчет создан: {pdf_path}")
            return pdf_path
        except Exception as e:
            self.send_notification("Ошибка", f"Не удалось создать отчет: {e}")
            if logger:
                logger.log("ERROR", f"Ошибка создания отчета: {e}")
            return None

    def clean_all_caches(self):
        from ml_analyzer import CLEANUP_PATHS
        import shutil
        total_freed = 0
        freed_details = {}
        for name, path in CLEANUP_PATHS.items():
            try:
                if not path.exists():
                    continue
                size_before = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
                for item in path.iterdir():
                    try:
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item)
                    except:
                        pass
                size_after = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
                freed = size_before - size_after
                if freed > 0:
                    freed_mb = freed / 1024 / 1024
                    total_freed += freed
                    freed_details[name] = round(freed_mb, 1)
            except:
                pass
        total_mb = total_freed / 1024 / 1024
        if total_mb > 0:
            with self.lock:
                self.stats['cache_cleaned_mb'] += total_mb
                self.stats['history'].append({
                    'timestamp': datetime.now().isoformat(),
                    'action': 'clean_cache',
                    'total_freed_mb': round(total_mb, 1),
                    'details': freed_details,
                })
            self._save_stats()
            self.send_notification("Кэш очищен", f"Освобождено: {total_mb:.1f} МБ")
            if logger:
                logger.log("INFO", f"Кэш очищен: {total_mb:.1f} МБ")
        return total_mb, freed_details

    def toggle_hud(self):
        try:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'].lower() == 'devhud.exe':
                    proc.terminate()
        except:
            pass

        if self.hud_process and self.hud_process.poll() is None:
            self.hud_process.terminate()
            self.hud_process = None
            self.config['hud_enabled'] = False
            self.send_notification("HUD", "HUD выключен")
        else:
            hud_exe = Path(sys.executable).parent / "DevHud.exe"
            if not hud_exe.exists():
                hud_exe = Path(__file__).parent / "DevHud.exe"
            if hud_exe.exists():
                try:
                    self.hud_process = subprocess.Popen(
                        [str(hud_exe)],
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    self.config['hud_enabled'] = True
                    self.send_notification("HUD", "HUD запущен с графиками")
                except Exception as e:
                    self.send_notification("HUD Ошибка", f"Не удалось запустить HUD: {e}")
                    if logger:
                        logger.log("ERROR", f"Ошибка запуска HUD: {e}")
            else:
                self.send_notification("HUD", "Файл DevHud.exe не найден.")
        self._save_config()

    def toggle_api(self):
        if self.api_server._running:
            self.api_server.shutdown()
            self.config['api_enabled'] = False
            self.send_notification("API Сервер", "API остановлен")
        else:
            self.api_server.start()
            self.config['api_enabled'] = True
            self.send_notification("API Сервер", f"API запущен на http://{self.api_server.host}:{self.api_server.port}")
        self._save_config()
        if self.icon:
            self.icon.update_menu()

    # --- Белый список ---
    def add_to_whitelist(self, proc_name: str):
        name = proc_name.lower()
        whitelist = self.config.setdefault('process_whitelist', [])
        if name not in whitelist:
            whitelist.append(name)
            self._save_config()
            self.send_notification("Белый список", f"Процесс '{proc_name}' добавлен в игнорируемые.")
            if logger:
                logger.log("INFO", f"Добавлен в белый список: {proc_name}")

    def remove_from_whitelist(self, proc_name: str):
        name = proc_name.lower()
        whitelist = self.config.get('process_whitelist', [])
        if name in whitelist:
            whitelist.remove(name)
            self._save_config()
            self.send_notification("Белый список", f"Процесс '{proc_name}' удалён из игнорируемых.")
            if logger:
                logger.log("INFO", f"Удалён из белого списка: {proc_name}")

    def is_whitelisted(self, proc_name: str) -> bool:
        return proc_name.lower() in self.config.get('process_whitelist', [])

    # --- Поиск тяжёлых процессов ---
    def find_suspicious_processes(self):
        suspicious = []
        try:
            for proc in psutil.process_iter(['name', 'memory_info', 'cpu_percent']):
                if proc.info['name'].lower() in ['compattelrunner.exe']:
                    suspicious.append({
                        'pid': proc.pid,
                        'name': proc.info['name'],
                        'memory_mb': proc.info['memory_info'].rss / 1024 / 1024,
                        'cpu_percent': proc.info['cpu_percent'] or 0,
                        'safe_to_kill': True,
                        'confidence': 0.9
                    })
        except:
            pass
        return suspicious

    def find_heavy_processes(self):
        my_pid = os.getpid()
        heavy = self.find_suspicious_processes()
        alert_mem = self.config.get('alert_memory_mb', 300)
        alert_cpu = self.config.get('alert_cpu_percent', 50)
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
            try:
                if proc.pid == my_pid:
                    continue
                if self.is_whitelisted(proc.info['name']):
                    continue
                mem = proc.info['memory_info'].rss / 1024 / 1024
                cpu = proc.info['cpu_percent'] or 0
                if mem > alert_mem or cpu > alert_cpu:
                    heavy.append({
                        'pid': proc.pid,
                        'name': proc.info['name'],
                        'memory_mb': mem,
                        'cpu_percent': cpu,
                        'safe_to_kill': True,
                        'confidence': 0.9
                    })
            except:
                pass
        seen = set()
        unique_heavy = []
        for p in heavy:
            if p['pid'] not in seen:
                seen.add(p['pid'])
                unique_heavy.append(p)
        unique_heavy.sort(key=lambda x: x['memory_mb'], reverse=True)
        return unique_heavy[:20]

    # --- Автоматический помощник и мониторинг ---
    def process_alert_loop(self):
        while self.running:
            try:
                time.sleep(120)
                if not self.running:
                    break
                heavy = self.find_heavy_processes()
                if heavy and self.gui_dispatcher:
                    self.gui_dispatcher.show_process_alert_signal.emit(heavy)
                    self.send_notification(
                        "Тяжёлые процессы",
                        f"Обнаружено {len(heavy)} процессов. Окно помощника открыто."
                    )
                    if logger:
                        logger.log("INFO", f"Автоматическое оповещение о {len(heavy)} процессах")
            except Exception as e:
                if logger:
                    logger.log("ERROR", f"process_alert_loop: {e}")

    def monitor_loop(self):
        while self.running:
            try:
                if self.config['auto_kill']:
                    my_pid = os.getpid()
                    for proc in self.monitor.scan_processes():
                        if proc['pid'] == my_pid:
                            continue
                        if self.is_whitelisted(proc['name']):
                            continue
                        if proc.get('confidence', 0) > 0.8:
                            success, _ = self.monitor.kill_process(proc['pid'])
                            if success:
                                with self.lock:
                                    self.stats['processes_killed'] += 1
                                    self.stats['memory_freed_mb'] += proc.get('memory_mb', 0)
                                self._save_stats()
                                if logger:
                                    logger.log("INFO", f"Авто-завершён процесс {proc['name']} (PID {proc['pid']})")
                if self.icon:
                    stats = self._get_system_stats()
                    api_status = "API: ON" if self.api_server._running else "API: OFF"
                    self.icon.title = (
                        f"DevCleaner Pro | CPU: {stats['cpu_total']:.0f}% | "
                        f"RAM: {stats['memory_total']:.0f}% | {api_status}"
                    )
            except Exception as e:
                if logger:
                    logger.log("ERROR", f"monitor_loop: {e}")
            time.sleep(self.config['scan_interval_seconds'])

    def auto_report_loop(self):
        while self.running:
            try:
                interval = self.config['auto_report_interval_hours'] * 3600
                time.sleep(interval)
                if self.running:
                    self.generate_report("daily")
            except Exception as e:
                if logger:
                    logger.log("ERROR", f"auto_report_loop: {e}")

    def toggle_light_mode(self):
        self.light_mode = not self.light_mode
        if self.light_mode:
            self.send_notification("Режим", "Лёгкий режим включён. Автообучение приостановлено.")
            if logger:
                logger.log("INFO", "Включён лёгкий режим")
        else:
            self.send_notification("Режим", "Полный режим.")
            if logger:
                logger.log("INFO", "Выключен лёгкий режим")

    # --- Показ диалога с кнопкой "Запомнить" ---
    def show_process_alert(self, processes):
        if not processes:
            return
        now = time.time()
        if now - self.last_alert_time < self.alert_cooldown:
            return
        self.last_alert_time = now

        def kill_callback(pid):
            self.monitor.kill_process(pid)
            with self.lock:
                self.stats['processes_killed'] += 1
                self.stats['memory_freed_mb'] += next((p['memory_mb'] for p in processes if p['pid'] == pid), 0)
            self._save_stats()
            if logger:
                logger.log("INFO", f"Завершён процесс PID {pid}")

        def whitelist_callback(pid):
            try:
                name = next((p['name'] for p in processes if p['pid'] == pid), None)
                if name:
                    self.add_to_whitelist(name)
            except Exception as e:
                if logger:
                    logger.log("ERROR", f"Ошибка добавления в белый список: {e}")
                self.send_notification("Ошибка", "Не удалось добавить процесс в белый список.")

        try:
            dlg = ProcessAlertDialog(processes, kill_callback, whitelist_callback)
            dlg.exec_()
        except Exception as e:
            if logger:
                logger.log("ERROR", f"Ошибка при показе диалога: {e}")
            self.send_notification("Ошибка", "Не удалось открыть окно помощника. Смотрите error.log")

    # --- Обработчики меню ---
    def on_login(self, icon, item):
        if self.login("admin", "admin123!"):
            self.send_notification("Авторизация", "Вход выполнен успешно!")
            if logger:
                logger.log("INFO", "Выполнен вход")
        else:
            self.send_notification("Ошибка", "Неверные учетные данные")

    def on_generate_report(self, icon, item):
        if not self.session_token:
            self.send_notification("Требуется вход", "Сначала авторизуйтесь!")
            return
        self.generate_report("daily")

    def on_toggle_hud(self, icon, item):
        self.toggle_hud()

    def on_toggle_api(self, icon, item):
        self.toggle_api()

    def on_scan_now(self, icon, item):
        try:
            heavy = self.find_heavy_processes()
            if heavy:
                self.show_process_alert(heavy)
            else:
                self.send_notification("Сканирование", "Тяжёлых процессов не найдено.")
        except Exception as e:
            if logger:
                logger.log("ERROR", f"on_scan_now: {e}")
            self.send_notification("Ошибка", "Произошла ошибка при сканировании. Смотрите error.log")

    def show_main_window(self):
        if self.gui_dispatcher:
            self.gui_dispatcher.show_main_window_signal.emit()

    def _show_main_window_impl(self):
        if self.main_window is None:
            self.main_window = MainWindow(self)
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def on_show_stats(self, icon, item):
        stats_text = (
            f"📊 DevCleaner Pro Статистика\n"
            f"{'='*35}\n"
            f"🛑 Процессов убито: {self.stats['processes_killed']}\n"
            f"💾 Памяти освобождено: {self.stats['memory_freed_mb']:.0f} MB\n"
            f"🗑️ Кэша очищено: {self.stats['cache_cleaned_mb']:.0f} MB\n"
            f"📄 Отчетов создано: {self.stats['reports_generated']}\n"
            f"🤖 ML модель: {'Активна' if self.config['ml_enabled'] else 'Выкл'}\n"
            f"👤 Пользователь: {self.current_user.get('username', 'Не авторизован') if self.current_user else 'Не авторизован'}\n"
            f"🌐 API: {'ВКЛ' if self.api_server._running else 'ВЫКЛ'}"
        )
        self.send_notification("Статистика", stats_text)

    def on_exit(self, icon, item):
        self.running = False
        if logger:
            logger.log("INFO", "Завершение работы")
        self.logout()
        if self.hud_process:
            self.hud_process.terminate()
        if self.api_server._running:
            self.api_server.shutdown()
        icon.stop()
        if self.qt_app:
            self.qt_app.quit()

    def create_menu(self):
        return Menu(
            MenuItem('👤 Войти', self.on_login),
            MenuItem('📊 Статистика', self.on_show_stats, default=True),
            MenuItem('🖥️ Главное окно', self.show_main_window),
            MenuItem('🔍 Сканировать сейчас', self.on_scan_now),
            MenuItem('📄 Создать отчет', self.on_generate_report),
            MenuItem('📺 HUD с графиками', self.on_toggle_hud,
                     checked=lambda item: self.config.get('hud_enabled', False)),
            Menu.SEPARATOR,
            MenuItem('⚡ Лёгкий режим', self.toggle_light_mode,
                     checked=lambda item: self.light_mode),
            MenuItem('🌐 API Сервер', self.on_toggle_api,
                     checked=lambda item: self.api_server._running),
            Menu.SEPARATOR,
            MenuItem('❌ Выход', self.on_exit),
        )

    def setup_autostart(self):
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                exe_path = f'"{sys.executable}" "{os.path.abspath(__file__)}"'
            winreg.SetValueEx(key, "DevCleanerPro", 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(key)
            return True
        except Exception as e:
            if logger:
                logger.log("ERROR", f"Ошибка автозагрузки: {e}")
            return False

    def run(self):
        global logger
        logger = RotatingLogger(ERROR_LOG_DIR)
        logger.log("INFO", "=== Запуск DevCleaner Pro v8.3 ===")
        try:
            self.setup_autostart()
            self.login("admin", "admin123!")

            self.qt_app = QApplication.instance()
            if self.qt_app is None:
                self.qt_app = QApplication(sys.argv)

            self.gui_dispatcher = GuiDispatcher()
            self.gui_dispatcher.show_main_window_signal.connect(self._show_main_window_impl)
            self.gui_dispatcher.show_process_alert_signal.connect(self.show_process_alert)

            self.cpu_monitor.start()

            self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.monitor_thread.start()
            self.report_thread = threading.Thread(target=self.auto_report_loop, daemon=True)
            self.report_thread.start()
            threading.Thread(target=self.process_alert_loop, daemon=True).start()

            if self.config.get('hud_enabled', False):
                self.toggle_hud()
            if self.config.get('api_enabled', False):
                self.api_server.start()

            image = self.create_icon_image()
            self.icon = pystray.Icon(
                "DevCleanerPro",
                image,
                "DevCleaner Pro – Умный помощник",
                self.create_menu()
            )
            self.send_notification("DevCleaner Pro запущен", "Помощник активен")
            logger.log("INFO", "Иконка в трее создана")

            self.icon_thread = threading.Thread(target=self.icon.run, daemon=True)
            self.icon_thread.start()

            sys.exit(self.qt_app.exec_())
        except Exception as e:
            logger.log("ERROR", f"Критическая ошибка в run: {e}")
            raise


# --- Диалог с кнопкой «Запомнить» ---
class ProcessAlertDialog(QDialog):
    def __init__(self, processes, kill_callback, whitelist_callback, parent=None):
        super().__init__(parent)
        self.processes = processes
        self.kill_callback = kill_callback
        self.whitelist_callback = whitelist_callback
        self.checkboxes = []
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Завершить процессы?")
        self.setMinimumWidth(450)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Отметьте процессы для завершения. Кнопка «Запомнить» добавит в белый список."))
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        for proc in self.processes:
            cb = QCheckBox(f"{proc['name']} (PID {proc['pid']}) – {proc['memory_mb']:.0f} MB, {proc['cpu_percent']:.0f}% CPU")
            cb.setChecked(True)
            self.checkboxes.append(cb)
            scroll_layout.addWidget(cb)
        scroll_widget.setLayout(scroll_layout)
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        kill_btn = QPushButton("Завершить выбранные")
        kill_btn.clicked.connect(self.kill_selected)
        remember_btn = QPushButton("Запомнить (не убивать)")
        remember_btn.clicked.connect(self.remember_selected)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.close)
        btn_layout.addWidget(kill_btn)
        btn_layout.addWidget(remember_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def kill_selected(self):
        for cb, proc in zip(self.checkboxes, self.processes):
            if cb.isChecked():
                self.kill_callback(proc['pid'])
        self.close()

    def remember_selected(self):
        for cb, proc in zip(self.checkboxes, self.processes):
            if cb.isChecked():
                self.whitelist_callback(proc['pid'])
        self.close()


def main():
    mutex_name = "Global\\DevCleanerProSingleInstance"
    try:
        mutex = win32event.CreateMutex(None, False, mutex_name)
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            ctypes.windll.user32.MessageBoxW(0, "DevCleaner Pro уже запущен!", "Предупреждение", 0x30)
            sys.exit(0)
    except:
        pass

    app = DevCleanerPro()
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(0, f"Ошибка: {str(e)}", "DevCleaner Pro Error", 0x10)


if __name__ == "__main__":
    main()
