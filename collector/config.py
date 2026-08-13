# -*- coding: utf-8 -*-
"""
collector/config.py — настройки сборщика. Можно переопределить переменными окружения,
но по умолчанию всё работает "из коробки" при запуске run_collector.bat.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # корень carcheck/

DB_PATH = os.environ.get("CARCHECK_DB", os.path.join(BASE_DIR, "collector", "db", "carcheck.sqlite3"))
ARCHIVE_DIR = os.environ.get("CARCHECK_ARCHIVE", os.path.join(BASE_DIR, "collector", "archive"))
LOG_DIR = os.environ.get("CARCHECK_LOGS", os.path.join(BASE_DIR, "collector", "logs"))

# Слаг пакета, где лежат оба "жирных" ресурса, которые мы копим (history + ownership).
SHINUI_MIVNE_SLUG = "shinui_mivne"

# Быть вежливыми к серверу: тайм-аут на скачивание одного файла (секунды).
DOWNLOAD_TIMEOUT = 60 * 30  # 30 минут — файлы по 150-170 МБ, сеть может быть небыстрой
DOWNLOAD_CHUNK = 1024 * 1024  # 1 МБ на чанк при потоковом скачивании

# Сколько строк грузим в staging за один executemany
BATCH_SIZE = 5000
