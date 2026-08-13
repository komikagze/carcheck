# -*- coding: utf-8 -*-
"""
shared/refdata.py

Единый справочник для всего проекта carcheck: resource_id датасетов data.gov.il,
слаги пакетов для package_show, перевод названий полей и значений с иврита на русский.

Используется и сборщиком (collector), и сервером (server), и экспортёром (export),
чтобы resource_id и переводы не расходились в трёх местах.

Все ID и слаги перенесены из проверенного прототипа carcheck.html и из BRIEF.md.
НЕ менять resource_id "на глаз" — они уже проверены живыми запросами.
"""

API_BASE = "https://data.gov.il/api/action/datastore_search"
API_BASE_V3 = "https://data.gov.il/api/3/action"  # package_show, package_list

# ---------------------------------------------------------------------------
# "Живые" ресурсы — опрашиваются на каждый запрос напрямую (маленькие/на лету)
# ---------------------------------------------------------------------------

RESOURCE_MAIN = "053cea08-09bc-40ec-8f7a-156f0677aff3"          # основной реестр (826 МБ)
RESOURCE_MAIN_CONT = "0866573c-40cd-4ca8-91d2-9dd2d7a492e5"      # продолжение реестра, запасной источник (288 МБ)
RESOURCE_HISTORY = "56063a99-8a3e-4ff4-912e-5966c0279bad"        # пробег + номер двигателя (155 МБ) — СНИМАЕТСЯ сборщиком
RESOURCE_TAV_NECHE = "c8b9f9c8-4612-4068-934f-d4acd2e3c06e"      # тав нехе (инвалидный знак)
RESOURCE_OWNERSHIP = "bb2355dc-9ec7-4f06-9c3f-3344672171da"      # история владения (162 МБ) — СНИМАЕТСЯ сборщиком
RESOURCE_INACTIVE = "f6efe89a-fb3d-43a4-bb61-9bf12a9b9099"       # неактивна / снята с учёта

RESOURCE_RECALL = "36bf1404-0be4-49d2-82dc-2f1ead4a8b93"         # невыполненный отзыв
RESOURCE_ADAS = "83bfb278-7be1-4dab-ae2d-40125a923da1"           # скидка на агру за систему безопасности
RESOURCE_SPECS = "142afde2-6228-49f9-8a29-9b6c3a0cbe40"          # каталог моделей (комплектация/безопасность/выбросы)
RESOURCE_PRICE = "39f455bf-6db0-4926-859d-017f34eacbcb"          # прайс импортёров, с 1996 г.
RESOURCE_TAXI = "cf29862d-ca25-4691-84f6-1be60dcb4a1e"           # такси / общественный транспорт
RESOURCE_IMPORT = "03adc637-b6fe-402b-9937-7c3d3afc9140"        # личный импорт

# окончательное списание — три периода, покрывают историю с 2000 г.
# значения периодов идут в отчёт напрямую (пользовательский текст) — на иврите
SCRAPPED_RESOURCES = [
    ("851ecab1-0622-4dbe-a6c7-f950cf82abf9", "מ-2017"),
    ("4e6b9724-4c1e-43f0-909a-154d4cc4e046", "2010–2016"),
    ("ec8cbc34-72e1-4b69-9c48-22821ba0bd6c", "2000–2009"),
]

# ---------------------------------------------------------------------------
# Ресурсы, которые НАКАПЛИВАЕТ сборщик (Часть 1 ТЗ) — самое ценное:
# история пробега и смена номера двигателя, история владения.
# ---------------------------------------------------------------------------

COLLECTED_RESOURCES = {
    "history": RESOURCE_HISTORY,     # 155 МБ — snake_case поля
    "ownership": RESOURCE_OWNERSHIP,  # 162 МБ — snake_case поля
}

# Слаги пакетов (для package_show) — все датасеты проекта, включая не собираемые,
# чтобы meta_archive хранил снимок метаданных по всем.
DATASET_SLUGS = {
    "shinui_mivne": "shinui_mivne",  # содержит и history, и ownership resource
    "main_registry": "private-and-commercial-vehicles",
    "scrapped_final": "reshev_bitul_sofi",
    "tav_neche": "rechev-tag-nachim",
    "recall": "hagbalat_recall",
    "adas": "zakaut-hatkana",
    "personal_import": "personal_import_vehicles",
    "taxi": "kli_rechev_ciburiim",
    "specs": "degem-rechev-wltp",
    "price": "mehir_yevuan",
    "inactive": "rechev_le_pail_with_degem",
}

# ---------------------------------------------------------------------------
# Перевод названий полей (техническое имя -> подпись на иврите для интерфейса)
# ---------------------------------------------------------------------------

FIELD_LABELS = {
    "mispar_rechev": "מספר רכב",
    "tozeret_cd": "קוד יצרן",
    "sug_degem": "סוג",
    "tozeret_nm": "יצרן",
    "degem_cd": "קוד דגם",
    "degem_nm": "דגם",
    "ramat_gimur": "רמת גימור",
    "ramat_eivzur_betihuty": "רמת אבזור בטיחותי",
    "kvutzat_zihum": "קבוצת זיהום",
    "shnat_yitzur": "שנת ייצור",
    "degem_manoa": "דגם מנוע",
    "mivchan_acharon_dt": "מבחן אחרון",
    "tokef_dt": "תוקף עד",
    "baalut": "סוג בעלות",
    "misgeret": "מספר שלדה (VIN)",
    "tzeva_rechev": "צבע",
    "tzeva_cd": "קוד צבע",
    "zmig_kidmi": "צמיג קדמי",
    "zmig_ahori": "צמיג אחורי",
    "sug_delek_nm": "סוג דלק",
    "horaat_rishum": "קוד רישום",
    "moed_aliya_lakvish": "עליה לכביש",
    "kinuy_mishari": "כינוי מסחרי",
    "mispar_manoa": "מספר מנוע",
    "kilometer_test_aharon": "קילומטראז' במבחן אחרון",
    "rishum_rishon_dt": "תאריך רישום ראשון",
    "shinui_mivne_ind": "שינוי מבנה",
    "shnui_zeva_ind": "שינוי צבע",
    "shinui_zmig_ind": "שינוי צמיג",
    "gapam_ind": "מותקן גפ\"ם",
    "mkoriut_nm": "מקוריות מרכב/צבע",
    "TAARICH HAFAKAT TAG": "תאריך הפקת תג",
    "SUG TAV": "סוג תו (קוד)",
    "MISPAR RECHEV": "מספר רכב",
    "baalut_dt": "תאריך מעבר בעלות",
    "RECALL_ID": "מספר קמפיין",
    "SUG_RECALL": "סוג ריקול",
    "SUG_TAKALA": "סוג תקלה",
    "TEUR_TAKALA": "תיאור תקלה",
    "TAARICH_PTICHA": "תאריך פתיחה",
    "nikud_betihut": "ניקוד בטיחות",
    "automatic_ind": "תיבת הילוכים",
    "mispar_dlatot": "מספר דלתות",
    "mispar_moshavim": "מספר מושבים",
    "koah_sus": "הספק (כ\"ס)",
    "nefah_manoa": "נפח מנוע (סמ\"ק)",
    "mazgan_ind": "מזגן",
    "abs_ind": "ABS",
    "mispar_kariot_avir": "כריות אוויר",
    "hege_koah_ind": "הגה כוח",
    "merkav": "סוג מרכב",
    "madad_yarok": "מדד ירוק",
    "hanaa_nm": "הנעה",
    "sug_tkina_nm": "תקן זיהום",
    "bakarat_yatzivut_ind": "בקרת יציבות (ESP)",
    "matzlemat_reverse_ind": "מצלמת רוורס",
    "bakarat_shyut_adaptivit_ind": "בקרת שיוט אדפטיבית",
    "zihuy_holchey_regel_ind": "זיהוי הולכי רגל",
    "bakarat_stiya_menativ_ind": "בקרת סטייה מנתיב",
    "nitur_merhak_milfanim_ind": "ניטור מרחק מלפנים",
    "maarechet_ezer_labalam_ind": "מערכת עזר לבלימה",
    "hayshaney_lahatz_avir_batzmigim_ind": "חיישני לחץ אוויר בצמיגים",
    "kosher_grira_im_blamim": "כושר גרירה עם בלמים (ק\"ג)",
    "kosher_grira_bli_blamim": "כושר גרירה בלי בלמים (ק\"ג)",
    "mishkal_kolel": "משקל כולל מותר (ק\"ג)",
    "mehir": "מחיר מחירון (₪)",
    "shem_yevuan": "יבואן",
}

# поля каталога моделей, которые показываем (остальные ~70 скрываем)
SPEC_FIELDS = [
    "merkav", "koah_sus", "nefah_manoa", "hanaa_nm", "automatic_ind",
    "mispar_dlatot", "mispar_moshavim", "mishkal_kolel",
    "nikud_betihut", "ramat_eivzur_betihuty", "mispar_kariot_avir", "abs_ind",
    "bakarat_yatzivut_ind", "bakarat_stiya_menativ_ind", "nitur_merhak_milfanim_ind",
    "bakarat_shyut_adaptivit_ind", "zihuy_holchey_regel_ind", "maarechet_ezer_labalam_ind",
    "matzlemat_reverse_ind", "hayshaney_lahatz_avir_batzmigim_ind",
    "mazgan_ind", "hege_koah_ind",
    "kosher_grira_im_blamim", "kosher_grira_bli_blamim",
    "sug_tkina_nm", "madad_yarok", "kvutzat_zihum",
]

# служебные/технические поля без пользы — не показываем вообще
HIDDEN_FIELDS = {"rank", "_id", "tozeret_cd", "sug_degem", "degem_cd", "tzeva_cd"}

# Значения из data.gov.il (тип владения, топливо, цвет и т.д.) уже приходят на
# иврите — интерфейс тоже на иврите, поэтому переводить их больше не нужно
# (см. translate_val в shared/formatting.py — теперь это passthrough).

AVG_KM_YEAR = 13500  # средний годовой пробег частного авто в Израиле (по данным ЦБС)

# Тестовые номера из ТЗ — используются в скрипте самопроверки сервера.
# Описания (значения словаря) идут в атрибут title кнопки в интерфейсе — на иврите.
TEST_PLATES = {
    "5156286": "סוזוקי בלנו 2017 — קילומטראז' כ-129,982, בעלים 1 מאז 04/2017, אין תו נכה",
    "2823923": "סובארו פורסטר 2002 — אין היסטוריה/בעלות (ותיק מ-2017), אך יש הנחת מערכת בטיחות (ADAS)",
    "2947251": "טויוטה הילוקס 2004 — אין היסטוריה/בעלות",
}
