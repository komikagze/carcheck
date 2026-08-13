# -*- coding: utf-8 -*-
"""
server/history_api.py — блоки из накопленной локальной базы (Часть 2 ТЗ, "новое,
чего нет ни у кого"): история показаний одометра по снимкам, смена номера
двигателя, аномалии пробега (скрутка), локальная история владения.

Если сборщик ещё ни разу не запускался — база отсутствует, отдаём честный
ответ available=False с пояснением, а не ошибку 500.
"""

import os
import sqlite3

from . import config


def _connect():
    if not os.path.exists(config.DB_PATH):
        return None
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def get_local_data(plate: str) -> dict:
    conn = _connect()
    if conn is None:
        return {
            "available": False,
            "note": "מסד הנתונים המקומי טרם נוצר. הריצו את run_collector.bat "
                    "לפחות פעם אחת כדי להתחיל לצבור היסטוריית קילומטראז' ובעלות.",
            "odometer_series": [],
            "engine_changes": [],
            "anomalies": [],
        }
    try:
        plate_int = int(plate)
    except ValueError:
        conn.close()
        return {"available": True, "odometer_series": [], "engine_changes": [], "anomalies": [], "note": None}

    try:
        odometer_series = [
            dict(row) for row in conn.execute(
                """
                SELECT h.detected_at, h.km, s.taken_at AS snapshot_taken_at
                FROM history h
                JOIN snapshots s ON s.snapshot_id = h.snapshot_id
                WHERE h.plate = ? AND h.km IS NOT NULL
                ORDER BY h.detected_at ASC
                """, (plate_int,)
            ).fetchall()
        ]
        # добавим самое первое (текущее на момент первого снимка) значение, если current_state есть
        # и в history для этой машины ещё не было ни одной записи (новая машина в базе)
        current = conn.execute(
            "SELECT km, updated_at FROM current_state WHERE plate=?", (plate_int,)
        ).fetchone()
        if current and not odometer_series:
            odometer_series = [{"detected_at": current["updated_at"], "km": current["km"],
                                 "snapshot_taken_at": current["updated_at"]}]
        elif current:
            last = odometer_series[-1]
            if last["km"] != current["km"]:
                odometer_series.append({"detected_at": current["updated_at"], "km": current["km"],
                                         "snapshot_taken_at": current["updated_at"]})

        engine_changes = [
            dict(row) for row in conn.execute(
                """
                SELECT old_engine, new_engine, detected_at, km_at_change
                FROM engine_changes WHERE plate=? ORDER BY detected_at ASC
                """, (plate_int,)
            ).fetchall()
        ]

        anomalies = [
            dict(row) for row in conn.execute(
                """
                SELECT prev_km, new_km, detected_at
                FROM odometer_anomalies WHERE plate=? ORDER BY detected_at ASC
                """, (plate_int,)
            ).fetchall()
        ]

        ownership_local = [
            dict(row) for row in conn.execute(
                """
                SELECT baalut_dt, baalut FROM ownership WHERE plate=? ORDER BY baalut_dt ASC
                """, (plate_int,)
            ).fetchall()
        ]

        return {
            "available": True,
            "note": None,
            "odometer_series": odometer_series,
            "engine_changes": engine_changes,
            "anomalies": anomalies,
            "ownership_local": ownership_local,
        }
    finally:
        conn.close()


def get_meta_stats() -> dict:
    """Для страницы статуса /api/status — сколько снимков в базе, дата последнего сбора."""
    conn = _connect()
    if conn is None:
        return {"available": False}
    try:
        snapshots = conn.execute("SELECT COUNT(*) AS c, MAX(taken_at) AS last FROM snapshots").fetchone()
        plates = conn.execute("SELECT COUNT(*) AS c FROM current_state").fetchone()
        engine_changes = conn.execute("SELECT COUNT(*) AS c FROM engine_changes").fetchone()
        anomalies = conn.execute("SELECT COUNT(*) AS c FROM odometer_anomalies").fetchone()
        return {
            "available": True,
            "snapshots_count": snapshots["c"],
            "last_snapshot_at": snapshots["last"],
            "plates_covered": plates["c"],
            "engine_changes_total": engine_changes["c"],
            "anomalies_total": anomalies["c"],
        }
    finally:
        conn.close()
