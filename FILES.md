# Карта файлов проекта carcheck

Ниже — точная структура, куда какой файл положить, чтобы получился рабочий
репозиторий. Регистр и точки в путях важны.

```
carcheck/
│
├── README.md                              ← общая инструкция (GitHub Actions, опционально Tailscale/Планировщик)
├── FILES.md                                ← этот файл
├── requirements.txt                        ← Flask==3.0.3 (единственная внешняя зависимость)
├── .gitignore                              ← исключает archive/, logs/, секреты сервера, .venv, dist/
├── run_server.bat                          ← опционально: локальный сервер
├── run_collector.bat                       ← опционально: только сборщик локально
├── run_all.bat                             ← опционально: сборщик + экспорт локально одной командой
│
├── .github/
│   └── workflows/
│       └── weekly.yml                      ← ОСНОВНОЙ сценарий: еженедельный сбор+экспорт на GitHub Actions
│
├── shared/
│   ├── __init__.py                         ← пустой файл (делает папку пакетом Python)
│   ├── refdata.py                          ← resource_id датасетов, слаги, переводы полей
│   └── formatting.py                       ← даты, статусы теста, normalize_plate, анализ пробега
│
├── collector/
│   ├── __init__.py
│   ├── config.py                           ← пути к БД/архиву/логам
│   ├── db.py                               ← схема SQLite, транзакции
│   ├── meta.py                             ← package_show, потоковое скачивание CSV
│   ├── csv_loader.py                       ← автоопределение разделителя/кодировки, загрузка в staging
│   ├── collector.py                        ← точка входа: python collector/collector.py
│   ├── db/                                 ← ПУСТАЯ папка на старте — carcheck.sqlite3 создастся сама
│   ├── archive/                            ← ПУСТАЯ папка на старте — снимки CSV (только локальный сценарий)
│   └── logs/                               ← ПУСТАЯ папка на старте — collector.log
│
├── server/                                 ← опциональный локальный сервер
│   ├── __init__.py
│   ├── config.py                           ← токен доступа, HOST/PORT, secret key
│   ├── app.py                              ← Flask-приложение: python server/app.py
│   ├── live_api.py                         ← живой опрос госбаз (порт логики carcheck.html)
│   ├── history_api.py                      ← чтение накопленной SQLite (одометр/двигатель/аномалии)
│   ├── price_meha.py                       ← заготовка под מחירון העם, требует данных из DevTools
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── style.css
│       └── app.js
│
└── export/
    ├── __init__.py
    ├── export.py                           ← собирает статический сайт в dist/ + агрегированный meta.json
    ├── kv_upload.py                         ← заливает историю по машинам в Cloudflare KV (отдельно от сайта!)
    └── dist_template/                      ← шаблон, который export.py копирует в dist/
        ├── index.html
        ├── static/
        │   ├── style.css
        │   └── app.js
        └── functions/
            └── api/
                └── history/
                    └── [plate].js          ← Cloudflare Pages Function: история ТОЛЬКО по одному номеру
```

**Важно про `export/`:** данные по конкретным машинам (пробег/двигатель/аномалии) не
попадают ни в `dist/`, ни в git вообще — они уходят напрямую в Cloudflare KV через
`kv_upload.py` и REST API Cloudflare. В репозитории и на самом сайте лежит только код
и агрегированный `meta.json` (общие счётчики, без разбивки по номерам). Так исключается
массовая выгрузка базы — прочитать можно только один номер за раз, через функцию.

## Папки, которые нужно создать пустыми

Git не хранит пустые папки — если будете собирать репозиторий вручную (не через
`git init` из уже готовой структуры), создайте пустыми (или положите `.gitkeep`):

- `collector/db/`
- `collector/archive/`
- `collector/logs/`

Они создадутся автоматически сами при первом запуске сборщика (`os.makedirs(...,
exist_ok=True)` в коде), так что можно просто ничего не делать — Python сам создаст
их при первом обращении.

## Порядок действий после того, как файлы разложены

См. README.md, раздел "Основной сценарий: GitHub Actions" — короткая версия:

```
git init
git add .
git commit -m "carcheck: первая версия"
git branch -M main
git remote add origin https://github.com/<логин>/carcheck.git
git push -u origin main
```

Дальше — включить права записи для Actions и запустить workflow вручную первый раз
(подробности в README.md).
