# -*- coding: utf-8 -*-
"""
export/export.py — сборка статики (Часть 4 ТЗ, с учётом финальной архитектуры).

ВАЖНО, архитектура доставки данных менялась дважды (см. README и HANDOFF):

  - Раньше (не используется) — накопленная история раскладывалась по публичным
    JSON-шардам dist/data/XXX.json. От этого отказались: такие файлы легко
    перебрать скриптом (300-999 файлов) и вытащить всю базу без всякого логина.
  - Теперь — накопленная история отдаётся ТОЛЬКО поштучно, по одному номеру,
    серверной функцией, которая делает SELECT по одному номеру в Turso.
    Массовой выгрузки через сайт не существует в принципе.
    Наполнение базы делает отдельный скрипт export/turso_upload.py (шаг workflow).

РАСКЛАДКА dist/ ПОМЕНЯЛАСЬ (август 2026), при правках это главное:

    dist/
      wrangler.jsonc      <- конфиг деплоя, читается Cloudflare
      worker/index.js     <- серверная часть, маршрут GET /api/history/<номер>
      public/             <- ВСЯ статика сайта, и только она
        index.html
        meta.json
        static/{app.js,style.css}

Раньше всё лежало в корне dist/ плюс папка functions/ с маршрутизацией по имени
файла (формат Cloudflare Pages). Cloudflare убрал создание новых проектов Pages
из панели, поэтому переехали на обычный Worker со static assets.

Почему статика именно в public/, а не в корне: у Workers ассеты отдаются ДО кода,
и корнем ассетов становится ровно одна папка. Лежи статика в корне dist/ — в
публичные файлы уехали бы и wrangler.jsonc, и worker/. Адреса страниц при этом
НЕ изменились: public/ и есть корень сайта, значит /static/app.js и /meta.json
остались на прежних местах.

Что делает ИМЕННО ЭТОТ файл:
  1. Начисто пересобирает export/dist/ из export/dist_template/ — то, что
     публикуется в ветку gh-pages и оттуда деплоится Cloudflare.
     Никаких данных по конкретным машинам сюда не пишем.
  2. Пишет dist/public/meta.json — ТОЛЬКО агрегированные публичные цифры
     (сколько всего снимков, сколько машин покрыто, дата последнего сбора).
     Никакой информации по отдельным номерам в этом файле нет и не может быть —
     это просто счётчики, их публикация не даёт возможности узнать что-либо
     про конкретную машину.
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

    # dist/ пересобираем НАЧИСТО. Иначе файлы прошлой раскладки (когда статика
    # лежала в корне, а рядом была папка functions/) остались бы лежать здесь
    # и уехали бы в gh-pages вместе с новыми — мусор, который потом ищи.
    if os.path.isdir(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR, exist_ok=True)

    # копируем шаблон целиком: public/ (статика), worker/ (код), wrangler.jsonc
    # (конфиг деплоя). Данных по конкретным машинам тут нет ни в одном файле.
    if os.path.isdir(TEMPLATE_DIR):
        for item in os.listdir(TEMPLATE_DIR):
            src = os.path.join(TEMPLATE_DIR, item)
            dst = os.path.join(DIST_DIR, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

    # meta.json — в public/, потому что это публичный файл сайта: его читает
    # интерфейс по адресу /meta.json. В корне dist/ он до браузера не дошёл бы.
    public_dir = os.path.join(DIST_DIR, "public")
    os.makedirs(public_dir, exist_ok=True)
    with open(os.path.join(public_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[export] Готово: dist/ = {DIST_DIR} (агрегированные счётчики: "
          f"{meta['plates_covered']} машин, {meta['snapshots_count']} снимков). "
          f"Данные по конкретным машинам сюда не публикуются — см. export/turso_upload.py.")
    return {"ok": True, "dist_dir": DIST_DIR, "meta": meta}


if __name__ == "__main__":
    run()
