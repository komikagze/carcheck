# -*- coding: utf-8 -*-
"""
export/turso_upload.py — заливает накопленную историю по машинам в Turso
(облачный SQLite/libSQL), откуда её поштучно читает Cloudflare Pages Function
functions/api/history/[plate].js.

ПОЧЕМУ TURSO, А НЕ CLOUDFLARE KV (история вопроса, чтобы не наступить дважды):
раньше это был Cloudflare KV. На первом реальном прогоне выяснилось, что на
бесплатном тарифе KV разрешает всего 1000 операций записи В СУТКИ, а нам нужно
залить ~2.4 млн машин — то есть в тысячи раз больше. Дальше upstream просто
возвращал 429 и заливка падала. Перебрали варианты (см. README): Supabase и
Neon отпали по объёму (0.5 ГБ бесплатно, у нас уже ~350 МБ и растёт),
Cloudflare D1 подошёл бы, но там лимит 100 тыс. строк в сутки — первую заливку
пришлось бы растягивать на ~25 дней. У Turso бесплатно 5 ГБ, 10 млн записей
строк В МЕСЯЦ и 500 млн чтений — наши 2.4 млн заходят за один прогон.
Бонус: Turso — это буквально SQLite, тот же диалект, что и в локальной базе
сборщика, поэтому схема и запросы переносятся почти один в один.

АРХИТЕКТУРА ДОСТУПА (не поменялась):
данные лежат не публично перечислимыми файлами, а в базе, к которой у браузера
посетителя нет прямого доступа. Наружу торчит только Pages Function, которая
принимает ровно один номер за раз и не имеет способа отдать список/дамп всего.

ИНКРЕМЕНТАЛЬНОСТЬ:
в самой Turso лежит служебная таблица sync_state с отметкой времени последней
удачной заливки. Каждый прогон отправляет только те строки, что появились
позже этой отметки:
  - первый прогон: отметки нет -> уезжает всё (~2.4 млн строк, это укладывается
    в месячный лимит 10 млн);
  - последующие: уезжают только реально изменившиеся машины (их на порядки
    меньше), так что лимит не тратится впустую.

Требует две переменные окружения (GitHub Secrets):
  TURSO_DATABASE_URL   — вида https://<имя-базы>-<организация>.turso.io
                          (libsql://... тоже принимается, заменим схему сами)
  TURSO_AUTH_TOKEN     — токен базы (turso db tokens create <имя-базы>)
"""

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector import config as collector_config

# Сколько строк кладём в один INSERT ... VALUES (...),(...),... .
# У SQLite есть предел на число переменных в одном запросе (обычно 32766),
# при 5 колонках 1000 строк = 5000 переменных — с большим запасом.
ROWS_PER_STATEMENT = 1000
# Сколько таких INSERT-ов отправляем в одном HTTP-запросе к /v2/pipeline.
STATEMENTS_PER_REQUEST = 10

SCHEMA_STATEMENTS = [
    # plate — TEXT, ровно как в локальной базе сборщика (collector/db.py).
    # Специально не INTEGER: на первом прогоне мы уже ловили баг из-за
    # несовпадения типов в JOIN, второй раз наступать не будем.
    #
    # ВСЕ показания одометра с датой теста — по строке на каждый тест.
    # Сводку "последний / предыдущий + разница" сайт считает из этой же таблицы
    # на лету (первые две строки при сортировке по дате вниз), поэтому отдельной
    # плоской таблицы нет: одни и те же числа не должны лежать в базе дважды.
    """CREATE TABLE IF NOT EXISTS odometer (
        plate     TEXT NOT NULL,
        test_date TEXT NOT NULL,
        km        INTEGER,
        PRIMARY KEY (plate, test_date)
    )""",
    # Подробный журнал: "когда, что, было -> стало", одна строка на изменение.
    # local_id — id той же записи в локальной базе (field_changes.id): служит
    # ключом, поэтому повторная заливка одного и того же ничего не задваивает.
    # Отдельных таблиц под смену двигателя и аномалии нет намеренно — они
    # выводятся из этого же журнала (change_kind='anomaly', field='engine_no'),
    # чтобы не держать одни и те же факты в двух местах.
    """CREATE TABLE IF NOT EXISTS changes (
        local_id    INTEGER PRIMARY KEY,
        plate       TEXT NOT NULL,
        detected_at TEXT NOT NULL,
        change_kind TEXT NOT NULL,
        field       TEXT,
        field_label TEXT,
        old_value   TEXT,
        new_value   TEXT
    )""",
    # Поиск журнала всегда идёт по номеру машины — без этого индекса выборка
    # шла бы полным сканом по миллионам строк.
    "CREATE INDEX IF NOT EXISTS idx_changes_plate ON changes(plate, detected_at)",
    # Счётчик запросов по IP для рейт-лимита в Pages Function (раньше жил в KV).
    # minute отдельной колонкой, чтобы функция могла подчищать старые корзины
    # одним DELETE ... WHERE minute < ? (по составному ключу-строке так не выйдет).
    """CREATE TABLE IF NOT EXISTS rate_limit (
        bucket TEXT PRIMARY KEY,
        minute INTEGER NOT NULL,
        hits   INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS sync_state (
        k TEXT PRIMARY KEY,
        v TEXT NOT NULL
    )""",
    # У odometer PRIMARY KEY (plate, test_date) сам покрывает поиск по одному
    # plate (leftmost prefix) — отдельный индекс по plate был бы дублирующим,
    # ровно та же история, что мы уже разбирали в collector/db.py.
]


def _api_url(raw_url: str) -> str:
    """Приводит TURSO_DATABASE_URL к HTTP-виду. Turso отдаёт адрес как
    libsql://..., а HTTP API живёт на том же хосте по https://."""
    url = raw_url.strip().rstrip("/")
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    elif not url.startswith("http"):
        url = "https://" + url
    return url + "/v2/pipeline"


def _arg(value):
    """Значение -> типизированный аргумент Turso. Целые числа передаются
    строкой — так требует протокол (чтобы не терять точность i64)."""
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    return {"type": "text", "value": str(value)}


def pipeline(api_url: str, token: str, statements: list, timeout: int = 120) -> list:
    """Отправляет пачку SQL-запросов одним HTTP-вызовом.
    statements — список либо строк, либо кортежей (sql, [args...]).
    Возвращает список результатов (по одному на запрос)."""
    requests_payload = []
    for st in statements:
        if isinstance(st, str):
            stmt = {"sql": st}
        else:
            sql, args = st
            stmt = {"sql": sql, "args": [_arg(a) for a in args]}
        requests_payload.append({"type": "execute", "stmt": stmt})
    requests_payload.append({"type": "close"})

    body = json.dumps({"requests": requests_payload}).encode("utf-8")
    req = urllib.request.Request(api_url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = data.get("results", [])
    for r in results:
        if r.get("type") == "error":
            raise RuntimeError(f"Turso вернул ошибку: {r.get('error')}")
    return results


def get_sync_state(api_url: str, token: str) -> dict:
    """Отметки, до какого места залито в прошлый раз (пусто на первом прогоне)."""
    results = pipeline(api_url, token, [
        "SELECT k, v FROM sync_state",
    ])
    rows = results[0].get("response", {}).get("result", {}).get("rows", [])
    state = {}
    for row in rows:
        state[row[0].get("value")] = row[1].get("value")
    return state


def set_sync_state(api_url: str, token: str, updates: dict):
    statements = [
        ("INSERT INTO sync_state (k, v) VALUES (?, ?) "
         "ON CONFLICT(k) DO UPDATE SET v = excluded.v", [k, str(v)])
        for k, v in updates.items()
    ]
    if statements:
        pipeline(api_url, token, statements)


def collect_rows(conn, state: dict):
    """Собирает из локальной базы всё, что появилось после прошлой заливки.
    Возвращает dict: имя таблицы -> (колонки, список кортежей значений)."""
    # Все показания одометра. Отсекаем по времени, когда сборщик впервые их
    # увидел: каждую неделю уезжают только новые тесты, а не вся история заново.
    since_reading = state.get("last_reading_seen") or ""
    odometer = [
        (r[0], r[1], r[2]) for r in conn.execute(
            "SELECT plate, test_date, km FROM odometer_readings "
            "WHERE first_seen_at > ?", (since_reading,)
        )
    ]

    # Журнал изменений: отсекаем по id — надёжнее времени, т.к. id строго растёт
    # и не зависит от того, совпали ли метки времени внутри одного прогона.
    since_change_id = int(state.get("last_change_id") or 0)
    changes = [
        (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in conn.execute(
            "SELECT id, plate, detected_at, change_kind, field, field_label, old_value, new_value "
            "FROM field_changes WHERE id > ?", (since_change_id,)
        )
    ]

    return {
        "odometer": (["plate", "test_date", "km"], odometer),
        "changes": (["local_id", "plate", "detected_at", "change_kind",
                     "field", "field_label", "old_value", "new_value"], changes),
    }


def build_insert_statements(table: str, columns: list, rows: list) -> list:
    """Многострочные INSERT-ы: INSERT OR REPLACE INTO t (a,b) VALUES (?,?),(?,?)...
    OR REPLACE, а не OR IGNORE — чтобы повторная заливка тех же данных
    (например, после ручного перезапуска) обновляла, а не падала."""
    statements = []
    placeholder = "(" + ",".join(["?"] * len(columns)) + ")"
    cols_sql = ",".join(columns)
    for i in range(0, len(rows), ROWS_PER_STATEMENT):
        chunk = rows[i:i + ROWS_PER_STATEMENT]
        sql = (f"INSERT OR REPLACE INTO {table} ({cols_sql}) VALUES "
               + ",".join([placeholder] * len(chunk)))
        args = [v for row in chunk for v in row]
        statements.append((sql, args))
    return statements


def run(db_path: str = None):
    db_path = db_path or collector_config.DB_PATH

    raw_url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")

    missing = [name for name, val in [("TURSO_DATABASE_URL", raw_url),
                                       ("TURSO_AUTH_TOKEN", token)] if not val]
    if missing:
        print(f"[turso_upload] Не заданы переменные окружения: {', '.join(missing)}. "
              f"Пропускаю заливку (см. README -> GitHub Secrets). "
              f"Это не ошибка сборщика — просто интеграция ещё не настроена.")
        return {"ok": False, "reason": "missing_env", "missing": missing}

    if not os.path.exists(db_path):
        print(f"[turso_upload] База {db_path} не найдена — нечего заливать "
              f"(сборщик ещё ни разу не запускался).")
        return {"ok": False, "reason": "no_db"}

    api_url = _api_url(raw_url)

    print("[turso_upload] Создаю схему (если её ещё нет)...")
    pipeline(api_url, token, SCHEMA_STATEMENTS)

    state = get_sync_state(api_url, token)
    print(f"[turso_upload] Отметки прошлой заливки: {state or 'нет (первый прогон, зальём всё)'}")

    conn = sqlite3.connect(db_path)
    try:
        data = collect_rows(conn, state)
        # Новые отметки считаем по тому, что реально лежит в локальной базе.
        row = conn.execute("SELECT MAX(first_seen_at) FROM odometer_readings").fetchone()
        new_reading_seen = row[0] if row else None
        row = conn.execute("SELECT MAX(id) FROM field_changes").fetchone()
        new_change_id = row[0] if row else None
    finally:
        conn.close()

    total = sum(len(rows) for _, rows in data.values())
    if total == 0:
        print("[turso_upload] Новых данных с прошлой заливки нет — заливать нечего.")
        return {"ok": True, "uploaded": 0}

    for table, (columns, rows) in data.items():
        print(f"[turso_upload] {table}: {len(rows)} строк к заливке")

    uploaded = 0
    for table, (columns, rows) in data.items():
        if not rows:
            continue
        statements = build_insert_statements(table, columns, rows)
        for i in range(0, len(statements), STATEMENTS_PER_REQUEST):
            batch = statements[i:i + STATEMENTS_PER_REQUEST]
            try:
                pipeline(api_url, token, batch)
            except (urllib.error.URLError, RuntimeError) as e:
                print(f"[turso_upload] Ошибка заливки в {table} (пачка {i}): {e}")
                raise
            uploaded += sum(len(s[1]) // len(columns) for s in batch)
            print(f"[turso_upload] Залито {uploaded}/{total} строк...")

    # Отметки двигаем ТОЛЬКО после того, как все пачки реально уехали:
    # если заливка упадёт посередине, при следующем запуске мы честно начнём
    # с прошлой отметки и дошлём всё заново (INSERT OR REPLACE это переживёт).
    updates = {}
    if new_reading_seen:
        updates["last_reading_seen"] = new_reading_seen
    if new_change_id:
        updates["last_change_id"] = new_change_id
    if updates:
        set_sync_state(api_url, token, updates)
        print(f"[turso_upload] Отметки синхронизации обновлены: {updates}")

    print(f"[turso_upload] Готово: {uploaded} строк в Turso.")
    return {"ok": True, "uploaded": uploaded}


if __name__ == "__main__":
    result = run()
    if result.get("ok") is False and result.get("reason") not in ("missing_env", "no_db"):
        sys.exit(1)
