import sys
import subprocess
import psutil
import os
import json
import threading
import time
from datetime import datetime
import uuid
import shutil
import winreg
import webbrowser
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QTreeWidget, QTreeWidgetItem,
    QDialog, QLineEdit, QCheckBox, QFileDialog, QMessageBox,
    QTextEdit, QFrame, QComboBox, QTabWidget, QSpinBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QIcon, QColor, QFont, QTextCursor
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QPixmap, QImage
from PIL import Image, ImageDraw
import winshell
from win32com.client import Dispatch


# ====================== UTILITY FUNCTIONS ======================

def find_system_python():
    """Находит системный интерпретатор Python"""
    try:
        registry_paths = [
            (winreg.HKEY_CURRENT_USER, r"Software\Python\PythonCore"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Python\PythonCore"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\Python\PythonCore")
        ]

        for hive, path in registry_paths:
            try:
                with winreg.OpenKey(hive, path) as key:
                    i = 0
                    while True:
                        try:
                            version = winreg.EnumKey(key, i)
                            try:
                                with winreg.OpenKey(hive, f"{path}\\{version}\\InstallPath") as install_key:
                                    install_path, _ = winreg.QueryValueEx(install_key, "")
                                    python_exe = os.path.join(install_path, "python.exe")
                                    if os.path.exists(python_exe):
                                        return python_exe
                            except:
                                pass
                            i += 1
                        except WindowsError:
                            break
            except:
                pass
    except:
        pass

    return sys.executable


def get_base_path():
    """Определяет базовый путь для работы с файлами"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


BASE_PATH = get_base_path()

# ====================== THEMES ======================

THEMES = {
    "light": {
        "bg": "#ffffff",
        "fg": "#000000",
        "frame_bg": "#f0f0f0",
        "button_bg": "#e0e0e0",
        "button_fg": "#000000",
        "console_bg": "#ffffff",
        "console_fg": "#000000",
    },
    "dark": {
        "bg": "#2d2d30",
        "fg": "#ffffff",
        "frame_bg": "#3e3e42",
        "button_bg": "#007acc",
        "button_fg": "#ffffff",
        "console_bg": "#0c0c0c",
        "console_fg": "#00ff00",
    }
}

# ====================== DIALOGS ======================

class ConsoleDialog(QDialog):
    def __init__(self, parent, script_name, process, theme="light"):
        super().__init__(parent)
        self.script_name = script_name
        self.process = process
        self.theme = theme
        self.colors = THEMES.get(theme, THEMES["light"])

        self.setWindowTitle(f"Консоль: {script_name}")
        self.setGeometry(100, 100, 800, 600)
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Output area
        output_label = QLabel("Вывод консоли:")
        layout.addWidget(output_label)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setStyleSheet(
            f"background-color: {self.colors['console_bg']}; color: {self.colors['console_fg']};"
        )
        layout.addWidget(self.output_text)

        # Input area
        input_layout = QHBoxLayout()
        input_label = QLabel("Ввод:")
        input_layout.addWidget(input_label)

        self.input_field = QLineEdit()
        self.input_field.returnPressed.connect(self.send_input)
        input_layout.addWidget(self.input_field)

        send_btn = QPushButton("Отправить")
        send_btn.clicked.connect(self.send_input)
        input_layout.addWidget(send_btn)

        layout.addLayout(input_layout)

        # Buttons
        buttons_layout = QHBoxLayout()
        clear_btn = QPushButton("Очистить вывод")
        clear_btn.clicked.connect(self.clear_output)
        buttons_layout.addWidget(clear_btn)

        buttons_layout.addStretch()

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.close)
        buttons_layout.addWidget(close_btn)

        layout.addLayout(buttons_layout)

        self.setLayout(layout)

    def clear_output(self):
        self.output_text.clear()

    def send_input(self):
        input_text = self.input_field.text()
        if input_text and self.process and self.process.poll() is None:
            try:
                encoded_input = (input_text + '\n').encode('utf-8')
                self.process.stdin.write(encoded_input)
                self.process.stdin.flush()

                self.append_text(f"> {input_text}\n")
                self.input_field.clear()
            except Exception as e:
                self.append_text(f"Ошибка ввода: {str(e)}\n")

    def append_text(self, text):
        """Безопасное добавление текста в текстовое поле"""
        cursor = self.output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.output_text.setTextCursor(cursor)

    def load_historical_output(self, historical_output):
        """Загружает исторический вывод при открытии консоли"""
        if historical_output:
            self.append_text(historical_output)


class ErrorDialog(QDialog):
    def __init__(self, parent, script_name, error_message, theme="light"):
        super().__init__(parent)
        self.script_name = script_name
        self.error_message = error_message
        self.theme = theme
        self.colors = THEMES.get(theme, THEMES["light"])

        self.setWindowTitle("Ошибка скрипта")
        self.setGeometry(100, 100, 700, 500)
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Script info
        script_label = QLabel("Скрипт:")
        script_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(script_label)

        script_name_label = QLabel(self.script_name)
        layout.addWidget(script_name_label)

        # Time info
        time_label = QLabel("Время ошибки:")
        time_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(time_label)

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_value_label = QLabel(current_time)
        layout.addWidget(time_value_label)

        # Error message
        error_label = QLabel("Текст ошибки:")
        error_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(error_label)

        self.error_text = QTextEdit()
        self.error_text.setReadOnly(True)
        self.error_text.setPlainText(self.error_message)
        layout.addWidget(self.error_text)

        # Buttons
        buttons_layout = QHBoxLayout()

        copy_btn = QPushButton("Копировать ошибку")
        copy_btn.clicked.connect(self.copy_error)
        buttons_layout.addWidget(copy_btn)

        buttons_layout.addStretch()

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.close)
        buttons_layout.addWidget(close_btn)

        layout.addLayout(buttons_layout)

        self.setLayout(layout)

    def copy_error(self):
        """Копирует текст ошибки в буфер обмена"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.error_message)
        QMessageBox.information(self, "Успех", "Ошибка скопирована в буфер обмена")


class SettingsDialog(QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Настройки Python Script Manager (PSM)")
        self.setGeometry(100, 100, 500, 400)
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Autostart
        self.autostart_cb = QCheckBox("Запускать Python Script Manager (PSM) при старте системы")
        self.autostart_cb.setChecked(self.settings.get('autostart', False))
        self.autostart_cb.stateChanged.connect(self.toggle_autostart)
        layout.addWidget(self.autostart_cb)

        # Performance monitoring
        self.monitoring_cb = QCheckBox("Включить мониторинг производительности")
        self.monitoring_cb.setChecked(self.settings.get('performance_monitoring', True))
        layout.addWidget(self.monitoring_cb)

        # Interpreter
        interpreter_label = QLabel("Интерпретатор по умолчанию:")
        layout.addWidget(interpreter_label)

        interpreter_layout = QHBoxLayout()
        self.interpreter_input = QLineEdit()
        self.interpreter_input.setText(self.settings.get('default_interpreter', sys.executable))
        interpreter_layout.addWidget(self.interpreter_input)

        browse_btn = QPushButton("Обзор")
        browse_btn.clicked.connect(self.browse_interpreter)
        interpreter_layout.addWidget(browse_btn)

        layout.addLayout(interpreter_layout)

        # Packages button
        packages_btn = QPushButton("Показать установленные пакеты")
        packages_btn.clicked.connect(self.show_packages)
        layout.addWidget(packages_btn)

        layout.addStretch()

        # Dialog buttons
        buttons_layout = QHBoxLayout()

        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self.save_settings)
        buttons_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        layout.addLayout(buttons_layout)

        self.setLayout(layout)

    def toggle_autostart(self):
        """Включение/выключение автозапуска"""
        try:
            startup_folder = winshell.startup()
            shortcut_path = os.path.join(startup_folder, "Python Script Manager (PSM).lnk")

            if self.autostart_cb.isChecked():
                if getattr(sys, 'frozen', False):
                    target_path = sys.executable
                    working_dir = os.path.dirname(sys.executable)
                    args = ""
                else:
                    target_path = sys.executable
                    script_path = os.path.abspath(sys.argv[0])
                    working_dir = os.path.dirname(script_path)
                    args = f'"{script_path}"'

                shell = Dispatch('WScript.Shell')
                shortcut = shell.CreateShortCut(shortcut_path)
                shortcut.Targetpath = target_path
                if args:
                    shortcut.Arguments = args
                shortcut.WorkingDirectory = working_dir
                shortcut.save()

                self.settings['autostart'] = True
            else:
                if os.path.exists(shortcut_path):
                    os.remove(shortcut_path)
                self.settings['autostart'] = False

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось настроить автозапуск: {str(e)}")
            self.autostart_cb.setChecked(not self.autostart_cb.isChecked())

    def browse_interpreter(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите интерпретатор Python",
            "",
            "Executable files (*.exe);;All files (*.*)"
        )
        if path:
            self.interpreter_input.setText(path)

    def show_packages(self):
        interpreter = self.interpreter_input.text()
        if not os.path.exists(interpreter):
            QMessageBox.critical(self, "Ошибка", "Указанный интерпретатор не найден")
            return

        try:
            result = subprocess.run([
                interpreter, "-m", "pip", "list"
            ], capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                packages_window = QDialog(self)
                packages_window.setWindowTitle("Установленные пакеты")
                packages_window.setGeometry(100, 100, 600, 400)

                layout = QVBoxLayout()
                text_widget = QTextEdit()
                text_widget.setReadOnly(True)
                text_widget.setPlainText(result.stdout)
                layout.addWidget(text_widget)

                packages_window.setLayout(layout)
                packages_window.exec()
            else:
                QMessageBox.critical(self, "Ошибка", f"Не удалось получить список пакетов:\n{result.stderr}")

        except subprocess.TimeoutExpired:
            QMessageBox.critical(self, "Ошибка", "Таймаут при получении списка пакетов")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при получении списка пакетов: {str(e)}")

    def save_settings(self):
        self.settings['autostart'] = self.autostart_cb.isChecked()
        self.settings['default_interpreter'] = self.interpreter_input.text()
        self.settings['performance_monitoring'] = self.monitoring_cb.isChecked()
        self.accept()


class RenameDialog(QDialog):
    def __init__(self, parent, current_name):
        super().__init__(parent)
        self.current_name = current_name
        self.result = None

        self.setWindowTitle("Переименовать скрипт")
        self.setGeometry(100, 100, 400, 150)
        
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        label = QLabel("Новое имя скрипта:")
        layout.addWidget(label)

        self.name_input = QLineEdit()
        self.name_input.setText(self.current_name)
        self.name_input.selectAll()
        layout.addWidget(self.name_input)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self.save_name)
        buttons_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        layout.addLayout(buttons_layout)

        self.setLayout(layout)

    def save_name(self):
        new_name = self.name_input.text().strip()
        if new_name:
            self.result = new_name
            self.accept()


# ====================== WORKER THREADS ======================

class ScriptMonitorThread(QThread):
    """Поток для мониторинга вывода скрипта"""
    output_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int)

    def __init__(self, process):
        super().__init__()
        self.process = process

    def run(self):
        try:
            while self.process.poll() is None:
                try:
                    raw_line = self.process.stdout.readline()
                    if raw_line:
                        decoded_line = self.decode_bytes(raw_line)
                        self.output_signal.emit(decoded_line)
                    else:
                        time.sleep(0.1)
                except Exception as e:
                    print(f"Ошибка чтения stdout: {e}")
                    break

            # Читаем оставшиеся данные
            remaining_stdout, remaining_stderr = self.process.communicate(timeout=2)
            if remaining_stdout:
                self.output_signal.emit(self.decode_bytes(remaining_stdout))
            if remaining_stderr:
                self.error_signal.emit(self.decode_bytes(remaining_stderr))

            self.finished_signal.emit(self.process.returncode)

        except Exception as e:
            self.error_signal.emit(f"Ошибка: {str(e)}")

    @staticmethod
    def decode_bytes(byte_data):
        """Декодирует байты с обработкой ошибок"""
        try:
            return byte_data.decode('utf-8')
        except UnicodeDecodeError:
            try:
                return byte_data.decode('cp1251')
            except UnicodeDecodeError:
                return byte_data.decode('utf-8', errors='replace')


class MonitoringThread(QThread):
    """Поток для мониторинга ресурсов"""
    update_signal = pyqtSignal(dict)

    def __init__(self, script_pids):
        super().__init__()
        self.script_pids = script_pids
        self.is_running = True

    def run(self):
        while self.is_running:
            try:
                total_cpu = 0
                total_memory = 0

                for script_uuid, pid in list(self.script_pids.items()):
                    if pid:
                        try:
                            process = psutil.Process(pid)
                            cpu = process.cpu_percent(interval=0.1)
                            memory = process.memory_percent()

                            self.update_signal.emit({
                                'type': 'script',
                                'uuid': script_uuid,
                                'cpu': cpu,
                                'memory': memory
                            })

                            total_cpu += cpu
                            total_memory += memory
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            self.update_signal.emit({
                                'type': 'script',
                                'uuid': script_uuid,
                                'cpu': 0,
                                'memory': 0
                            })

                total_cpu = min(psutil.cpu_percent(interval=0.1), 100)
                total_memory = min(total_memory, 100)

                self.update_signal.emit({
                    'type': 'total',
                    'cpu': total_cpu,
                    'memory': total_memory
                })

                time.sleep(1)
            except Exception as e:
                print(f"Ошибка мониторинга: {e}")
                time.sleep(1)

    def stop(self):
        self.is_running = False


# ====================== MAIN APPLICATION ======================

class ScriptManagerPyQt6(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Python Script Manager (PSM)")
        self.setGeometry(100, 100, 1200, 800)

        self.current_theme = "light"
        self.active_scripts = []
        self.saved_scripts = {}
        self.script_frames = {}
        self.process_output_buffers = {}
        self.open_consoles = {}
        self.script_pids = {}
        self.error_messages = {}

        self.scripts_file = os.path.join(BASE_PATH, "scripts.json")
        self.settings_file = os.path.join(BASE_PATH, "settings.json")
        self.settings = {}

        self.monitoring_thread = None

        self.load_settings()
        self.load_scripts()
        self.init_ui()
        self.setup_tray_icon()
        self.start_monitoring()

    def init_ui(self):
        """Инициализирует пользовательский интерфейс"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout()

        # Left side - active scripts
        left_layout = QVBoxLayout()

        system_label = QLabel("Общая нагрузка (сумма всех скриптов):")
        system_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        left_layout.addWidget(system_label)

        # CPU monitoring
        cpu_layout = QHBoxLayout()
        cpu_layout.addWidget(QLabel("CPU:"))
        self.total_cpu_bar = QProgressBar()
        self.total_cpu_bar.setMaximum(100)
        cpu_layout.addWidget(self.total_cpu_bar)
        self.total_cpu_label = QLabel("0%")
        cpu_layout.addWidget(self.total_cpu_label)
        left_layout.addLayout(cpu_layout)

        # Memory monitoring
        memory_layout = QHBoxLayout()
        memory_layout.addWidget(QLabel("Память:"))
        self.total_memory_bar = QProgressBar()
        self.total_memory_bar.setMaximum(100)
        memory_layout.addWidget(self.total_memory_bar)
        self.total_memory_label = QLabel("0%")
        memory_layout.addWidget(self.total_memory_label)
        left_layout.addLayout(memory_layout)

        scripts_label = QLabel("Активные скрипты:")
        scripts_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        left_layout.addWidget(scripts_label)

        self.scripts_container = QWidget()
        self.scripts_layout = QVBoxLayout()
        self.scripts_layout.addStretch()
        self.scripts_container.setLayout(self.scripts_layout)

        self.scripts_scroll = QVBoxLayout()
        self.scripts_scroll.addWidget(self.scripts_container)

        left_layout.addLayout(self.scripts_scroll, 1)

        # Right side - saved scripts
        right_layout = QVBoxLayout()

        catalog_label = QLabel("КАТАЛОГ СКРИПТОВ")
        catalog_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        right_layout.addWidget(catalog_label)

        # Buttons for catalog
        buttons_layout = QHBoxLayout()

        add_btn = QPushButton("Добавить")
        add_btn.clicked.connect(self.add_script)
        buttons_layout.addWidget(add_btn)

        delete_btn = QPushButton("Удалить")
        delete_btn.clicked.connect(self.delete_script)
        buttons_layout.addWidget(delete_btn)

        rename_btn = QPushButton("Переименовать")
        rename_btn.clicked.connect(self.rename_script)
        buttons_layout.addWidget(rename_btn)

        show_file_btn = QPushButton("Показать файл")
        show_file_btn.clicked.connect(self.show_script_file)
        buttons_layout.addWidget(show_file_btn)

        right_layout.addLayout(buttons_layout)

        # Scripts tree
        self.scripts_tree = QTreeWidget()
        self.scripts_tree.setHeaderLabels(["Скрипты", "Статус", "Автозапуск"])
        self.scripts_tree.setColumnCount(3)
        self.scripts_tree.itemDoubleClicked.connect(self.on_tree_double_click)
        right_layout.addWidget(self.scripts_tree)

        # Layouts composition
        main_layout.addLayout(left_layout, 2)
        main_layout.addLayout(right_layout, 1)

        central_widget.setLayout(main_layout)

        # Menu bar
        self.create_menu_bar()

        self.apply_theme(self.current_theme)

    def create_menu_bar(self):
        """Создает панель меню"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("ФАЙЛ")
        file_menu.addAction("Настройки", self.open_settings)
        file_menu.addSeparator()
        file_menu.addAction("Свернуть в трей", self.hide_to_tray)
        file_menu.addAction("Закрыть", self.quit_application)

        # View menu
        view_menu = menubar.addMenu("ВИД")
        view_menu.addAction("Светлая тема", lambda: self.change_theme("light"))
        view_menu.addAction("Тёмная тема", lambda: self.change_theme("dark"))

        # Help menu
        help_menu = menubar.addMenu("СПРАВКА")
        help_menu.addAction("Информация", self.show_info)
        help_menu.addAction("Репозиторий GitHub", self.open_github)

    def apply_theme(self, theme_name):
        """Применяет выбранную тему"""
        self.current_theme = theme_name
        # Реализация применения темы к стилям PyQt6
        pass

    def setup_tray_icon(self):
        """Создает иконку в системном трее"""
        try:
            image = Image.new('RGB', (64, 64), color='white')
            dc = ImageDraw.Draw(image)
            dc.rectangle([16, 16, 48, 48], fill='blue')
            dc.text((25, 25), 'PSM', fill='white')

            # Сохраняем временно изображение
            temp_icon_path = os.path.join(BASE_PATH, "temp_icon.png")
            image.save(temp_icon_path)

            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setIcon(QIcon(temp_icon_path))

            tray_menu = QMenu(self)
            tray_menu.addAction("Развернуть окно", self.show_from_tray)
            tray_menu.addAction("Закрыть", self.quit_application)

            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self.on_tray_activated)
            self.tray_icon.show()

        except Exception as e:
            print(f"Ошибка создания иконки в трее: {e}")

    def on_tray_activated(self, reason):
        """Обработчик активации иконки в трее"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_from_tray()

    def hide_to_tray(self):
        """Скрывает окно в трей"""
        self.hide()

    def show_from_tray(self):
        """Показывает окно из трея"""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def change_theme(self, theme_name):
        """Изменяет тему приложения"""
        self.current_theme = theme_name
        self.apply_theme(theme_name)
        self.settings['theme'] = theme_name
        self.save_settings()

    def open_settings(self):
        """Открывает диалог настроек"""
        dialog = SettingsDialog(self, self.settings)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.save_settings()

    def show_info(self):
        """Показывает информацию о программе"""
        info_text = """Python Script Manager (PSM) - менеджер для управления Python-скриптами

Версия: 2.0 (PyQt6)
Разработчик: Vanillllla

Основные возможности:
• Запуск и остановка Python-скриптов
• Мониторинг потребления ресурсов (CPU, память)
• Интерактивная консоль для взаимодействия со скриптами
• Каталог скриптов с возможностью группировки
• Темная и светлая темы оформления
• Автозапуск скриптов при старте программы
• Работа в системном трее
• Обработка и отображение ошибок

Использование:
1. Добавьте скрипты через кнопку 'Добавить' в каталоге
2. Активируйте скрипты двойным кликом или через меню
3. Запускайте/останавливайте скрипты кнопками в основном окне
4. Используйте консоль для взаимодействия с запущенными скриптами
5. Настройте автозапуск в настройках скрипта"""

        QMessageBox.information(self, "Информация о программе", info_text)

    def open_github(self):
        """Открывает репозиторий GitHub в браузере"""
        try:
            webbrowser.open("https://github.com/Vanillllla/Python_Script_Manager")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть браузер: {str(e)}")

    def load_settings(self):
        """Загружает настройки из JSON файла"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    self.settings = json.load(f)
            else:
                self.settings = {
                    'theme': 'light',
                    'performance_monitoring': True,
                    'autostart': False,
                    'default_interpreter': find_system_python()
                }
                self.save_settings()

            saved_theme = self.settings.get('theme', 'light')
            self.current_theme = saved_theme

        except Exception as e:
            print(f"Ошибка загрузки настроек: {str(e)}")
            self.settings = {
                'theme': 'light',
                'performance_monitoring': True,
                'autostart': False,
                'default_interpreter': find_system_python()
            }

    def save_settings(self):
        """Сохраняет настройки в JSON файл"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Ошибка сохранения настроек: {str(e)}")

    def load_scripts(self):
        """Загружает скрипты из JSON файла"""
        try:
            if os.path.exists(self.scripts_file):
                with open(self.scripts_file, 'r', encoding='utf-8') as f:
                    loaded_scripts = json.load(f)

                self.saved_scripts.clear()
                self.active_scripts.clear()

                for script_uuid, script_info in loaded_scripts.items():
                    self.saved_scripts[script_uuid] = script_info

                    if script_info.get('is_active', False):
                        self.active_scripts.append(script_uuid)

                    if script_info.get('autostart', False):
                        if script_uuid not in self.active_scripts:
                            self.active_scripts.append(script_uuid)
                        self.root.after(1000, lambda s=script_uuid: self.start_script(s))

            self.update_scripts_ui()

        except Exception as e:
            print(f"Ошибка загрузки скриптов: {str(e)}")

    def save_scripts(self):
        """Сохраняет скрипты в JSON файл"""
        try:
            scripts_to_save = {}
            for script_uuid, script_info in self.saved_scripts.items():
                script_copy = script_info.copy()
                script_copy['is_active'] = script_uuid in self.active_scripts
                scripts_to_save[script_uuid] = script_copy

            with open(self.scripts_file, 'w', encoding='utf-8') as f:
                json.dump(scripts_to_save, f, indent=4, ensure_ascii=False)

        except Exception as e:
            print(f"Ошибка сохранения скриптов: {str(e)}")

    def update_scripts_ui(self):
        """Обновляет UI всех скриптов"""
        # Очищаем текущие фреймы
        for i in reversed(range(self.scripts_layout.count() - 1)):
            self.scripts_layout.itemAt(i).widget().setParent(None)

        # Создаем фреймы для активных скриптов
        for script_uuid in self.active_scripts:
            self.create_script_frame(script_uuid)

        self.update_scripts_tree()

    def create_script_frame(self, script_uuid):
        """Создает фрейм для активного скрипта"""
        script_info = self.saved_scripts.get(script_uuid)
        if not script_info:
            return

        display_name = script_info.get('display_name', script_info['name'])

        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout()

        # Header
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(display_name))
        header_layout.addStretch()

        self.script_frames[script_uuid] = {
            'frame': frame,
            'toggle_btn': None,
            'console_btn': None,
            'cpu_label': None,
            'memory_label': None,
            'process': None,
            'is_running': False
        }

        layout.addLayout(header_layout)

        # Control buttons
        controls_layout = QHBoxLayout()

        toggle_btn = QPushButton("Запуск")
        toggle_btn.clicked.connect(lambda: self.toggle_script(script_uuid))
        controls_layout.addWidget(toggle_btn)

        console_btn = QPushButton("Консоль")
        console_btn.setEnabled(False)
        console_btn.clicked.connect(lambda: self.open_console(script_uuid))
        controls_layout.addWidget(console_btn)

        config_btn = QPushButton("Настройки")
        config_btn.clicked.connect(lambda: self.configure_script(script_uuid))
        controls_layout.addWidget(config_btn)

        remove_btn = QPushButton("Удалить из активных")
        remove_btn.clicked.connect(lambda: self.remove_from_active(script_uuid))
        controls_layout.addWidget(remove_btn)

        self.script_frames[script_uuid]['toggle_btn'] = toggle_btn
        self.script_frames[script_uuid]['console_btn'] = console_btn

        layout.addLayout(controls_layout)

        # Resource monitoring
        cpu_layout = QHBoxLayout()
        cpu_layout.addWidget(QLabel("CPU:"))
        cpu_bar = QProgressBar()
        cpu_bar.setMaximum(100)
        cpu_layout.addWidget(cpu_bar)
        cpu_label = QLabel("0%")
        cpu_layout.addWidget(cpu_label)

        memory_layout = QHBoxLayout()
        memory_layout.addWidget(QLabel("Память:"))
        memory_bar = QProgressBar()
        memory_bar.setMaximum(100)
        memory_layout.addWidget(memory_bar)
        memory_label = QLabel("0%")
        memory_layout.addWidget(memory_label)

        self.script_frames[script_uuid]['cpu_label'] = cpu_label
        self.script_frames[script_uuid]['memory_label'] = memory_label

        layout.addLayout(cpu_layout)
        layout.addLayout(memory_layout)

        frame.setLayout(layout)

        # Вставляем перед stretch элементом
        self.scripts_layout.insertWidget(self.scripts_layout.count() - 1, frame)

    def toggle_script(self, script_uuid):
        """Переключает состояние скрипта"""
        if script_uuid in self.script_frames:
            if self.script_frames[script_uuid]['is_running']:
                self.stop_script(script_uuid)
            else:
                self.start_script(script_uuid)

    def start_script(self, script_uuid):
        """Запускает скрипт"""
        script_info = self.saved_scripts.get(script_uuid)
        if not script_info:
            return

        try:
            if not os.path.exists(script_info['path']):
                QMessageBox.critical(self, "Ошибка", f"Файл {script_info['path']} не найден")
                return

            interpreter = script_info['interpreter']
            if not os.path.exists(interpreter):
                interpreter = find_system_python()
                script_info['interpreter'] = interpreter

            process = subprocess.Popen([
                interpreter,
                script_info['path']
            ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                bufsize=0,
                universal_newlines=False)

            if script_uuid in self.script_frames:
                self.script_frames[script_uuid]['process'] = process
                self.script_frames[script_uuid]['is_running'] = True
                self.script_frames[script_uuid]['toggle_btn'].setText("Остановить")
                self.script_frames[script_uuid]['console_btn'].setEnabled(True)

            self.script_pids[script_uuid] = process.pid
            self.process_output_buffers[script_uuid] = ""

            # Мониторим вывод в отдельном потоке
            monitor = ScriptMonitorThread(process)
            monitor.output_signal.connect(lambda text, uuid=script_uuid: self.on_script_output(uuid, text))
            monitor.error_signal.connect(lambda text, uuid=script_uuid: self.on_script_error(uuid, text))
            monitor.finished_signal.connect(lambda code, uuid=script_uuid: self.on_script_finished(uuid, code))
            monitor.start()

            self.update_scripts_tree()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось запустить скрипт: {str(e)}")

    def stop_script(self, script_uuid):
        """Останавливает скрипт"""
        if script_uuid in self.script_frames and self.script_frames[script_uuid]['process']:
            try:
                process = self.script_frames[script_uuid]['process']
                process.terminate()
                process.wait(timeout=5)
            except:
                try:
                    process.kill()
                except:
                    pass

            self.script_frames[script_uuid]['process'] = None
            self.script_frames[script_uuid]['is_running'] = False
            self.script_frames[script_uuid]['toggle_btn'].setText("Запуск")
            self.script_frames[script_uuid]['console_btn'].setEnabled(False)

            self.update_scripts_tree()

    def open_console(self, script_uuid):
        """Открывает консоль для скрипта"""
        script_info = self.saved_scripts.get(script_uuid)
        if not script_info or script_uuid not in self.script_frames:
            return

        if script_uuid in self.open_consoles:
            try:
                self.open_consoles[script_uuid].raise_()
                self.open_consoles[script_uuid].activateWindow()
                return
            except:
                del self.open_consoles[script_uuid]

        display_name = script_info.get('display_name', script_info['name'])
        process = self.script_frames[script_uuid]['process']

        console = ConsoleDialog(self, display_name, process, self.current_theme)
        if script_uuid in self.process_output_buffers:
            console.load_historical_output(self.process_output_buffers[script_uuid])

        self.open_consoles[script_uuid] = console
        console.exec()

        if script_uuid in self.open_consoles:
            del self.open_consoles[script_uuid]

    def on_script_output(self, script_uuid, text):
        """Обработчик вывода скрипта"""
        if script_uuid in self.process_output_buffers:
            self.process_output_buffers[script_uuid] += text
        else:
            self.process_output_buffers[script_uuid] = text

        if script_uuid in self.open_consoles:
            self.open_consoles[script_uuid].append_text(text)

    def on_script_error(self, script_uuid, text):
        """Обработчик ошибок скрипта"""
        self.on_script_output(script_uuid, text)

    def on_script_finished(self, script_uuid, return_code):
        """Обработчик завершения скрипта"""
        if script_uuid in self.script_frames:
            self.script_frames[script_uuid]['is_running'] = False
            self.script_frames[script_uuid]['toggle_btn'].setText("Запуск")
            self.script_frames[script_uuid]['console_btn'].setEnabled(False)

            if script_uuid in self.script_pids:
                del self.script_pids[script_uuid]

            if return_code != 0:
                error_output = self.process_output_buffers.get(script_uuid, "")
                if error_output:
                    self.show_error_dialog(script_uuid, f"Скрипт завершился с ошибкой (код: {return_code})\n\n{error_output}")

            self.update_scripts_tree()

    def show_error_dialog(self, script_uuid, error_message):
        """Показывает диалог ошибки"""
        script_info = self.saved_scripts.get(script_uuid)
        if not script_info:
            return

        script_name = script_info.get('display_name', script_info['name'])
        dialog = ErrorDialog(self, script_name, error_message, self.current_theme)
        dialog.exec()

    def add_script(self):
        """Добавляет новый скрипт"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите Python скрипт",
            "",
            "Python files (*.py);;All files (*.*)"
        )

        if path:
            script_name = os.path.basename(path).replace('.py', '')
            script_uuid = str(uuid.uuid4())

            script_info = {
                'uuid': script_uuid,
                'name': script_name,
                'display_name': script_name,
                'path': path,
                'interpreter': self.settings.get('default_interpreter', find_system_python()),
                'autostart': False
            }

            self.saved_scripts[script_uuid] = script_info
            self.active_scripts.append(script_uuid)

            self.create_script_frame(script_uuid)
            self.update_scripts_tree()
            self.save_scripts()

    def delete_script(self):
        """Удаляет скрипт"""
        selected_items = self.scripts_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Предупреждение", "Выберите скрипт для удаления")
            return

        item = selected_items[0]
        parent = item.parent()

        if not parent:
            return

        script_name = item.text(0)

        script_uuid = None
        for uuid, info in self.saved_scripts.items():
            if info.get('display_name', info['name']) == script_name:
                script_uuid = uuid
                break

        if not script_uuid:
            return

        if QMessageBox.question(self, "Подтверждение",
                               f"Вы уверены, что хотите удалить скрипт '{script_name}'?") == QMessageBox.StandardButton.Yes:
            if script_uuid in self.active_scripts:
                self.remove_from_active(script_uuid)

            del self.saved_scripts[script_uuid]
            self.update_scripts_tree()
            self.save_scripts()

    def rename_script(self):
        """Переименовывает скрипт"""
        selected_items = self.scripts_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Предупреждение", "Выберите скрипт для переименования")
            return

        item = selected_items[0]
        parent = item.parent()

        if not parent:
            return

        script_name = item.text(0)

        script_uuid = None
        for uuid, info in self.saved_scripts.items():
            if info.get('display_name', info['name']) == script_name:
                script_uuid = uuid
                break

        if not script_uuid:
            return

        script_info = self.saved_scripts[script_uuid]
        current_name = script_info.get('display_name', script_info['name'])

        dialog = RenameDialog(self, current_name)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result:
            script_info['display_name'] = dialog.result
            self.update_scripts_tree()
            self.save_scripts()

    def show_script_file(self):
        """Показывает файл скрипта в проводнике"""
        selected_items = self.scripts_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Предупреждение", "Выберите скрипт")
            return

        item = selected_items[0]
        parent = item.parent()

        if not parent:
            return

        script_name = item.text(0)

        script_uuid = None
        for uuid, info in self.saved_scripts.items():
            if info.get('display_name', info['name']) == script_name:
                script_uuid = uuid
                break

        if not script_uuid:
            return

        script_info = self.saved_scripts[script_uuid]
        script_path = script_info['path']
        folder_path = os.path.dirname(script_path)

        if os.path.exists(folder_path):
            try:
                os.startfile(folder_path)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось открыть папку: {str(e)}")

    def configure_script(self, script_uuid):
        """Открывает диалог настроек скрипта"""
        script_info = self.saved_scripts.get(script_uuid)
        if not script_info:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Настройки: {script_info.get('display_name', script_info['name'])}")
        dialog.setGeometry(100, 100, 500, 350)

        layout = QVBoxLayout()

        # Display name
        layout.addWidget(QLabel("Отображаемое имя:"))
        name_input = QLineEdit()
        name_input.setText(script_info.get('display_name', script_info['name']))
        layout.addWidget(name_input)

        # Interpreter
        layout.addWidget(QLabel("Интерпретатор:"))
        interpreter_layout = QHBoxLayout()
        interpreter_input = QLineEdit()
        interpreter_input.setText(script_info['interpreter'])
        interpreter_layout.addWidget(interpreter_input)

        browse_btn = QPushButton("Обзор")
        browse_btn.clicked.connect(lambda: self.browse_interpreter_dialog(interpreter_input))
        interpreter_layout.addWidget(browse_btn)
        layout.addLayout(interpreter_layout)

        # Packages button
        packages_btn = QPushButton("Показать установленные пакеты")
        packages_btn.clicked.connect(lambda: self.show_script_packages(interpreter_input.text()))
        layout.addWidget(packages_btn)

        # Autostart
        autostart_cb = QCheckBox("Запускать скрипт при старте программы")
        autostart_cb.setChecked(script_info.get('autostart', False))
        layout.addWidget(autostart_cb)

        layout.addStretch()

        # Dialog buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        save_btn = QPushButton("Сохранить")
        def save_config():
            script_info['display_name'] = name_input.text()
            script_info['interpreter'] = interpreter_input.text()
            script_info['autostart'] = autostart_cb.isChecked()
            self.update_scripts_tree()
            self.save_scripts()
            dialog.accept()

        save_btn.clicked.connect(save_config)
        buttons_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(dialog.reject)
        buttons_layout.addWidget(cancel_btn)

        layout.addLayout(buttons_layout)

        dialog.setLayout(layout)
        dialog.exec()

    def browse_interpreter_dialog(self, input_field):
        """Открывает диалог выбора интерпретатора"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите интерпретатор Python",
            "",
            "Executable files (*.exe);;All files (*.*)"
        )
        if path:
            input_field.setText(path)

    def show_script_packages(self, interpreter):
        """Показывает установленные пакеты"""
        if not interpreter or not os.path.exists(interpreter):
            interpreter = find_system_python()

        if not os.path.exists(interpreter):
            QMessageBox.critical(self, "Ошибка", "Интерпретатор Python не найден")
            return

        try:
            result = subprocess.run([
                interpreter, "-m", "pip", "list"
            ], capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                packages_window = QDialog(self)
                packages_window.setWindowTitle("Установленные пакеты")
                packages_window.setGeometry(100, 100, 600, 400)

                layout = QVBoxLayout()
                text_widget = QTextEdit()
                text_widget.setReadOnly(True)
                text_widget.setPlainText(result.stdout)
                layout.addWidget(text_widget)

                packages_window.setLayout(layout)
                packages_window.exec()
            else:
                QMessageBox.critical(self, "Ошибка", f"Не удалось получить список пакетов:\n{result.stderr}")

        except subprocess.TimeoutExpired:
            QMessageBox.critical(self, "Ошибка", "Таймаут при получении списка пакетов")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка: {str(e)}")

    def remove_from_active(self, script_uuid):
        """Удаляет скрипт из активных"""
        if script_uuid in self.script_frames:
            if self.script_frames[script_uuid]['is_running']:
                self.stop_script(script_uuid)

            self.script_frames[script_uuid]['frame'].setParent(None)
            del self.script_frames[script_uuid]

        if script_uuid in self.active_scripts:
            self.active_scripts.remove(script_uuid)

        self.update_scripts_tree()
        self.save_scripts()

    def on_tree_double_click(self, item, column):
        """Обработчик двойного клика по дереву"""
        parent = item.parent()

        if not parent:
            return

        script_name = item.text(0)
        parent_text = parent.text(0)

        script_uuid = None
        for uuid, info in self.saved_scripts.items():
            if info.get('display_name', info['name']) == script_name:
                script_uuid = uuid
                break

        if not script_uuid:
            return

        if parent_text == "Активные скрипты":
            if QMessageBox.question(self, "Подтверждение",
                                   f"Переместить '{script_name}' в неактивные?") == QMessageBox.StandardButton.Yes:
                self.remove_from_active(script_uuid)
        elif parent_text == "Неактивные скрипты":
            self.active_scripts.append(script_uuid)
            self.create_script_frame(script_uuid)
            self.update_scripts_tree()
            self.save_scripts()

    def update_scripts_tree(self):
        """Обновляет дерево скриптов"""
        self.scripts_tree.clear()

        # Active scripts
        active_node = QTreeWidgetItem(["Активные скрипты"])
        for script_uuid in self.active_scripts:
            script_info = self.saved_scripts.get(script_uuid)
            if script_info:
                display_name = script_info.get('display_name', script_info['name'])
                status = "Запущен" if (script_uuid in self.script_frames and self.script_frames[script_uuid]['is_running']) else "Остановлен"
                autostart_status = "Автозапуск" if script_info.get('autostart', False) else ""
                item = QTreeWidgetItem([display_name, status, autostart_status])
                active_node.addChild(item)

        self.scripts_tree.addTopLevelItem(active_node)
        active_node.setExpanded(True)

        # Inactive scripts
        inactive_node = QTreeWidgetItem(["Неактивные скрипты"])
        for script_uuid, script_info in self.saved_scripts.items():
            if script_uuid not in self.active_scripts:
                display_name = script_info.get('display_name', script_info['name'])
                autostart_status = "Автозапуск" if script_info.get('autostart', False) else ""
                item = QTreeWidgetItem([display_name, "Неактивен", autostart_status])
                inactive_node.addChild(item)

        self.scripts_tree.addTopLevelItem(inactive_node)
        inactive_node.setExpanded(True)

    def start_monitoring(self):
        """Запускает мониторинг ресурсов"""
        if self.settings.get('performance_monitoring', True):
            self.monitoring_thread = MonitoringThread(self.script_pids)
            self.monitoring_thread.update_signal.connect(self.on_monitoring_update)
            self.monitoring_thread.start()

    def on_monitoring_update(self, data):
        """Обработчик обновления мониторинга"""
        if data['type'] == 'script':
            script_uuid = data['uuid']
            if script_uuid in self.script_frames:
                self.script_frames[script_uuid]['cpu_label'].setText(f"{data['cpu']:.1f}%")
                self.script_frames[script_uuid]['memory_label'].setText(f"{data['memory']:.1f}%")
        elif data['type'] == 'total':
            self.total_cpu_bar.setValue(int(data['cpu']))
            self.total_cpu_label.setText(f"{data['cpu']:.1f}%")
            self.total_memory_bar.setValue(int(data['memory']))
            self.total_memory_label.setText(f"{data['memory']:.1f}%")

    def quit_application(self):
        """Завершает приложение"""
        self.save_scripts()
        self.save_settings()

        if self.monitoring_thread:
            self.monitoring_thread.stop()
            self.monitoring_thread.wait()

        for script_uuid in list(self.script_frames.keys()):
            if self.script_frames[script_uuid]['is_running']:
                self.stop_script(script_uuid)

        QApplication.quit()

    def closeEvent(self, event):
        """Обработчик закрытия окна"""
        if self.tray_icon and self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            self.quit_application()


# ====================== MAIN ======================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ScriptManagerPyQt6()
    window.show()
    sys.exit(app.exec())
