# -*- coding: utf-8 -*-
"""
collector/collector.py — точка входа сборщика. Запускается run_collector.bat
(или вручную: `python collector/collector.py` из корня carcheck/) раз в неделю
через Планировщик заданий Windows.

Алгоритм (см. Часть 1 BRIEF.md; ОБНОВЛЕНО после первого реального прогона — см.
collector/api_loader.py про то, почему шаг 3 теперь не скачивание CSV):
  1. package_show(shinui_mivne) -> реальные url/last_modified для двух ресурсов,
     которые мы копим: history (56063a99...) и ownership (bb2355dc...). url
     сейчас используется только для записи в snapshots.source_url (для справки),
     сами данные тянутся через JSON API — см. пункт 3.
  2. Если last_modified не изменился с прошлого снимка — пропускаем ресурс, выходим.
  3. Тянем ВСЕ строки ресурса постранично через JSON API datastore_search
     (collector/api_loader.py) — НЕ скачиванием сырого CSV с e.data.gov.il, тот
     эндпоинт с некоторого момента стоит за защитой от ботов и обычным HTTP-клиентом
     недоступен (подробности в api_loader.py). Попутно считаем sha256 по сырым
     страницам ответа и архивируем их (gzip) в archive/<resource_id>/<дата>.jsonl.gz.
     Если sha256 совпал с прошлым снимком (данные "тронули", но содержимое то же) —
     снимок не создаём.
  4. Загружаем в staging пачками (сами постраничные ответы уже в JSON, парсить
     CSV/детектить кодировку/разделитель для этих двух ресурсов больше не нужно).
  5. Через SQL JOIN staging <-> current_state находим ТОЛЬКО измененные строки
     (не тащим 2.4 млн строк в python — JOIN и WHERE делает sqlite).
  6. Пишем history/engine_changes/odometer_anomalies, обновляем current_state,
     фиксируем snapshot.
  7. Отдельно архивируем сырой package_show JSON по всем датасетам проекта (meta_archive).
  8. Пишем лог в collector/logs/collector.log и таблицу run_log.

Идемпотентность: повторный запуск в тот же день на тех же данных не создаёт новых
снимков и не портит данные (см. проверки в шаге 2/3 выше). Все операции записи в БД
идут в транзакциях (см. db.transaction) — убийство процесса посередине не бьёт базу,
т.к. sqlite либо целиком закоммитит, либо откатит последнюю транзакцию.
"""

import gzip
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # чтобы видеть shared/

from shared.refdata import COLLECTED_RESOURCES, DATASET_SLUGS
from collector import config, db, meta
from collector import api_loader

logger = logging.getLogger("collector")


def setup_logging():
    os.makedirs(config.LOG_DIR, exist_ok=True)
    log_path = os.path.join(config.LOG_DIR, "collector.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


def last_snapshot_for(conn, resource_id):
    row = conn.execute(
        "SELECT * FROM snapshots WHERE resource_id=? ORDER BY snapshot_id DESC LIMIT 1",
        (resource_id,),
    ).fetchone()
    return row


def archive_meta(conn):
    """Пункт 7 алгоритма: сохраняем сырой package_show JSON по всем датасетам проекта —
    доказательство состояния метаданных на случай, если министерство что-то поменяет."""
    now = datetime.utcnow().isoformat()
    for name, slug in DATASET_SLUGS.items():
        try:
            result = meta.retry(meta.package_show, 3, 5, slug)
            with db.transaction(conn):
                conn.execute(
                    "INSERT INTO meta_archive (dataset_slug, taken_at, package_show_json) VALUES (?,?,?)",
                    (slug, now, json.dumps(result, ensure_ascii=False)),
                )
            logger.info("meta_archive: %s (%s) сохранён", name, slug)
        except Exception as e:
            logger.warning("meta_archive: не удалось получить %s (%s): %s", name, slug, e)


def process_history_resource(conn, resource, resource_id, snapshot_taken_at, row_count):
    """staging_history уже загружена (см. api_loader.load_resource_to_staging в run_resource).
    Находит изменения через SQL JOIN, пишет history/engine_changes/odometer_anomalies,
    обновляет current_state."""
    cur = conn.execute("""
        SELECT
            CAST(TRIM(s.mispar_rechev) AS INTEGER) AS plate,
            s.mispar_manoa AS new_engine,
            CAST(s.kilometer_test_aharon AS INTEGER) AS new_km,
            CAST(s.shinui_mivne_ind AS INTEGER) AS new_shinui_mivne,
            CAST(s.gapam_ind AS INTEGER) AS new_gapam,
            CAST(s.shnui_zeva_ind AS INTEGER) AS new_shnui_zeva,
            CAST(s.shinui_zmig_ind AS INTEGER) AS new_shinui_zmig,
            s.mkoriut_nm AS new_mkoriut,
            s.rishum_rishon_dt AS new_rishum_rishon,
            c.plate AS existing_plate,
            c.engine_no AS old_engine,
            c.km AS old_km,
            c.shinui_mivne_ind AS old_shinui_mivne,
            c.gapam_ind AS old_gapam,
            c.shnui_zeva_ind AS old_shnui_zeva,
            c.shinui_zmig_ind AS old_shinui_zmig,
            c.mkoriut_nm AS old_mkoriut,
            c.snapshot_id AS old_snapshot_id
        FROM staging_history s
        LEFT JOIN current_state c ON c.plate = TRIM(s.mispar_rechev)
        WHERE s.mispar_rechev IS NOT NULL AND TRIM(s.mispar_rechev) != ''
          AND (
            c.plate IS NULL
            OR IFNULL(c.km,-1) != IFNULL(CAST(s.kilometer_test_aharon AS INTEGER),-1)
            OR IFNULL(c.engine_no,'') != IFNULL(s.mispar_manoa,'')
            OR IFNULL(c.shinui_mivne_ind,-1) != IFNULL(CAST(s.shinui_mivne_ind AS INTEGER),-1)
            OR IFNULL(c.gapam_ind,-1) != IFNULL(CAST(s.gapam_ind AS INTEGER),-1)
            OR IFNULL(c.shnui_zeva_ind,-1) != IFNULL(CAST(s.shnui_zeva_ind AS INTEGER),-1)
            OR IFNULL(c.shinui_zmig_ind,-1) != IFNULL(CAST(s.shinui_zmig_ind AS INTEGER),-1)
            OR IFNULL(c.mkoriut_nm,'') != IFNULL(s.mkoriut_nm,'')
          )
    """)

    # snapshot уже создан выше по стеку (см. run_resource) — сюда приходит готовый snapshot_id через resource dict
    snapshot_id = resource["_snapshot_id"]

    changed_count = 0
    engine_change_count = 0
    anomaly_count = 0
    new_plate_count = 0

    history_batch = []
    engine_batch = []
    anomaly_batch = []
    state_batch = []

    def flush():
        nonlocal history_batch, engine_batch, anomaly_batch, state_batch
        if history_batch:
            conn.executemany(
                "INSERT INTO history (plate, snapshot_id, km, engine_no, changed_fields, detected_at) "
                "VALUES (?,?,?,?,?,?)", history_batch)
            history_batch = []
        if engine_batch:
            conn.executemany(
                "INSERT INTO engine_changes (plate, old_engine, new_engine, detected_at, km_at_change, "
                "prev_snapshot_id, new_snapshot_id) VALUES (?,?,?,?,?,?,?)", engine_batch)
            engine_batch = []
        if anomaly_batch:
            conn.executemany(
                "INSERT INTO odometer_anomalies (plate, prev_km, new_km, detected_at, prev_snapshot_id, "
                "new_snapshot_id) VALUES (?,?,?,?,?,?)", anomaly_batch)
            anomaly_batch = []
        if state_batch:
            conn.executemany("""
                INSERT INTO current_state (plate, km, engine_no, shinui_mivne_ind, gapam_ind,
                    shnui_zeva_ind, shinui_zmig_ind, mkoriut_nm, rishum_rishon_dt, snapshot_id, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(plate) DO UPDATE SET
                    km=excluded.km, engine_no=excluded.engine_no,
                    shinui_mivne_ind=excluded.shinui_mivne_ind, gapam_ind=excluded.gapam_ind,
                    shnui_zeva_ind=excluded.shnui_zeva_ind, shinui_zmig_ind=excluded.shinui_zmig_ind,
                    mkoriut_nm=excluded.mkoriut_nm, rishum_rishon_dt=excluded.rishum_rishon_dt,
                    snapshot_id=excluded.snapshot_id, updated_at=excluded.updated_at
            """, state_batch)
            state_batch = []

    detected_at = snapshot_taken_at
    processed = 0
    with db.transaction(conn):
        for row in cur:
            plate = row["plate"]
            if plate is None:
                continue
            processed += 1
            if processed % 300000 == 0:
                logger.info("history: обработано %d строк diff'а...", processed)
            changed_fields = []
            is_new = row["existing_plate"] is None

            if is_new:
                new_plate_count += 1
            else:
                if row["old_km"] != row["new_km"]:
                    changed_fields.append("km")
                if (row["old_engine"] or "") != (row["new_engine"] or ""):
                    changed_fields.append("engine_no")
                if row["old_shinui_mivne"] != row["new_shinui_mivne"]:
                    changed_fields.append("shinui_mivne_ind")
                if row["old_gapam"] != row["new_gapam"]:
                    changed_fields.append("gapam_ind")
                if row["old_shnui_zeva"] != row["new_shnui_zeva"]:
                    changed_fields.append("shnui_zeva_ind")
                if row["old_shinui_zmig"] != row["new_shinui_zmig"]:
                    changed_fields.append("shinui_zmig_ind")
                if (row["old_mkoriut"] or "") != (row["new_mkoriut"] or ""):
                    changed_fields.append("mkoriut_nm")

                if changed_fields:
                    changed_count += 1
                    history_batch.append((plate, snapshot_id, row["new_km"], row["new_engine"],
                                           json.dumps(changed_fields), detected_at))

                # Флагманская фича: смена номера двигателя
                if "engine_no" in changed_fields and row["old_engine"] and row["new_engine"]:
                    engine_change_count += 1
                    engine_batch.append((plate, row["old_engine"], row["new_engine"], detected_at,
                                          row["new_km"], row["old_snapshot_id"],
                                          snapshot_id))

                # Аномалия: пробег УМЕНЬШИЛСЯ между снимками -> вероятная скрутка одометра
                if (row["old_km"] is not None and row["new_km"] is not None
                        and row["new_km"] < row["old_km"]):
                    anomaly_count += 1
                    anomaly_batch.append((plate, row["old_km"], row["new_km"], detected_at,
                                           row["old_snapshot_id"], snapshot_id))

            state_batch.append((plate, row["new_km"], row["new_engine"], row["new_shinui_mivne"],
                                 row["new_gapam"], row["new_shnui_zeva"], row["new_shinui_zmig"],
                                 row["new_mkoriut"], row["new_rishum_rishon"], snapshot_id, detected_at))

            if len(state_batch) >= config.BATCH_SIZE:
                flush()
        flush()

    logger.info("history: новых машин=%d, изменений=%d, смен двигателя=%d, аномалий пробега=%d",
                new_plate_count, changed_count, engine_change_count, anomaly_count)
    return {
        "new_plates": new_plate_count, "changed": changed_count,
        "engine_changes": engine_change_count, "anomalies": anomaly_count,
        "row_count": row_count,
    }


def process_ownership_resource(conn, resource, snapshot_id, row_count):
    """staging_ownership уже загружена (см. api_loader.load_resource_to_staging в run_resource)."""
    with db.transaction(conn):
        cur = conn.execute("""
            INSERT OR IGNORE INTO ownership (plate, baalut_dt, baalut, first_seen_snapshot)
            SELECT CAST(TRIM(mispar_rechev) AS INTEGER), baalut_dt, baalut, ?
            FROM staging_ownership
            WHERE mispar_rechev IS NOT NULL AND TRIM(mispar_rechev) != ''
        """, (snapshot_id,))
        inserted = cur.rowcount
    logger.info("ownership: новых записей владения=%d (из %d строк файла)", inserted, row_count)
    return {"new_ownership_rows": inserted, "row_count": row_count}


def run_resource(conn, resource_key, resource_id, resources_by_id, run_stats):
    res = resources_by_id.get(resource_id)
    if res is None:
        logger.error("Ресурс %s не найден в package_show(shinui_mivne) — пропуск", resource_id)
        return

    last_modified = res.get("last_modified")
    prev_snapshot = last_snapshot_for(conn, resource_id)

    if prev_snapshot is not None and prev_snapshot["last_modified"] == last_modified:
        logger.info("[%s] last_modified не изменился (%s) — снимок пропущен", resource_key, last_modified)
        run_stats[resource_key] = {"skipped": True, "reason": "last_modified не изменился"}
        return

    logger.info("[%s] last_modified изменился (было %s, стало %s) — тяну через JSON API",
                resource_key, prev_snapshot["last_modified"] if prev_snapshot else None, last_modified)

    staging_table = "staging_history" if resource_key == "history" else "staging_ownership"
    date_tag = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    archive_path = os.path.join(config.ARCHIVE_DIR, resource_id, f"{date_tag}.jsonl.gz")
    os.makedirs(os.path.dirname(archive_path), exist_ok=True)

    archive_file = gzip.open(archive_path, "wb")
    try:
        def archive_writer(raw_bytes):
            archive_file.write(raw_bytes)
            archive_file.write(b"\n")
        try:
            load_stats = api_loader.load_resource_to_staging(conn, resource_id, staging_table,
                                                               archive_writer=archive_writer)
        except Exception as e:
            logger.error("[%s] загрузка через JSON API не удалась: %s", resource_key, e)
            run_stats[resource_key] = {"error": str(e)}
            return
    finally:
        archive_file.close()

    sha256 = load_stats["sha256"]
    row_count = load_stats["row_count"]
    logger.info("staging_%s: %s строк (через JSON API, постранично)", resource_key, row_count)

    if prev_snapshot is not None and prev_snapshot["sha256"] == sha256:
        logger.info("[%s] sha256 совпал с прошлым снимком, содержимое не изменилось — снимок пропущен", resource_key)
        run_stats[resource_key] = {"skipped": True, "reason": "sha256 совпал"}
        os.remove(archive_path)
        with db.transaction(conn):
            conn.execute(f'DROP TABLE IF EXISTS "{staging_table}"')
        return

    logger.info("[%s] сохранён снимок в %s (%d строк, %.1f МБ сжато)",
                resource_key, archive_path, row_count, os.path.getsize(archive_path) / 1e6)

    taken_at = datetime.utcnow().isoformat()
    with db.transaction(conn):
        cur = conn.execute(
            "INSERT INTO snapshots (resource_id, taken_at, source_url, last_modified, sha256, row_count, file_path) "
            "VALUES (?,?,?,?,?,?,?)",
            (resource_id, taken_at, res["url"], last_modified, sha256, row_count,
             os.path.relpath(archive_path, config.BASE_DIR)),
        )
        snapshot_id = cur.lastrowid

    resource_ctx = dict(res)
    resource_ctx["_snapshot_id"] = snapshot_id
    resource_ctx["_prev_snapshot_id"] = prev_snapshot["snapshot_id"] if prev_snapshot else None

    if resource_key == "history":
        stats = process_history_resource(conn, resource_ctx, resource_id, taken_at, row_count)
    else:
        stats = process_ownership_resource(conn, resource_ctx, snapshot_id, row_count)

    # staging — временная рабочая таблица (см. api_loader.py), в базе постоянно
    # храниться не должна: она дублирует те же данные, что уже разложены по
    # current_state/ownership, и на миллионах строк заметно раздувает файл БД
    # (обнаружено на первом реальном прогоне — carcheck.sqlite3 распух почти
    # до 1.2 ГБ, что и в git не запушить, и незачем).
    with db.transaction(conn):
        conn.execute(f'DROP TABLE IF EXISTS "{staging_table}"')

    run_stats[resource_key] = stats


def main():
    setup_logging()
    logger.info("=== Запуск сборщика carcheck ===")

    conn = db.get_connection()
    db.init_db(conn)

    with db.transaction(conn):
        cur = conn.execute("INSERT INTO run_log (started_at, status) VALUES (?, 'running')",
                            (datetime.utcnow().isoformat(),))
        run_id = cur.lastrowid

    run_stats = {}
    error_message = None
    try:
        package = meta.retry(meta.package_show, 3, 10, "shinui_mivne")
        resources_by_id = {r["id"]: r for r in package.get("resources", [])}

        for key, resource_id in COLLECTED_RESOURCES.items():
            run_resource(conn, key, resource_id, resources_by_id, run_stats)

        archive_meta(conn)

        status = "ok"
    except Exception as e:
        logger.exception("Сборщик упал с ошибкой")
        error_message = str(e)
        status = "error"

    with db.transaction(conn):
        conn.execute(
            "UPDATE run_log SET finished_at=?, status=?, message=? WHERE id=?",
            (datetime.utcnow().isoformat(), status, error_message or json.dumps(run_stats, ensure_ascii=False), run_id),
        )

    # VACUUM возвращает диску место, освобождённое DROP TABLE staging_* выше —
    # без этого файл БД не сжимается сам по себе (SQLite просто помечает
    # страницы свободными, не обрезая файл). Нужен вне транзакции.
    try:
        conn.execute("VACUUM")
    except sqlite3.Error as e:
        logger.warning("VACUUM не выполнен: %s", e)

    conn.close()
    logger.info("=== Сборщик завершён: %s ===", status)
    if status == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
