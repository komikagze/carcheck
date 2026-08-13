# -*- coding: utf-8 -*-
"""
export/kv_upload.py — наполняет Cloudflare KV накопленной историей по машинам.

Это и есть "приватная" часть архитектуры (см. README, "Деплой: Cloudflare Pages
+ Pages Functions + KV"): данные лежат не как публично перечислимые файлы на
сайте, а как записи в KV-хранилище, ключ = нормализованный номер машины,
значение = JSON с историей одометра/двигателя/аномалий ИМЕННО для этой машины.
Прочитать запись можно только зная точный номер — через Cloudflare Pages Function
functions/api/history/[plate].js (см. export/dist_template/functions/), которая
не даёт способа перечислить/выгрузить все ключи разом.

Запускается отдельным шагом workflow (.github/workflows/weekly.yml) ПОСЛЕ
collector.py и export.py. Требует три переменные окружения (GitHub Secrets):

  CF_API_TOKEN        — API-токен Cloudflare с правом "Workers KV Storage: Edit"
  CF_ACCOUNT_ID        — ID аккаунта Cloudflare (Dashboard -> Workers & Pages -> Overview)
  CF_KV_NAMESPACE_ID   — ID KV namespace (создаётся один раз вручную, см. README)

Использует Cloudflare REST API напрямую (bulk write), без wrangler/npm —
чтобы не тянуть Node.js в тот же джоб, который и так уже настроил Python.
Ключи разбиваются на пачки по BULK_BATCH_SIZE штук — у Cloudflare есть лимит
на размер одного bulk-запроса (сейчас 10 000 ключей / до 100 МБ на запрос),
для нашего объёма (десятки-сотни тысяч машин, JSON на машину — сотни байт)
чанкование почти наверняка не понадобится, но сделано на будущее.
"""

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector import config as collector_config

BULK_BATCH_SIZE = 5000
API_BASE = "https://api.cloudflare.com/client/v4"


def load_history_by_plate(conn):
    """Тот же принцип, что был раньше в export.py для шардов: одним проходом на
    таблицу собираем показания одометра/смены двигателя/аномалии по каждой машине.
    В значение KV попадает ТОЛЬКО номер (в качестве ключа) + пробег с датами +
    номера двигателя — ничего лишнего (никаких путей на диске, snapshot_id и т.п.)."""
    plates = {}

    for row in conn.execute("SELECT plate, km, updated_at FROM current_state"):
        plates[row["plate"]] = {"odometer": [{"date": row["updated_at"], "km": row["km"]}],
                                 "engine_changes": [], "anomalies": []}

    for row in conn.execute("""
        SELECT plate, km, detected_at FROM history WHERE km IS NOT NULL ORDER BY plate, detected_at ASC
    """):
        p = plates.setdefault(row["plate"], {"odometer": [], "engine_changes": [], "anomalies": []})
        p["odometer"].append({"date": row["detected_at"], "km": row["km"]})

    for p in plates.values():
        seen, dedup = set(), []
        for point in sorted(p["odometer"], key=lambda x: x["date"] or ""):
            key = (point["date"], point["km"])
            if key in seen:
                continue
            seen.add(key)
            dedup.append(point)
        p["odometer"] = dedup

    for row in conn.execute("""
        SELECT plate, old_engine, new_engine, detected_at, km_at_change
        FROM engine_changes ORDER BY plate, detected_at ASC
    """):
        p = plates.setdefault(row["plate"], {"odometer": [], "engine_changes": [], "anomalies": []})
        p["engine_changes"].append({"date": row["detected_at"], "old_engine": row["old_engine"],
                                     "new_engine": row["new_engine"], "km": row["km_at_change"]})

    for row in conn.execute("""
        SELECT plate, prev_km, new_km, detected_at FROM odometer_anomalies ORDER BY plate, detected_at ASC
    """):
        p = plates.setdefault(row["plate"], {"odometer": [], "engine_changes": [], "anomalies": []})
        p["anomalies"].append({"date": row["detected_at"], "prev_km": row["prev_km"], "new_km": row["new_km"]})

    return plates


def build_kv_entries(plates: dict) -> list:
    entries = []
    for plate, payload in plates.items():
        value = {
            "available": True,
            "plate": str(plate),
            "odometer": payload["odometer"],
            "engine_changes": payload["engine_changes"],
            "anomalies": payload["anomalies"],
        }
        entries.append({"key": f"car:{plate}", "value": json.dumps(value, ensure_ascii=False, separators=(",", ":"))})
    return entries


def cf_bulk_put(account_id, namespace_id, token, entries):
    url = f"{API_BASE}/accounts/{account_id}/storage/kv/namespaces/{namespace_id}/bulk"
    body = json.dumps(entries).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="PUT", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if not result.get("success"):
        raise RuntimeError(f"Cloudflare KV bulk write вернул ошибку: {result.get('errors')}")
    return result


def run(db_path: str = None):
    db_path = db_path or collector_config.DB_PATH

    account_id = os.environ.get("CF_ACCOUNT_ID")
    namespace_id = os.environ.get("CF_KV_NAMESPACE_ID")
    token = os.environ.get("CF_API_TOKEN")

    missing = [name for name, val in [("CF_ACCOUNT_ID", account_id),
                                       ("CF_KV_NAMESPACE_ID", namespace_id),
                                       ("CF_API_TOKEN", token)] if not val]
    if missing:
        print(f"[kv_upload] Не заданы переменные окружения: {', '.join(missing)}. "
              f"Пропускаю загрузку в KV (см. README -> GitHub Secrets). "
              f"Это не ошибка сборщика — просто интеграция с Cloudflare ещё не настроена.")
        return {"ok": False, "reason": "missing_env", "missing": missing}

    if not os.path.exists(db_path):
        print(f"[kv_upload] База {db_path} не найдена — нечего загружать (сборщик ещё ни разу не запускался).")
        return {"ok": False, "reason": "no_db"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        plates = load_history_by_plate(conn)
    finally:
        conn.close()

    entries = build_kv_entries(plates)
    if not entries:
        print("[kv_upload] Накопленных машин пока нет — загружать нечего.")
        return {"ok": True, "uploaded": 0}

    uploaded = 0
    for i in range(0, len(entries), BULK_BATCH_SIZE):
        batch = entries[i:i + BULK_BATCH_SIZE]
        try:
            cf_bulk_put(account_id, namespace_id, token, batch)
        except (urllib.error.URLError, RuntimeError) as e:
            print(f"[kv_upload] Ошибка загрузки пачки {i}-{i + len(batch)}: {e}")
            raise
        uploaded += len(batch)
        print(f"[kv_upload] Загружено {uploaded}/{len(entries)} записей...")

    print(f"[kv_upload] Готово: {uploaded} записей в KV namespace {namespace_id}.")
    return {"ok": True, "uploaded": uploaded}


if __name__ == "__main__":
    result = run()
    if result.get("ok") is False and result.get("reason") not in ("missing_env", "no_db"):
        sys.exit(1)
