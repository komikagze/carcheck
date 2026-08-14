# -*- coding: utf-8 -*-
"""
collector/api_loader.py — загрузка ресурса в staging-таблицу через постраничные
запросы к JSON API datastore_search, а НЕ через скачивание сырого CSV-файла
с e.data.gov.il.

ПОЧЕМУ ТАК (обнаружено на первом реальном прогоне, не было видно на этапе
подготовки без исполнения кода): CDN e.data.gov.il, откуда раньше отдавался
сырой CSV по прямой ссылке из package_show, с некоторого момента стоит за
защитой от ботов (JS-челлендж, похожий на Google Cloud Armor/reCAPTCHA
Enterprise — заголовок ответа "Via: 1.1 google"). Обычный HTTP-клиент
(urllib, requests и т.п.) получает вместо CSV HTML-страницу с обфусцированным
JS вместо файла. Проверено вживую: тот же URL, открытый в настоящем браузере
(после чего в нём выполнился челлендж и появилась сессионная cookie), отдаёт
нормальный CSV; тот же URL из чистого urllib — всегда HTML-заглушку, даже
с браузерным User-Agent.

При этом JSON API datastore_search (data.gov.il/api/action/datastore_search —
ТОТ ЖЕ эндпоинт, которым уже пользуется живой поиск по одному номеру в
server/live_api.py и в браузерной версии export/dist_template/static/app.js)
этой защитой не прикрыт вообще и прекрасно работает из чистого urllib.
Он поддерживает пагинацию (limit/offset) и глубокую пагинацию (проверено
на offset=2 400 000+) без проблем, поэтому весь объём ресурса (~2.4-5.3 млн
строк) можно вытянуть за десяток постраничных запросов вместо одного
скачивания файла.

Это НЕ попытка обойти защиту от ботов — мы используем совершенно другой,
официальный и открытый публичный API того же портала, тем же вежливым
способом (User-Agent с контактной информацией, паузы между попытками), каким
уже и так пользуется остальной проект.
"""

import hashlib
import json
import urllib.parse
import urllib.request

from shared.refdata import API_BASE
from . import config, db

USER_AGENT = "carcheck-collector/1.0 (personal use, github.com/local)"
PAGE_SIZE = 500000


def _fetch_page(resource_id: str, offset: int, limit: int, timeout=None, fields=None):
    timeout = timeout or config.DOWNLOAD_TIMEOUT
    url = f"{API_BASE}?resource_id={resource_id}&limit={limit}&offset={offset}"
    if fields:
        # Просим у API только нужные колонки. Для основного реестра это 2 поля
        # вместо 24 — на 4.2 млн строк разница в разы по трафику и по памяти
        # (без этого процесс на загрузке реестра разрастался до ~2 ГБ, что
        # рискованно для раннера GitHub Actions).
        url += "&fields=" + urllib.parse.quote(",".join(fields))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    data = json.loads(raw.decode("utf-8"))
    if not data.get("success"):
        raise RuntimeError(f"datastore_search({resource_id}) вернул success=false: {data}")
    return data["result"], raw


def load_resource_to_staging(conn, resource_id: str, staging_table: str, archive_writer=None,
                              fields=None) -> dict:
    """Постранично тянет ВСЕ строки ресурса через datastore_search и грузит их
    в staging_table (пересоздаётся заново, как раньше делал csv_loader).

    archive_writer(raw_bytes), если передан, вызывается для каждой сырой
    страницы ответа — используется вызывающим кодом для архивации (gzip) и
    тем самым входит в подсчёт sha256, которым мы по-прежнему детектим
    "содержимое не изменилось, хотя last_modified и обновился".

    Возвращает {"row_count", "columns", "column_map", "delimiter", "encoding", "sha256"} —
    та же форма, что раньше отдавал csv_loader.load_csv_to_staging (delimiter/encoding
    больше не применимы к JSON, но вызывающий код их только логирует).
    """
    columns = None
    row_count = 0
    offset = 0
    sha256 = hashlib.sha256()

    # ВАЖНО: conn открыт с isolation_level=None (см. collector/db.py) — без явной
    # транзакции sqlite3 автокоммитит КАЖДУЮ отдельную вставленную строку (каждый
    # executemany() всё равно один statement-execution на строку), что на
    # миллионах строк означает миллионы fsync и превращает загрузку в часы простоя
    # (обнаружено на первом реальном прогоне — висело без видимого прогресса).
    # Оборачиваем всю загрузку страницы в один explicit BEGIN/COMMIT.
    with db.transaction(conn):
        while True:
            result, raw = _fetch_page(resource_id, offset, PAGE_SIZE, fields=fields)
            sha256.update(raw)
            if archive_writer:
                archive_writer(raw)

            records = result.get("records", [])

            if columns is None:
                columns = [f["id"] for f in result.get("fields", []) if f["id"] != "_id"]
                conn.execute(f'DROP TABLE IF EXISTS "{staging_table}"')
                cols_ddl = ", ".join(f'"{c}" TEXT' for c in columns)
                conn.execute(f'CREATE TABLE "{staging_table}" ({cols_ddl})')

            if records:
                placeholders = ", ".join(["?"] * len(columns))
                insert_sql = f'INSERT INTO "{staging_table}" VALUES ({placeholders})'
                batch = [tuple(None if r.get(c) is None else str(r.get(c)) for c in columns) for r in records]
                conn.executemany(insert_sql, batch)
                row_count += len(records)

            if len(records) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        if columns and "mispar_rechev" in columns:
            conn.execute(f'CREATE INDEX IF NOT EXISTS "idx_{staging_table}_plate" '
                         f'ON "{staging_table}"("mispar_rechev")')

    return {
        "row_count": row_count,
        "columns": columns or [],
        "column_map": {c: c for c in (columns or [])},
        "delimiter": None,
        "encoding": "json",
        "sha256": sha256.hexdigest(),
    }
