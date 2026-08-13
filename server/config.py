# -*- coding: utf-8 -*-
"""
server/config.py — настройки локального веб-сервера.

Порт и хост вынесены в переменные окружения (Часть 4 ТЗ):
  CARCHECK_HOST — по умолчанию 0.0.0.0 (слушать все интерфейсы, нужно для Tailscale)
  CARCHECK_PORT — по умолчанию 8000
  CARCHECK_TOKEN — токен доступа. Если не задан переменной окружения, генерируется
                   один раз и сохраняется в server/secret_token.txt рядом с этим файлом,
                   чтобы при следующих запусках токен не менялся (иначе пришлось бы
                   каждый раз перезакладывать телефон в закладки).
"""

import os
import secrets

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # корень carcheck/

HOST = os.environ.get("CARCHECK_HOST", "0.0.0.0")
PORT = int(os.environ.get("CARCHECK_PORT", "8000"))

DB_PATH = os.environ.get("CARCHECK_DB", os.path.join(BASE_DIR, "collector", "db", "carcheck.sqlite3"))

_TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secret_token.txt")


def _load_or_create_token() -> str:
    env_token = os.environ.get("CARCHECK_TOKEN")
    if env_token:
        return env_token
    if os.path.exists(_TOKEN_FILE):
        with open(_TOKEN_FILE, "r", encoding="utf-8") as f:
            existing = f.read().strip()
            if existing:
                return existing
    new_token = secrets.token_urlsafe(18)
    with open(_TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(new_token)
    return new_token


ACCESS_TOKEN = _load_or_create_token()

# Ключ для подписи cookie-сессии Flask (запоминаем, что токен уже вводили,
# чтобы не таскать ?token=... в каждой ссылке). Тоже стабилен между запусками.
_SECRET_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secret_flask_key.txt")


def _load_or_create_secret_key() -> str:
    if os.path.exists(_SECRET_KEY_FILE):
        with open(_SECRET_KEY_FILE, "r", encoding="utf-8") as f:
            existing = f.read().strip()
            if existing:
                return existing
    new_key = secrets.token_hex(32)
    with open(_SECRET_KEY_FILE, "w", encoding="utf-8") as f:
        f.write(new_key)
    return new_key


FLASK_SECRET_KEY = _load_or_create_secret_key()

# Можно временно отключить авторизацию для отладки на localhost: CARCHECK_AUTH_DISABLED=1
AUTH_DISABLED = os.environ.get("CARCHECK_AUTH_DISABLED") == "1"

HTTP_TIMEOUT = 12  # секунд на один запрос к data.gov.il
MAX_WORKERS = 8    # параллельных запросов к госбазам на один поиск номера
