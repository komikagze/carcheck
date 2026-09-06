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
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

from shared.refdata import API_BASE
from . import config, db

log = logging.getLogger(__name__)

USER_AGENT = "carcheck-collector/1.0 (personal use, github.com/local)"

# Размер страницы. Начинаем с большого и УМЕНЬШАЕМ на лету, если портал отбил
# запрос (см. _fetch_page_adaptive).
#
# ПОЧЕМУ так, а не просто константа (обнаружено 06.09.2026 на живых запросах):
# с 24.08 основной реестр перестал отдаваться именно на limit=500000 — портал
# возвращает 404 МГНОВЕННО (0.1 с, то есть это отказ шлюза, а не таймаут).
# Замерено вживую по одному и тому же ресурсу 053cea08:
#     limit=300000 -> 200, 69 МБ, 6.4 с
#     limit=500000 -> 404 за 0.1 с
# При этом history на limit=500000 в тот же момент отдаётся нормально (111 МБ),
# и сам реестр на limit=300000 тоже. То есть ресурс жив, отбивается конкретная
# комбинация, и порог у портала может поехать снова в любую сторону. Поэтому
# размер страницы не зашит намертво, а деградирует сам.
PAGE_SIZE = 500000
MIN_PAGE_SIZE = 25000
FETCH_ATTEMPTS = 4


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


def _fetch_page_adaptive(resource_id: str, offset: int, limit: int, fields=None):
    """То же, что _fetch_page, но переживает отказ портала: сначала повторяет
    запрос, а если не помогло — просит страницу вдвое меньше.

    Возвращает (result, raw, limit) — limit тот, на котором в итоге получилось.
    Вызывающий код должен продолжать с ним же, иначе следующая страница снова
    упрётся в тот же отказ.
    """
    last_err = None
    for attempt in range(FETCH_ATTEMPTS):
        try:
            result, raw = _fetch_page(resource_id, offset, limit, fields=fields)
            return result, raw, limit
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            # Половиним страницу, а не просто ждём: отказ приходит мгновенно и
            # повторяется стабильно — значит дело в размере запроса, и пауза
            # сама по себе ничего не изменит.
            if limit > MIN_PAGE_SIZE:
                limit = max(MIN_PAGE_SIZE, limit // 2)
                log.warning("страница отбита (%s) — повторяю с limit=%d", e, limit)
            else:
                log.warning("страница отбита (%s) на минимальном limit=%d — повторяю", e, limit)
            if attempt < FETCH_ATTEMPTS - 1:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(
        f"datastore_search({resource_id}) не отдал страницу offset={offset} "
        f"за {FETCH_ATTEMPTS} попыток, последняя ошибка: {last_err}"
    )


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
    page_size = PAGE_SIZE
    total = None
    sha256 = hashlib.sha256()

    # ВАЖНО: conn открыт с isolation_level=None (см. collector/db.py) — без явной
    # транзакции sqlite3 автокоммитит КАЖДУЮ отдельную вставленную строку (каждый
    # executemany() всё равно один statement-execution на строку), что на
    # миллионах строк означает миллионы fsync и превращает загрузку в часы простоя
    # (обнаружено на первом реальном прогоне — висело без видимого прогресса).
    # Оборачиваем всю загрузку страницы в один explicit BEGIN/COMMIT.
    with db.transaction(conn):
        while True:
            result, raw, page_size = _fetch_page_adaptive(
                resource_id, offset, page_size, fields=fields)
            sha256.update(raw)
            if archive_writer:
                archive_writer(raw)

            records = result.get("records", [])

            if total is None:
                # Сколько строк в ресурсе всего. datastore_search отдаёт это в
                # каждом ответе (include_total) — единственный честный признак,
                # что мы выкачали ВЕСЬ срез, а не сколько дали.
                total = result.get("total")

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

            # Сдвигаемся на СТОЛЬКО, сколько реально пришло, а не на размер
            # запрошенной страницы: портал имеет право отдать меньше, и на
            # фиксированном шаге мы бы молча перепрыгнули через строки.
            offset += len(records)

            if not records:
                break
            if total is not None and row_count >= total:
                break

        # ЗАЩИТА ОТ ОБРЕЗАННОГО СНИМКА (обнаружено 06.09.2026 при разборе
        # прогона 24.08). Портал тогда отдал по 32 000 строк вместо 2.4 млн и
        # 5.4 млн, а старый цикл завершался по условию len(records) < PAGE_SIZE
        # — то есть принял обрезок за полный срез и записал его в snapshots
        # как настоящий (записи id 10 и 11, с честным sha256 и архивом).
        # Для проекта, который живёт сравнением НЕДЕЛЬНЫХ СРЕЗОВ, тихий обрезок
        # хуже падения: упавший прогон видно сразу, а такой снимок потом ничем
        # не отличить от настоящего, и сравнивать с ним нельзя.
        if total is not None and row_count < total:
            raise RuntimeError(
                f"datastore_search({resource_id}) отдал {row_count} строк из {total} — "
                f"снимок неполный, отказываюсь записывать его как срез"
            )

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
