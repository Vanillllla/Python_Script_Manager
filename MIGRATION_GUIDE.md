# Миграция с Tkinter на PyQt6

## 📋 Обзор изменений

Проект успешно перенесен с **tkinter** на **PyQt6**. Это модернизация фреймворка, которая приносит:

✅ Современный и профессиональный UI  
✅ Лучшая производительность  
✅ Улучшенная поддержка системного трея  
✅ Более активная разработка и обновления  
✅ Лучшая кроссплатформенность  

---

## 🔄 Выбор между версиями

### PyQt5 vs PyQt6

**Мы выбрали PyQt6** по следующим причинам:

| Критерий | PyQt5 | PyQt6 | 
|----------|-------|-------|
| **Поддержка** | Устаревает | ✅ Активная |
| **Новые возможности** | Ограничены | ✅ Расширены |
| **Python 3.12+** | ❌ Проблемы | ✅ Полная поддержка |
| **Производительность** | Хорошая | ✅ Лучше |
| **Qt версия** | Qt5 | Qt6 (новейшая) |

---

## 📦 Установка

### 1. Обновите зависимости

```bash
pip install -r requirements.txt
```

Или установите вручную:

```bash
pip install PyQt6 PyQt6-sip psutil Pillow pystray pywin32
```

### 2. Запустите новую версию

```bash
python main_pyqt6.py
```

**Старая версия (tkinter) остается доступной:**

```bash
python main.py
```

---

## 🔧 Ключевые изменения в коде

### Импорты

**Старо (tkinter):**
```python
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
```

**Ново (PyQt6):**
```python
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QProgressBar, QTreeWidget, ...
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QFont
```

### Структура приложения

**tkinter:**
```python
root = tk.Tk()
app = ScriptManagerTkinter(root)
root.mainloop()
```

**PyQt6:**
```python
app = QApplication(sys.argv)
window = ScriptManagerPyQt6()
window.show()
sys.exit(app.exec())
```

### Диалоги

**tkinter:**
```python
messagebox.showinfo("Заголовок", "Сообщение")
path = filedialog.askopenfilename()
```

**PyQt6:**
```python
QMessageBox.information(self, "Заголовок", "Сообщение")
path, _ = QFileDialog.getOpenFileName(self, "...", "")
```

### Потоки

**tkinter:**
```python
threading.Thread(target=function, daemon=True).start()
```

**PyQt6:**
```python
class WorkerThread(QThread):
    signal = pyqtSignal(str)
    def run(self):
        self.signal.emit("data")

worker = WorkerThread()
worker.signal.connect(handler)
worker.start()
```

---

## 🎨 Особенности интерфейса PyQt6

### 1. Системный трей

Полная поддержка контекстного меню:
- Развернуть окно
- Закрыть приложение
- Двойной клик для развертывания

### 2. Консоль

Улучшенный интерфейс консоли с:
- Лучшей визуализацией
- Поддержкой цветов
- Более плавной прокруткой

### 3. Мониторинг

Перезапроектирован с использованием потоков PyQt6:
- Более отзывчивый UI
- Нет "зависаний"
- Плавные обновления графиков

---

## 🐛 Различия в функциональности

### Что осталось прежним

✅ Управление скриптами (запуск/остановка)  
✅ Мониторинг ресурсов (CPU, память)  
✅ Интерактивная консоль  
✅ Система автозапуска  
✅ Работа в системном трее  
✅ Обработка ошибок  
✅ Темы оформления  
✅ JSON сохранение состояния  

### Улучшено

✨ Более современный UI  
✨ Лучшая обработка событий  
✨ Оптимизированное использование памяти  
✨ Более надежная система потоков  
✨ Правильная обработка сигналов  

### Известные особенности

⚠️ Темы реализованы более просто (без полной поддержки стилей PyQt6, но функционально эквивалентны)  
⚠️ Иконки в системном трее загружаются более сложно (создается временный PNG файл)  

---

## 📊 Архитектура PyQt6 версии

### Классы и компоненты

```
ScriptManagerPyQt6 (QMainWindow)
├── ConsoleDialog
├── ErrorDialog
├── SettingsDialog
├── RenameDialog
├── ScriptMonitorThread (QThread)
└── MonitoringThread (QThread)
```

### Сигналы (Signals)

- `pyqtSignal` для межпроцессного взаимодействия
- Асинхронные обновления UI
- Безопасная работа с потоками

---

## 🚀 Запуск и использование

### Развертывание как EXE

Для создания EXE используйте PyInstaller с PyQt6:

```bash
pyinstaller --onefile --windowed main_pyqt6.py
```

### Отладка

```bash
python main_pyqt6.py  # с выводом консоли
pythonw main_pyqt6.py  # без консоли (Windows)
```

---

## 📝 Рекомендации

1. **Тестирование**: Рекомендуется тестировать обе версии перед переходом
2. **Обратная совместимость**: Данные (JSON файлы) полностью совместимы
3. **Python версия**: Используйте Python 3.8+ (рекомендуется 3.10+)
4. **Производительность**: PyQt6 использует больше памяти, но обеспечивает лучший UI

---

## 🔗 Полезные ссылки

- [PyQt6 Документация](https://www.riverbankcomputing.com/static/Docs/PyQt6/)
- [PyQt6 Примеры](https://github.com/baoboa/pyqt6-examples)
- [Qt6 Документация](https://doc.qt.io/qt-6/)

---

## ❓ FAQ

**Q: Должен ли я переходить на PyQt6?**  
A: Рекомендуется для новых проектов. Текущая версия полностью рабочая.

**Q: Будет ли поддерживаться tkinter версия?**  
A: Да, обе версии будут поддерживаться параллельно.

**Q: Какая версия лучше?**  
A: PyQt6 современнее и надежнее, tkinter проще для редакции.

---

**Версия документации**: 1.0  
**Дата обновления**: 2025-12-13
