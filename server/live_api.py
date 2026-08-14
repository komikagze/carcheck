# -*- coding: utf-8 -*-
"""
server/live_api.py — Python-порт живой логики из прототипа carcheck.html
(функции fetchResource/fetchByModel/render* в оригинале были на JS и бегали
в браузере; здесь то же самое делает сервер и параллельно опрашивает все
госбазы data.gov.il через ThreadPoolExecutor — аналог Promise.all).

Возвращает структурированный dict (не HTML) — рендерит его в HTML уже
static/app.js на клиенте, чтобы страница оставалась лёгкой и одинаковой
что для серверной, что для статической (dist/) версии интерфейса.
"""

import concurrent.futures
import json
import urllib.parse
import urllib.request
import urllib.error

from shared.refdata import (
    API_BASE, RESOURCE_MAIN, RESOURCE_MAIN_CONT, RESOURCE_HISTORY, RESOURCE_TAV_NECHE,
    RESOURCE_OWNERSHIP, RESOURCE_INACTIVE, RESOURCE_RECALL, RESOURCE_ADAS, RESOURCE_SPECS,
    RESOURCE_PRICE, RESOURCE_TAXI, RESOURCE_IMPORT, SCRAPPED_RESOURCES,
    FIELD_LABELS, HIDDEN_FIELDS, SPEC_FIELDS,
)
from shared.formatting import (
    normalize_plate, translate_val, fmt_date, fmt_val, is_date_field, is_junk,
    mileage_analysis, test_status,
)
from . import config

USER_AGENT = "carcheck-server/1.0 (personal use)"


def _http_get_json(url: str, timeout=None):
    timeout = timeout or config.HTTP_TIMEOUT
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_resource(resource_id: str, plate: str) -> dict:
    """Аналог fetchResource() из JS. Возвращает {"records":[...], "error": None|str}."""
    q = urllib.parse.quote(plate)
    url = f"{API_BASE}?resource_id={resource_id}&q={q}&limit=50"
    try:
        data = _http_get_json(url)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"records": [], "error": f"רשת: {e}"}
    except json.JSONDecodeError as e:
        return {"records": [], "error": f"JSON לא תקין: {e}"}
    if not data.get("success"):
        return {"records": [], "error": "ה-API החזיר success:false"}
    records = data["result"].get("records", [])
    target = normalize_plate(plate)

    def rec_plate(r):
        v = r.get("mispar_rechev", r.get("MISPAR_RECHEV", r.get("MISPAR RECHEV")))
        return normalize_plate(v) if v is not None else ""

    exact = [r for r in records if rec_plate(r) == target]
    return {"records": exact if exact else records, "error": None}


def fetch_by_model(resource_id: str, car: dict) -> dict:
    """Аналог fetchByModel(): последовательно пробует несколько фильтров,
    т.к. degem_cd нужно дополнять нулями до 4 знаков, а иногда фильтр вообще
    не совпадает и нужно ослаблять условия."""
    cd = str(car.get("degem_cd", "") or "")
    attempts = [
        {"tozeret_cd": str(car.get("tozeret_cd", "")), "degem_nm": car.get("degem_nm"),
         "shnat_yitzur": str(car.get("shnat_yitzur", "")), "degem_cd": cd.zfill(4)},
        {"tozeret_cd": str(car.get("tozeret_cd", "")), "degem_nm": car.get("degem_nm"),
         "shnat_yitzur": str(car.get("shnat_yitzur", "")), "degem_cd": cd},
        {"tozeret_cd": str(car.get("tozeret_cd", "")), "degem_nm": car.get("degem_nm"),
         "shnat_yitzur": str(car.get("shnat_yitzur", ""))},
        {"tozeret_cd": str(car.get("tozeret_cd", "")), "degem_nm": car.get("degem_nm")},
    ]
    for f in attempts:
        try:
            qf = urllib.parse.quote(json.dumps(f, ensure_ascii=False))
            url = f"{API_BASE}?resource_id={resource_id}&filters={qf}&limit=5"
            data = _http_get_json(url)
            if data.get("success") and data["result"].get("records"):
                return {"records": data["result"]["records"], "error": None}
        except Exception:
            continue
    return {"records": [], "error": None}


def _row_to_kv(record: dict, skip_keys=frozenset()) -> list:
    """Строка -> список [{key,label,value,is_date}] готовых для рендера полей."""
    out = []
    for key, val in record.items():
        if key.startswith("_") or key in HIDDEN_FIELDS or key in skip_keys:
            continue
        if val is None or val == "":
            continue
        display = fmt_date(val) if is_date_field(key) else translate_val(val)
        out.append({"key": key, "label": FIELD_LABELS.get(key, key), "value": display})
    return out


def build_report(plate_raw: str) -> dict:
    plate = normalize_plate(plate_raw)
    errors = []
    if not plate:
        return {"plate": plate_raw, "errors": ["יש להזין מספר רכב (ספרות בלבד)."], "not_found": True}

    tasks = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as ex:
        tasks["main"] = ex.submit(fetch_resource, RESOURCE_MAIN, plate)
        tasks["history"] = ex.submit(fetch_resource, RESOURCE_HISTORY, plate)
        tasks["tav_neche"] = ex.submit(fetch_resource, RESOURCE_TAV_NECHE, plate)
        tasks["ownership"] = ex.submit(fetch_resource, RESOURCE_OWNERSHIP, plate)
        tasks["inactive"] = ex.submit(fetch_resource, RESOURCE_INACTIVE, plate)
        tasks["recall"] = ex.submit(fetch_resource, RESOURCE_RECALL, plate)
        tasks["adas"] = ex.submit(fetch_resource, RESOURCE_ADAS, plate)
        tasks["taxi"] = ex.submit(fetch_resource, RESOURCE_TAXI, plate)
        tasks["personal_import"] = ex.submit(fetch_resource, RESOURCE_IMPORT, plate)
        for rid, period in SCRAPPED_RESOURCES:
            tasks[f"scrapped::{rid}"] = ex.submit(fetch_resource, rid, plate)

        results = {k: f.result() for k, f in tasks.items()}

    main_data = results["main"]
    if not main_data["records"]:
        cont = fetch_resource(RESOURCE_MAIN_CONT, plate)
        if cont["records"]:
            main_data = cont

    if main_data.get("error"):
        errors.append("מרשם ראשי: " + main_data["error"])
    if results["history"].get("error"):
        errors.append("היסטוריה/קילומטראז': " + results["history"]["error"])

    main_record = main_data["records"][0] if main_data["records"] else None
    history_record = results["history"]["records"][0] if results["history"]["records"] else None
    merged = dict(main_record) if main_record else None
    if merged and history_record:
        merged.update({k: v for k, v in history_record.items() if v not in (None, "")})

    report = {
        "plate": plate,
        "errors": errors,
        "not_found": merged is None,
        "main": None,
        "main_extra": [],
        "mileage_analysis": None,
        "history_records": [],
        "scrapped": {"found": False, "period": None},
        "taxi": bool(results["taxi"]["records"]),
        "personal_import": None,
        "inactive": bool(results["inactive"]["records"]),
        "tav_neche": {"has": bool(results["tav_neche"]["records"]), "dates": []},
        "ownership": {"records": [], "covered": True},
        "recalls": {"records": [], "count": 0},
        "adas": bool(results["adas"]["records"]),
        "specs": [],
        "price": [],
        "limitations": [
            "האבזור לפי קטלוג הדגם — נתוני יצרן של הדגם, לא בדיקה של הרכב הספציפי.",
            "הקילומטראז' ממאגר המדינה — רק הקריאה האחרונה בעת מבחן הרישוי, היסטוריה שנתית אינה מתפרסמת.",
            "מאגרי הקילומטראז' והבעלות מכסים רק רכבים שנרשמו החל משנת 2017.",
        ],
    }

    if merged:
        priority_order = [
            "shnat_yitzur", "tzeva_rechev", "sug_delek_nm", "baalut",
            "kilometer_test_aharon", "mivchan_acharon_dt", "tokef_dt",
            "kvutzat_zihum", "ramat_eivzur_betihuty", "misgeret", "rishum_rishon_dt",
        ]
        shown = {"mispar_rechev", "tozeret_nm", "kinuy_mishari", "degem_nm",
                 "horaat_rishum", "moed_aliya_lakvish"}
        rows = []
        for key in priority_order:
            if merged.get(key) in (None, ""):
                continue
            shown.add(key)
            val = translate_val(merged[key])
            extra = None
            if is_date_field(key):
                val = fmt_date(val)
                if key == "tokef_dt":
                    extra = test_status(merged[key])
            rows.append({"key": key, "label": FIELD_LABELS.get(key, key), "value": val, "status": extra})

        model_name = " ".join(filter(None, [merged.get("tozeret_nm"), merged.get("kinuy_mishari") or merged.get("degem_nm")]))
        report["main"] = {
            "plate": merged.get("mispar_rechev", plate),
            "model": model_name or "רכב",
            "rows": rows,
        }
        report["main_extra"] = _row_to_kv(merged, skip_keys=shown)
        report["mileage_analysis"] = mileage_analysis(merged.get("kilometer_test_aharon"), merged.get("shnat_yitzur"))

    if len(results["history"]["records"]) > 1:
        report["history_records"] = [_row_to_kv(r) for r in results["history"]["records"]]

    if results["tav_neche"]["records"]:
        dates = []
        for r in results["tav_neche"]["records"]:
            d = r.get("TAARICH HAFAKAT TAG") or r.get("taarich_hafakat_tag")
            if d:
                dates.append(fmt_date(d))
        report["tav_neche"]["dates"] = dates

    ownership_records = results["ownership"]["records"]
    if ownership_records:
        sorted_recs = sorted(ownership_records, key=lambda r: str(r.get("baalut_dt") or ""))
        # Отдаём СЫРЫЕ даты (YYYYMM) и тип, а не готовые подписи: анализ владения
        # (сколько времени у каждого владельца, перекупщики, частая перепродажа)
        # считается в интерфейсе, чтобы логика жила в одном месте и одинаково
        # работала и на локальном сервере, и на статическом сайте.
        report["ownership"]["records"] = [
            {"baalut_dt": str(r.get("baalut_dt") or ""), "baalut": r.get("baalut")}
            for r in sorted_recs
        ]

    for rid, period in SCRAPPED_RESOURCES:
        recs = results[f"scrapped::{rid}"]["records"]
        if recs:
            r = recs[0]
            report["scrapped"] = {
                "found": True, "period": period,
                "date": fmt_date(r.get("bitul_dt")) if r.get("bitul_dt") else None,
            }
            break

    if results["personal_import"]["records"]:
        r = results["personal_import"]["records"][0]
        report["personal_import"] = translate_val(r.get("sug_yevu")) if r.get("sug_yevu") else True

    recall_records = results["recall"]["records"]
    if recall_records:
        report["recalls"]["count"] = len(recall_records)
        report["recalls"]["records"] = [
            _row_to_kv(r, skip_keys={"MISPAR_RECHEV", "mispar_rechev"}) for r in recall_records
        ]

    if merged:
        specs_data = fetch_by_model(RESOURCE_SPECS, merged)
        price_data = fetch_by_model(RESOURCE_PRICE, merged)
        if specs_data["records"]:
            r = specs_data["records"][0]
            spec_rows = []
            for key in SPEC_FIELDS:
                val = r.get(key)
                if is_junk(key, val):
                    continue
                spec_rows.append({"key": key, "label": FIELD_LABELS.get(key, key), "value": fmt_val(key, val)})
            if spec_rows:
                report["specs"] = {
                    "rows": spec_rows,
                    "model_label": f"{r.get('degem_nm', '')} {r.get('shnat_yitzur', '')}".strip(),
                }
        if price_data["records"]:
            price_rows = []
            for r in price_data["records"]:
                if r.get("mehir"):
                    price_rows.append({"importer": r.get("shem_yevuan") or "יבואן", "price": r["mehir"]})
            report["price"] = price_rows

    return report
