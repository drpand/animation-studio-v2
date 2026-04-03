"""
Лёгкий логгер с ротацией.
Хранит только последние 100 строк в logs/app.log.
"""
import os
import sys
from datetime import datetime
from collections import deque

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")
MAX_LINES = 100

# Кольцевой буфер в памяти
_buffer = deque(maxlen=MAX_LINES)


def _init():
    os.makedirs(LOG_DIR, exist_ok=True)
    # Загружаем последние строки из файла при старте
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    _buffer.append(line.rstrip("\n"))
        except Exception:
            pass


def _save():
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            for line in _buffer:
                f.write(line + "\n")
    except Exception:
        pass


def _log(level: str, msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    _buffer.append(line)
    _save()
    # Дублируем в stdout для отладки
    print(line, file=sys.stderr)


def info(msg: str):
    _log("INFO", msg)


def warn(msg: str):
    _log("WARN", msg)


def error(msg: str):
    _log("ERROR", msg)


def debug(msg: str):
    _log("DEBUG", msg)


# Инициализация при импорте
_init()
