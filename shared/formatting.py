# -*- coding: utf-8 -*-
"""
shared/formatting.py

Общие функции форматирования/перевода, перенесённые из JS-прототипа carcheck.html
(fmtDate, translateVal, testStatusBadge, isDateField и т.д.), плюс нормализация
номера машины, которая нужна и сборщику, и серверу.
"""

import re
from datetime import datetime, date

from .refdata import AVG_KM_YEAR


def normalize_plate(raw) -> str:
    """Убрать всё, кроме цифр, и убрать ведущие нули (в архиве встречаются
    номера с ведущим нулём, например 02947251). Возвращает строку без нулей
    слева, либо '0' если строка состояла только из нулей."""
    if raw is None:
        return ""
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return ""
    stripped = digits.lstrip("0")
    return stripped if stripped else "0"


def translate_val(v):
    """Значения из data.gov.il (баалут, топливо, цвет и т.д.) уже приходят на
    иврите, а интерфейс теперь тоже на иврите — переводить нечего, просто
    возвращаем значение как есть."""
    return v


def is_date_field(key: str) -> bool:
    return bool(re.search(r"(dt|date|taarich)$", key, re.IGNORECASE)) or "taarich" in key.lower()


def fmt_date(v):
    """Приводит дату к виду ДД.ММ.ГГГГ. Понимает YYYYMMDD, YYYY-MM-DD,
    'YYYY-MM-DD HH:MM:SS' и YYYYMM (полугодовые даты владения)."""
    if v is None or v == "":
        return None
    s = str(v)
    if re.fullmatch(r"\d{8}", s):
        return f"{s[6:8]}.{s[4:6]}.{s[0:4]}"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(3)}.{m.group(2)}.{m.group(1)}"
    if re.fullmatch(r"\d{6}", s):
        return f"{s[4:6]}.{s[0:4]}"
    return s


def test_status(date_str):
    """Возвращает 'ok'/'warn'/'bad'/None по дате окончания теста (tokef_dt)."""
    if not date_str:
        return None
    s = str(date_str)
    try:
        if re.fullmatch(r"\d{8}", s):
            d = datetime(int(s[0:4]), int(s[4:6]), int(s[6:8])).date()
        else:
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
            if not m:
                return None
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
    except ValueError:
        return None
    diff_days = (d - date.today()).days
    if diff_days < 0:
        return "bad"       # פג תוקף
    if diff_days < 30:
        return "warn"      # עומד לפוג
    return "ok"             # תקף


TEST_STATUS_LABELS = {"ok": "תקף", "warn": "עומד לפוג", "bad": "פג תוקף"}


def fmt_val(key, val):
    """Аналог fmtVal из JS: булевы _ind поля, автомат/механика, даты, переводы."""
    if key == "automatic_ind":
        return "אוטומט" if str(val) == "1" else "ידני"
    if key.endswith("_ind"):
        if str(val) == "1":
            return "כן"
        if str(val) == "0":
            return "לא"
    if is_date_field(key):
        return fmt_date(val)
    return translate_val(val)


def is_junk(key, val) -> bool:
    if val is None or val == "":
        return True
    if isinstance(val, str) and "לא ידוע" in val:
        return True
    if key.startswith("kosher_grira"):
        try:
            if float(val) == 0:
                return True
        except (TypeError, ValueError):
            pass
    return False


def mileage_analysis(km, year):
    """Пробег/год, сравнение со средним по стране. Возвращает dict или None."""
    try:
        km = float(km)
        year = int(year)
    except (TypeError, ValueError):
        return None
    if not km or not year:
        return None
    now_year = date.today().year
    age = max(1, now_year - year)
    per_year = round(km / age)
    ratio = per_year / AVG_KM_YEAR

    if ratio < 0.55:
        verdict, cls = "נמוך משמעותית מהממוצע", "warn"
        note = ("קילומטראז' נמוך יכול להיות תקין (רכב שני במשפחה), אך יכול גם להעיד "
                "על מד קילומטרים מסובב. כדאי להשוות עם בלאי הריפוד, ההגה והדוושות.")
    elif ratio > 1.6:
        verdict, cls = "גבוה משמעותית מהממוצע", "warn"
        note = ("קילומטראז' גבוה מעיד לרוב על שימוש במונית, בהפצה או בנסיעות בין-עירוניות תכופות. "
                "כדאי לשים לב למצב המתלים והמנוע.")
    else:
        verdict, cls = "בטווח התקין", "ok"
        note = ""

    return {
        "km": int(km),
        "age_years": age,
        "km_per_year": per_year,
        "verdict": verdict,
        "verdict_class": cls,
        "note": note,
        "avg_km_year": AVG_KM_YEAR,
    }
