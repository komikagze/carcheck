# -*- coding: utf-8 -*-
"""
collector/csv_loader.py — автоопределение кодировки/разделителя и потоковая
загрузка CSV в staging-таблицу SQLite пачками (executemany), БЕЗ загрузки
2.4 млн строк в python-словарь. Дальше сравнение делает сам SQLite через JOIN
(см. collector.py: diff_and_apply).

Грабли из BRIEF.md, которые здесь учтены:
- Разделитель не обязательно запятая — возможен ";" или "|". Определяем через csv.Sniffer,
  с фоллбэком на разделитель, который даёт наибольшее и стабильное число колонок.
- Кодировка: пробуем BOM (utf-8-sig), затем utf-8, затем windows-1255 (иврит),
  берём первую, которая читает пробную порцию без ошибок декодирования.
"""

import csv
import gzip
import sqlite3

from . import config

CANDIDATE_ENCODINGS = ["utf-8-sig", "utf-8", "windows-1255", "cp1255"]
CANDIDATE_DELIMITERS = [",", ";", "|", "\t"]


def _open_text(path):
    """Открывает CSV или CSV.GZ как текстовый поток в подходящей кодировке."""
    raw_opener = gzip.open if path.endswith(".gz") else open
    last_err = None
    for enc in CANDIDATE_ENCODINGS:
        try:
            f = raw_opener(path, "rt", encoding=enc, newline="")
            sample = f.read(65536)
            f.seek(0)
            sample.encode("utf-8")  # проверка, что декодировалось осмысленно
            return f, enc
        except (UnicodeDecodeError, UnicodeError) as e:
            last_err = e
            try:
                f.close()
            except Exception:
                pass
            continue
    raise RuntimeError(f"Не удалось определить кодировку файла {path}: {last_err}")


def _sniff_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(CANDIDATE_DELIMITERS))
        return dialect.delimiter
    except csv.Error:
        # Фоллбэк: выбираем разделитель, который встречается чаще всего
        # в первой строке и даёт больше одной колонки.
        first_line = sample.splitlines()[0] if sample.splitlines() else ""
        counts = {d: first_line.count(d) for d in CANDIDATE_DELIMITERS}
        best = max(counts, key=counts.get)
        if counts[best] == 0:
            return ","  # однозначно одна колонка, разделитель не важен
        return best


def _sanitize_column(name: str) -> str:
    """Имена полей в разных ресурсах бывают 'MISPAR RECHEV' (с пробелом) или
    'RECALL_ID' (капс). Для staging-таблицы делаем безопасное имя колонки,
    но исходное имя сохраняем в маппинге, чтобы дальше можно было найти нужное поле."""
    safe = name.strip().replace(" ", "_").replace("-", "_")
    safe = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in safe)
    if not safe:
        safe = "col"
    if safe[0].isdigit():
        safe = "c_" + safe
    return safe.lower()


def load_csv_to_staging(conn: sqlite3.Connection, csv_path: str, staging_table: str) -> dict:
    """Читает CSV (сам детектит кодировку/разделитель), создаёт staging_table
    заново (DROP + CREATE), грузит все строки пачками executemany.

    Возвращает {"row_count": N, "columns": [...], "column_map": {sanitized: original}, "delimiter": ..., "encoding": ...}
    """
    f, encoding = _open_text(csv_path)
    try:
        sample = f.read(65536)
        f.seek(0)
        delimiter = _sniff_delimiter(sample)

        reader = csv.reader(f, delimiter=delimiter)
        header = next(reader)
        column_map = {}
        columns = []
        for col in header:
            safe = _sanitize_column(col)
            # избегаем дублей после санитайза
            base, i = safe, 1
            while safe in column_map:
                i += 1
                safe = f"{base}_{i}"
            column_map[safe] = col
            columns.append(safe)

        conn.execute(f'DROP TABLE IF EXISTS "{staging_table}"')
        cols_ddl = ", ".join(f'"{c}" TEXT' for c in columns)
        conn.execute(f'CREATE TABLE "{staging_table}" ({cols_ddl})')

        placeholders = ", ".join(["?"] * len(columns))
        insert_sql = f'INSERT INTO "{staging_table}" VALUES ({placeholders})'

        batch = []
        row_count = 0
        ncols = len(columns)
        for row in reader:
            if not row:
                continue
            # защита от строк с "лишними" или недостающими колонками
            if len(row) < ncols:
                row = row + [None] * (ncols - len(row))
            elif len(row) > ncols:
                row = row[:ncols]
            batch.append(row)
            row_count += 1
            if len(batch) >= config.BATCH_SIZE:
                conn.executemany(insert_sql, batch)
                batch.clear()
        if batch:
            conn.executemany(insert_sql, batch)

        if "mispar_rechev" in columns:
            conn.execute(f'CREATE INDEX IF NOT EXISTS "idx_{staging_table}_plate" '
                         f'ON "{staging_table}"("mispar_rechev")')

        return {
            "row_count": row_count,
            "columns": columns,
            "column_map": column_map,
            "delimiter": delimiter,
            "encoding": encoding,
        }
    finally:
        f.close()
