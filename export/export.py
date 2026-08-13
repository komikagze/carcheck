# -*- coding: utf-8 -*-
"""
export/export.py — сборка статики (Часть 4 ТЗ, с учётом финальной архитектуры).

ВАЖНО, архитектура доставки данных поменялась в процессе (см. README, раздел
"Деплой: Cloudflare Pages + Pages Functions + KV"):

  - Раньше (не используется) — накопленная история раскладывалась по публичным
    JSON-шардам dist/data/XXX.json. От этого отказались: такие файлы легко
    перебрать скриптом (300-999 файлов) и вытащить всю базу без всякого логина.
  - Теперь — накопленная история отдаётся ТОЛЬКО поштучно, по одному номеру,
    через Cloudflare Pages Function (functions/api/history/[plate].js), которая
    читает Cloudflare KV. Массовой выгрузки через сайт не существует в принципе.
    Наполнение KV делает отдельный скрипт export/kv_upload.py (шаг workflow).

Что делает ИМЕННО ЭТОТ файл:
  1. Копирует статический интерфейс (export/dist_template/*, включая
     functions/api/history/[plate].js) в export/dist/ — то, что публикуется как
     сайт на Cloudflare Pages. Никаких данных по конкретным машинам сюда не пишем.
  2. Пишет dist/meta.json — ТОЛЬКО агрегированные публичные цифры (сколько всего
     снимков, сколько машин покрыто, дата последнего сбора). Никакой информации
     по отдельным номерам в этом файле нет и не может быть — это просто счётчики,
     их публикация не даёт возможности узнать что-либо про конкретную машину.

Наполнение Cloudflare KV данными по машинам — в export/kv_upload.py, это
отдельный шаг того же workflow, выполняется после этого скрипта.
"""

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector import config as collector_config

EXPORT_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(EXPORT_DIR, "dist")
TEMPLATE_DIR = os.path.join(EXPORT_DIR, "dist_template")


def run(db_path: str = None):
    db_path = db_path or collector_config.DB_PATH

    meta = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "snapshots_count": 0,
        "last_snapshot_at": None,
        "plates_covered": 0,
        "db_found": os.path.exists(db_path),
    }

    if meta["db_found"]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            snap = conn.execute("SELECT COUNT(*) AS c, MAX(taken_at) AS last FROM snapshots").fetchone()
            plates = conn.execute("SELECT COUNT(*) AS c FROM current_state").fetchone()
            meta["snapshots_count"] = snap["c"]
            meta["last_snapshot_at"] = snap["last"]
            meta["plates_covered"] = plates["c"]
        finally:
            conn.close()
    else:
        print(f"[export] База {db_path} не найдена — публикую сайт без счётчиков "
              f"(сборщик ещё ни разу не запускался).")

    os.makedirs(DIST_DIR, exist_ok=True)

    # копируем статический интерфейс + functions/ поверх (не data-файлов конкретных машин тут нет)
    if os.path.isdir(TEMPLATE_DIR):
        for item in os.listdir(TEMPLATE_DIR):
            src = os.path.join(TEMPLATE_DIR, item)
            dst = os.path.join(DIST_DIR, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

    with open(os.path.join(DIST_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[export] Готово: dist/ = {DIST_DIR} (агрегированные счётчики: "
          f"{meta['plates_covered']} машин, {meta['snapshots_count']} снимков). "
          f"Данные по конкретным машинам сюда не публикуются — см. export/kv_upload.py.")
    return {"ok": True, "dist_dir": DIST_DIR, "meta": meta}


if __name__ == "__main__":
    run()
