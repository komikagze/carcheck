# -*- coding: utf-8 -*-
"""
collector/meta.py — работа с package_show: получение реального списка ресурсов
датасета (URL, last_modified, размер, hash) и скачивание файла.

ВАЖНО (грабли из BRIEF.md): URL для скачивания CSV нельзя угадывать/собирать руками
вида "/datastore/dump/<id>" — такого эндпоинта нет. Единственный надёжный способ —
взять готовый url из ответа package_show -> resources[].url.

Путь /api/3/action/ и /api/action/ ведут себя по-разному на разных методах:
для datastore_search подтверждён /api/action/, для package_show и package_list —
/api/3/action/. Здесь используется именно /api/3/action/package_show.
"""

import hashlib
import json
import os
import time
import urllib.request
import urllib.error

from shared.refdata import API_BASE_V3
from . import config

USER_AGENT = "carcheck-collector/1.0 (personal use, github.com/local)"


def package_show(slug: str) -> dict:
    """Возвращает распарсенный JSON ответа package_show для датасета slug.
    Бросает исключение, если success != true."""
    url = f"{API_BASE_V3}/package_show?id={slug}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("success"):
        raise RuntimeError(f"package_show({slug}) вернул success=false: {data}")
    return data["result"]


def find_resource(package_result: dict, resource_id: str) -> dict:
    """Находит нужный ресурс в resources[] по id. Бросает исключение, если не нашли —
    значит министерство переименовало/удалило ресурс, и надо разбираться руками,
    а не гадать новый ID."""
    for res in package_result.get("resources", []):
        if res.get("id") == resource_id:
            return res
    raise RuntimeError(
        f"Ресурс {resource_id} не найден в package_show. "
        f"Доступные ресурсы: {[r.get('id') for r in package_result.get('resources', [])]}"
    )


def download_file(url: str, dest_path: str, timeout: int = None) -> tuple:
    """Потоково скачивает файл, считая sha256 на лету. Возвращает (sha256_hex, size_bytes).
    Не читает файл целиком в память — критично для файлов по 150-170 МБ."""
    timeout = timeout or config.DOWNLOAD_TIMEOUT
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    sha256 = hashlib.sha256()
    size = 0
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp_path = dest_path + ".part"
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp_path, "wb") as out:
        while True:
            chunk = resp.read(config.DOWNLOAD_CHUNK)
            if not chunk:
                break
            sha256.update(chunk)
            out.write(chunk)
            size += len(chunk)
    os.replace(tmp_path, dest_path)
    return sha256.hexdigest(), size


def retry(fn, attempts=3, delay=5, *args, **kwargs):
    """Простой ретрай на случай временного сбоя сети/сервера. Быть вежливыми —
    не долбим параллельно, ждём delay секунд между попытками."""
    last_err = None
    for i in range(attempts):
        try:
            return fn(*args, **kwargs)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            if i < attempts - 1:
                time.sleep(delay)
    raise last_err
