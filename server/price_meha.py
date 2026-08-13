# -*- coding: utf-8 -*-
"""
server/price_meha.py — интеграция с מחירון העם (carlistprice.mot.gov.il), Часть 3 ТЗ.

СТАТУС: НЕ РЕАЛИЗОВАНО АВТОМАТИЧЕСКИ.

Что было сделано при подготовке проекта:
  - carlistprice.mot.gov.il отдаёт HTML-оболочку SPA (Angular/React) без содержимого —
    все данные подгружаются JS-кодом после загрузки страницы.
  - В окружении, где собирался этот проект, не было браузера с исполнением JS
    (headless Chrome/DevTools), поэтому не удалось вытащить реальные адреса API
    из скомпилированного бандла.
  - Попытки угадать типовые пути (assets/env.json, api/car-price/search и т.п.)
    результата не дали (пустой ответ/404) — угадывать дальше вслепую бессмысленно
    и создаёт лишнюю нагрузку на сервер министерства.

Что нужно от пользователя, чтобы включить эту интеграцию:
  1. Открыть https://carlistprice.mot.gov.il/ в Chrome.
  2. Открыть DevTools -> вкладка Network, оставить фильтр "Fetch/XHR".
  3. Ввести в поиске на сайте любую машину (например номер или модель+год).
  4. Найти в списке запросов тот, что вернул JSON с ценой (обычно POST или GET
     с "price"/"mehir"/"search" в пути).
  5. Правым кликом по запросу -> Copy -> Copy as cURL, прислать этот curl.

Как только появится реальный запрос, нужно:
  - вписать METHOD/URL/HEADERS/BODY ниже в функцию fetch_meha_price(),
  - подключить её вызов в server/live_api.py (добавить в build_report ещё один
    источник цены рядом с renderPrice/прайсом импортёров), и в export/export.py,
    если нужно тянуть данные и в статическую версию.

Ниже — рабочий каркас на requests/urllib, готовый принять реальные детали запроса.
"""

import json
import urllib.request

MEHA_BASE_URL = None  # TODO: вставить сюда реальный базовый URL API, когда он станет известен
MEHA_SEARCH_PATH = None  # TODO: путь эндпоинта поиска (например "/api/v1/search")


def is_configured() -> bool:
    return bool(MEHA_BASE_URL and MEHA_SEARCH_PATH)


def fetch_meha_price(tozeret_nm: str, degem_nm: str, shnat_yitzur, timeout=10):
    """Заглушка. Вернёт None, пока MEHA_BASE_URL не заполнен реальным адресом
    из DevTools. Как только появится рабочий запрос — реализовать здесь
    формирование query/тела запроса и разбор ответа в список
    [{"price": ..., "date": ..., "source": "מחירון העם"}]."""
    if not is_configured():
        return None
    url = f"{MEHA_BASE_URL}{MEHA_SEARCH_PATH}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "carcheck/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
