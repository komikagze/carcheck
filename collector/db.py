# -*- coding: utf-8 -*-
"""
collector/db.py — схема SQLite и вспомогательные функции подключения.

Схема соответствует Части 1 ТЗ (BRIEF.md), с уточнениями:
- staging: временная таблица для сырых строк CSV перед диффом (пересоздаётся при каждом прогоне).
- current_state: текущее состояние по каждой машине (для JOIN-диффа, а не python-словаря).
- history: пишем строку ТОЛЬКО когда что-то реально изменилось.
- ownership: дедуп по (plate, baalut_dt, baalut).
- engine_changes: флагманская фича — смена номера двигателя между снимками.
- odometer_anomalies: показание пробега уменьшилось между снимками -> вероятная скрутка.
- snapshots / meta_archive: журнал снятых снимков и архив метаданных package_show.

Все операции идут в транзакциях: если процесс убьют посередине, sqlite либо
целиком применит изменения, либо целиком откатит (WAL + один writer).
"""

import os
import sqlite3
import contextlib

from . import config


SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id   TEXT NOT NULL,
    taken_at      TEXT NOT NULL,             -- ISO datetime снятия снимка
    source_url    TEXT NOT NULL,             -- url ресурса, взятый из package_show
    last_modified TEXT,                       -- last_modified, который вернул package_show
    sha256        TEXT NOT NULL,
    row_count     INTEGER NOT NULL,
    file_path     TEXT NOT NULL,              -- относительный путь к archive/<resource_id>/<дата>.csv.gz
    UNIQUE(resource_id, sha256)
);

CREATE TABLE IF NOT EXISTS current_state (
    plate              TEXT PRIMARY KEY,
    km                 INTEGER,
    engine_no          TEXT,
    shinui_mivne_ind   INTEGER,
    gapam_ind          INTEGER,
    shnui_zeva_ind     INTEGER,
    shinui_zmig_ind    INTEGER,
    mkoriut_nm         TEXT,
    rishum_rishon_dt   TEXT,
    snapshot_id        INTEGER NOT NULL,
    updated_at         TEXT NOT NULL,
    FOREIGN KEY(snapshot_id) REFERENCES snapshots(snapshot_id)
);

CREATE TABLE IF NOT EXISTS history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    plate          TEXT NOT NULL,
    snapshot_id    INTEGER NOT NULL,
    km             INTEGER,
    engine_no      TEXT,
    changed_fields TEXT NOT NULL,   -- JSON-список изменившихся полей, например ["km","engine_no"]
    detected_at    TEXT NOT NULL,
    FOREIGN KEY(snapshot_id) REFERENCES snapshots(snapshot_id)
);
-- один составной индекс (plate, detected_at) покрывает и поиск "по номеру",
-- и "по номеру + сортировка по дате" — отдельный индекс только по plate был
-- бы избыточен (leftmost prefix того же составного индекса), поэтому его нет.
CREATE INDEX IF NOT EXISTS idx_history_plate_time ON history(plate, detected_at);

CREATE TABLE IF NOT EXISTS ownership (
    plate               TEXT NOT NULL,
    baalut_dt           TEXT,
    baalut               TEXT,
    first_seen_snapshot INTEGER NOT NULL,
    PRIMARY KEY (plate, baalut_dt, baalut),
    FOREIGN KEY(first_seen_snapshot) REFERENCES snapshots(snapshot_id)
);
-- отдельного индекса по plate нет намеренно: PRIMARY KEY (plate, baalut_dt, baalut)
-- уже покрывает поиск по одному plate (leftmost prefix) — дублирующий индекс
-- на миллионах строк заметно раздувал бы файл БД без всякой пользы для запросов
-- (обнаружено на первом реальном прогоне).

CREATE TABLE IF NOT EXISTS engine_changes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    plate            TEXT NOT NULL,
    old_engine       TEXT,
    new_engine       TEXT,
    detected_at      TEXT NOT NULL,
    km_at_change     INTEGER,
    prev_snapshot_id INTEGER NOT NULL,
    new_snapshot_id  INTEGER NOT NULL,
    FOREIGN KEY(prev_snapshot_id) REFERENCES snapshots(snapshot_id),
    FOREIGN KEY(new_snapshot_id) REFERENCES snapshots(snapshot_id)
);
CREATE INDEX IF NOT EXISTS idx_engine_changes_plate ON engine_changes(plate);

CREATE TABLE IF NOT EXISTS odometer_anomalies (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    plate            TEXT NOT NULL,
    prev_km          INTEGER NOT NULL,
    new_km           INTEGER NOT NULL,
    detected_at      TEXT NOT NULL,
    prev_snapshot_id INTEGER NOT NULL,
    new_snapshot_id  INTEGER NOT NULL,
    FOREIGN KEY(prev_snapshot_id) REFERENCES snapshots(snapshot_id),
    FOREIGN KEY(new_snapshot_id) REFERENCES snapshots(snapshot_id)
);
CREATE INDEX IF NOT EXISTS idx_odometer_anomalies_plate ON odometer_anomalies(plate);

-- Текущее состояние полей ОСНОВНОГО РЕЕСТРА по каждой машине (цвет, VIN, тип
-- владения, топливо, модель двигателя, код модели). Отдельно от current_state
-- намеренно: та таблица живёт по данным ресурса history и обновляется своим
-- проходом, а смешивать два источника в одной строке — верный способ,
-- чтобы один затирал поля другого.
CREATE TABLE IF NOT EXISTS current_state_main (
    plate        TEXT PRIMARY KEY,
    tzeva_rechev TEXT,
    misgeret     TEXT,
    baalut       TEXT,
    sug_delek_nm TEXT,
    degem_manoa  TEXT,
    degem_cd     TEXT,
    degem_nm     TEXT,
    updated_at   TEXT NOT NULL
);

-- Показания одометра с ПРИВЯЗКОЙ К ДАТЕ ТЕСТА (а не к дате нашего прогона).
-- Собирается join-ом ресурса history (там километраж) и основного реестра
-- (там mivchan_acharon_dt — дата теста); поодиночке ни один из них полной
-- картины не даёт. PRIMARY KEY (plate, test_date) + INSERT OR IGNORE делают
-- накопление идемпотентным: каждый тест попадает в историю ровно один раз,
-- сколько бы раз сборщик ни запускался.
CREATE TABLE IF NOT EXISTS odometer_readings (
    plate         TEXT NOT NULL,
    test_date     TEXT NOT NULL,   -- дата теста по данным Минтранса (YYYY-MM-DD)
    km            INTEGER,
    first_seen_at TEXT NOT NULL,   -- когда наш сборщик впервые увидел эту запись
    PRIMARY KEY (plate, test_date)
);

-- Подробный журнал изменений: одна строка на КАЖДОЕ изменившееся поле,
-- с человекочитаемым названием поля и значениями "было -> стало".
-- Таблицы history/engine_changes/odometer_anomalies выше хранят только новые
-- значения и сам факт изменения; здесь же — полная понятная летопись, из
-- которой видно "когда, что и как поменялось" без расшифровки JSON-полей.
-- change_kind: 'new_car'  — машина впервые появилась в базе (поля пустые),
--              'changed'  — у уже известной машины изменилось конкретное поле.
CREATE TABLE IF NOT EXISTS field_changes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    plate        TEXT NOT NULL,
    detected_at  TEXT NOT NULL,
    snapshot_id  INTEGER NOT NULL,
    change_kind  TEXT NOT NULL,
    field        TEXT,
    field_label  TEXT,
    old_value    TEXT,
    new_value    TEXT,
    FOREIGN KEY(snapshot_id) REFERENCES snapshots(snapshot_id)
);
CREATE INDEX IF NOT EXISTS idx_field_changes_plate ON field_changes(plate, detected_at);

CREATE TABLE IF NOT EXISTS meta_archive (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_slug     TEXT NOT NULL,
    taken_at         TEXT NOT NULL,
    package_show_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meta_archive_slug ON meta_archive(dataset_slug, taken_at);

CREATE TABLE IF NOT EXISTS run_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL DEFAULT 'running',  -- running|ok|error
    message     TEXT
);
"""


def get_connection(db_path: str = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # isolation_level=None -> автокоммит-режим python-модуля sqlite3 отключён от
    # неявного управления транзакциями; транзакциями управляем сами явным BEGIN
    # IMMEDIATE / COMMIT / ROLLBACK в transaction() ниже. Это исключает конфликт
    # "cannot start a transaction within a transaction" при смешивании DDL и DML.
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection):
    with conn:
        conn.executescript(SCHEMA_SQL)


def backfill_initial_changes(conn: sqlite3.Connection) -> int:
    """Одноразовая досыпка журнала изменений для машин, которые попали в базу
    ДО появления таблицы field_changes (у нас это первый реальный прогон —
    2.4 млн машин уехали в current_state, когда журнала ещё не существовало).

    Без этого в журнале была бы дыра: машины есть, а записи "когда добавлена" нет.
    Выполняется только если журнал пуст, а current_state — нет, поэтому
    повторные запуски ничего не дублируют."""
    already = conn.execute("SELECT 1 FROM field_changes LIMIT 1").fetchone()
    if already:
        return 0
    has_state = conn.execute("SELECT 1 FROM current_state LIMIT 1").fetchone()
    if not has_state:
        return 0

    with transaction(conn):
        cur = conn.execute("""
            INSERT INTO field_changes
                (plate, detected_at, snapshot_id, change_kind, field, field_label, old_value, new_value)
            SELECT plate, updated_at, snapshot_id, 'new_car', NULL, NULL, NULL, NULL
            FROM current_state
        """)
        return cur.rowcount


@contextlib.contextmanager
def transaction(conn: sqlite3.Connection):
    """Явный контекст транзакции. sqlite3 в Python уже открывает неявную
    транзакцию на первый INSERT/UPDATE, но явный BEGIN IMMEDIATE снижает
    риск гонки при параллельном доступе (например, сервер читает в этот момент)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
