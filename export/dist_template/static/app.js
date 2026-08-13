// export/dist_template/static/app.js
// Статическая версия интерфейса (без сервера): живые данные тянутся прямо
// из data.gov.il в браузере (CORS там открыт — проверено в исходном прототипе
// carcheck.html), а накопленная история пробега/двигателя — поштучно, по одному
// номеру за раз, через Cloudflare Pages Function /api/history/<номер>, которая
// читает Cloudflare KV (см. functions/api/history/[plate].js и export/kv_upload.py).
// Никакого файла со всеми машинами сразу не существует — так исключается
// массовый скрейпинг накопленной базы (см. README, раздел "Деплой: Cloudflare
// Pages + Pages Functions + KV").
//
// Логика живых блоков — прямой перенос уже проверенного прототипа carcheck.html
// (тот же набор resource_id, тот же перевод полей). Дополнительно добавлен блок
// "Накопленная история" с тем же видом, что и в серверной версии server/static/app.js.

window.onerror = function (msg, src, line) {
  const el = document.getElementById("result");
  if (el) {
    el.innerHTML = `<div class="card"><div class="error">שגיאת JavaScript: ${msg}<br><small>שורה ${line}</small></div></div>` + el.innerHTML;
  }
  return false;
};

const RESOURCE_MAIN = "053cea08-09bc-40ec-8f7a-156f0677aff3";
const RESOURCE_HISTORY = "56063a99-8a3e-4ff4-912e-5966c0279bad";
const RESOURCE_TAV_NECHE = "c8b9f9c8-4612-4068-934f-d4acd2e3c06e";
const RESOURCE_OWNERSHIP = "bb2355dc-9ec7-4f06-9c3f-3344672171da";
const RESOURCE_MAIN_CONT = "0866573c-40cd-4ca8-91d2-9dd2d7a492e5";
const RESOURCE_RECALL = "36bf1404-0be4-49d2-82dc-2f1ead4a8b93";
const RESOURCE_ADAS = "83bfb278-7be1-4dab-ae2d-40125a923da1";
const RESOURCE_SPECS = "142afde2-6228-49f9-8a29-9b6c3a0cbe40";
const RESOURCE_PRICE = "39f455bf-6db0-4926-859d-017f34eacbcb";
const RESOURCE_TAXI = "cf29862d-ca25-4691-84f6-1be60dcb4a1e";
const RESOURCE_IMPORT = "03adc637-b6fe-402b-9937-7c3d3afc9140";
const SCRAPPED_RESOURCES = [
  ["851ecab1-0622-4dbe-a6c7-f950cf82abf9", "מ-2017"],
  ["4e6b9724-4c1e-43f0-909a-154d4cc4e046", "2010–2016"],
  ["ec8cbc34-72e1-4b69-9c48-22821ba0bd6c", "2000–2009"],
];
const RESOURCE_INACTIVE = "f6efe89a-fb3d-43a4-bb61-9bf12a9b9099";
const API_BASE = "https://data.gov.il/api/action/datastore_search";

const FIELD_LABELS = {
  mispar_rechev: "מספר רכב", tozeret_cd: "קוד יצרן", sug_degem: "סוג",
  tozeret_nm: "יצרן", degem_cd: "קוד דגם", degem_nm: "דגם",
  ramat_gimur: "רמת גימור", ramat_eivzur_betihuty: "רמת אבזור בטיחותי",
  kvutzat_zihum: "קבוצת זיהום", shnat_yitzur: "שנת ייצור", degem_manoa: "דגם מנוע",
  mivchan_acharon_dt: "מבחן אחרון", tokef_dt: "תוקף עד", baalut: "סוג בעלות",
  misgeret: "מספר שלדה (VIN)", tzeva_rechev: "צבע", tzeva_cd: "קוד צבע",
  zmig_kidmi: "צמיג קדמי", zmig_ahori: "צמיג אחורי", sug_delek_nm: "סוג דלק",
  horaat_rishum: "קוד רישום", moed_aliya_lakvish: "עליה לכביש",
  kinuy_mishari: "כינוי מסחרי", mispar_manoa: "מספר מנוע",
  kilometer_test_aharon: "קילומטראז' במבחן אחרון", rishum_rishon_dt: "תאריך רישום ראשון",
  shinui_mivne_ind: "שינוי מבנה", shnui_zeva_ind: "שינוי צבע",
  shinui_zmig_ind: "שינוי צמיג", gapam_ind: "מותקן גפ\"ם", mkoriut_nm: "מקוריות מרכב/צבע",
  "TAARICH HAFAKAT TAG": "תאריך הפקת תג", "SUG TAV": "סוג תו (קוד)",
  "MISPAR RECHEV": "מספר רכב", baalut_dt: "תאריך מעבר בעלות",
  RECALL_ID: "מספר קמפיין", SUG_RECALL: "סוג ריקול", SUG_TAKALA: "סוג תקלה",
  TEUR_TAKALA: "תיאור תקלה", TAARICH_PTICHA: "תאריך פתיחה",
  nikud_betihut: "ניקוד בטיחות", automatic_ind: "תיבת הילוכים", mispar_dlatot: "מספר דלתות",
  mispar_moshavim: "מספר מושבים", koah_sus: "הספק (כ\"ס)", nefah_manoa: "נפח מנוע (סמ\"ק)",
  mazgan_ind: "מזגן", abs_ind: "ABS", mispar_kariot_avir: "כריות אוויר",
  hege_koah_ind: "הגה כוח", merkav: "סוג מרכב", madad_yarok: "מדד ירוק",
  hanaa_nm: "הנעה", sug_tkina_nm: "תקן זיהום", bakarat_yatzivut_ind: "בקרת יציבות (ESP)",
  matzlemat_reverse_ind: "מצלמת רוורס", bakarat_shyut_adaptivit_ind: "בקרת שיוט אדפטיבית",
  zihuy_holchey_regel_ind: "זיהוי הולכי רגל", bakarat_stiya_menativ_ind: "בקרת סטייה מנתיב",
  nitur_merhak_milfanim_ind: "ניטור מרחק מלפנים", maarechet_ezer_labalam_ind: "מערכת עזר לבלימה",
  hayshaney_lahatz_avir_batzmigim_ind: "חיישני לחץ אוויר בצמיגים",
  kosher_grira_im_blamim: "כושר גרירה עם בלמים (ק\"ג)",
  kosher_grira_bli_blamim: "כושר גרירה בלי בלמים (ק\"ג)",
  mishkal_kolel: "משקל כולל מותר (ק\"ג)", mehir: "מחיר מחירון (₪)", shem_yevuan: "יבואן",
};

const SPEC_FIELDS = [
  "merkav", "koah_sus", "nefah_manoa", "hanaa_nm", "automatic_ind",
  "mispar_dlatot", "mispar_moshavim", "mishkal_kolel",
  "nikud_betihut", "ramat_eivzur_betihuty", "mispar_kariot_avir", "abs_ind",
  "bakarat_yatzivut_ind", "bakarat_stiya_menativ_ind", "nitur_merhak_milfanim_ind",
  "bakarat_shyut_adaptivit_ind", "zihuy_holchey_regel_ind", "maarechet_ezer_labalam_ind",
  "matzlemat_reverse_ind", "hayshaney_lahatz_avir_batzmigim_ind",
  "mazgan_ind", "hege_koah_ind", "kosher_grira_im_blamim", "kosher_grira_bli_blamim",
  "sug_tkina_nm", "madad_yarok", "kvutzat_zihum",
];

const HIDDEN_FIELDS = new Set(["rank", "_id", "tozeret_cd", "sug_degem", "degem_cd", "tzeva_cd"]);

// Значения מ-data.gov.il (баалут, топливо, цвет и т.д.) уже приходят на иврите —
// интерфейс тоже на иврите, поэтому переводить их больше не нужно (passthrough).
function translateVal(v) {
  return v;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmtDate(v) {
  if (!v) return null;
  const s = String(v);
  if (/^\d{8}$/.test(s)) return `${s.slice(6, 8)}.${s.slice(4, 6)}.${s.slice(0, 4)}`;
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return `${m[3]}.${m[2]}.${m[1]}`;
  if (/^\d{6}$/.test(s)) return `${s.slice(4, 6)}.${s.slice(0, 4)}`;
  return s;
}

function isDateField(key) { return /dt$|date|taarich/i.test(key); }

function normalizePlate(raw) {
  const digits = String(raw || "").replace(/\D/g, "");
  const stripped = digits.replace(/^0+/, "");
  return stripped || (digits ? "0" : "");
}

async function fetchResource(resourceId, plate) {
  const url = `${API_BASE}?resource_id=${resourceId}&q=${plate}&limit=50`;
  let res;
  try { res = await fetch(url); } catch (e) { throw new Error("רשת/CORS: " + e.message); }
  if (!res.ok) throw new Error("HTTP " + res.status);
  const data = await res.json();
  if (!data.success) throw new Error("ה-API החזיר success:false");
  const records = data.result.records || [];
  const target = normalizePlate(plate);
  const exact = records.filter(r => {
    const v = r.mispar_rechev ?? r.MISPAR_RECHEV ?? r["MISPAR RECHEV"] ?? "";
    return normalizePlate(v) === target;
  });
  return { records: exact.length ? exact : records };
}

async function fetchByModel(resourceId, car) {
  const cd = String(car.degem_cd ?? "");
  const attempts = [
    { tozeret_cd: String(car.tozeret_cd), degem_nm: car.degem_nm, shnat_yitzur: String(car.shnat_yitzur), degem_cd: cd.padStart(4, "0") },
    { tozeret_cd: String(car.tozeret_cd), degem_nm: car.degem_nm, shnat_yitzur: String(car.shnat_yitzur), degem_cd: cd },
    { tozeret_cd: String(car.tozeret_cd), degem_nm: car.degem_nm, shnat_yitzur: String(car.shnat_yitzur) },
    { tozeret_cd: String(car.tozeret_cd), degem_nm: car.degem_nm },
  ];
  for (const f of attempts) {
    try {
      const url = `${API_BASE}?resource_id=${resourceId}&filters=${encodeURIComponent(JSON.stringify(f))}&limit=5`;
      const res = await fetch(url);
      if (!res.ok) continue;
      const data = await res.json();
      if (data.success && data.result?.records?.length) return { records: data.result.records };
    } catch (e) { /* следующий вариант фильтра */ }
  }
  return { records: [] };
}

function testStatusBadge(dateStr) {
  if (!dateStr) return "";
  let d;
  const s = String(dateStr);
  d = /^\d{8}$/.test(s) ? new Date(`${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`) : new Date(s);
  if (isNaN(d)) return "";
  const diffDays = Math.round((d - new Date()) / 86400000);
  if (diffDays < 0) return `<span class="status bad">פג תוקף</span>`;
  if (diffDays < 30) return `<span class="status warn">עומד לפוג</span>`;
  return `<span class="status ok">תקף</span>`;
}

function renderMain(record) {
  if (!record) {
    return `<div class="card"><div class="empty">לא נמצא רכב עם המספר הזה במאגר משרד התחבורה.<br>בדקו את המספר (ללא רווחים ומקפים).</div></div>`;
  }
  const plate = record.mispar_rechev || "—";
  const model = [record.tozeret_nm, record.kinuy_mishari || record.degem_nm].filter(Boolean).join(" ");
  let rows = "";
  const priorityOrder = ["shnat_yitzur", "tzeva_rechev", "sug_delek_nm", "baalut",
    "kilometer_test_aharon", "mivchan_acharon_dt", "tokef_dt", "kvutzat_zihum",
    "ramat_eivzur_betihuty", "misgeret", "rishum_rishon_dt"];
  const shown = new Set(["mispar_rechev", "tozeret_nm", "kinuy_mishari", "degem_nm", "horaat_rishum", "moed_aliya_lakvish"]);
  for (const key of priorityOrder) {
    if (record[key] === undefined || record[key] === null || record[key] === "") continue;
    shown.add(key);
    let val = translateVal(record[key]);
    let extra = "";
    if (isDateField(key)) { val = fmtDate(val); if (key === "tokef_dt") extra = " " + testStatusBadge(record[key]); }
    rows += `<div class="row"><span class="k">${esc(FIELD_LABELS[key] || key)}</span><span class="v">${esc(val)}${extra}</span></div>`;
  }
  let otherRows = "";
  for (const key in record) {
    if (key.startsWith("_") || shown.has(key) || HIDDEN_FIELDS.has(key)) continue;
    let val = record[key];
    if (val === null || val === "") continue;
    if (isDateField(key)) val = fmtDate(val);
    val = translateVal(val);
    otherRows += `<div class="row"><span class="k">${esc(FIELD_LABELS[key] || key)}</span><span class="v">${esc(val)}</span></div>`;
  }
  return `<div class="card">
      <div class="car-title"><h2>${esc(model || "רכב")}</h2><span class="plate">${esc(plate)}</span></div>
      ${rows}
      <div class="src">מקור: מספרי רישוי של כלי רכב — המרשם הפעיל של משרד התחבורה,
      ובנוסף שדה הקילומטראז' מתוך היסטוריית כלי רכב פרטיים (1).</div>
    </div>
    ${otherRows ? `<div class="section-title">מידע נוסף</div><div class="card">${otherRows}</div>` : ""}`;
}

const AVG_KM_YEAR = 13500;

function renderMileageAnalysis(record) {
  const km = Number(record.kilometer_test_aharon);
  const year = Number(record.shnat_yitzur);
  if (!km || !year) return "";
  const age = Math.max(1, new Date().getFullYear() - year);
  const perYear = Math.round(km / age);
  const ratio = perYear / AVG_KM_YEAR;
  let verdict, cls, note = "";
  if (ratio < 0.55) { verdict = "נמוך משמעותית מהממוצע"; cls = "warn"; note = "קילומטראז' נמוך יכול להיות תקין (רכב שני במשפחה), אך יכול גם להעיד על מד קילומטרים מסובב. כדאי להשוות עם בלאי הריפוד, ההגה והדוושות."; }
  else if (ratio > 1.6) { verdict = "גבוה משמעותית מהממוצע"; cls = "warn"; note = "קילומטראז' גבוה מעיד לרוב על שימוש במונית/הפצה. כדאי לשים לב למצב המתלים והמנוע."; }
  else { verdict = "בטווח התקין"; cls = "ok"; }
  return `<div class="section-title">ניתוח קילומטראז'</div>
    <div class="card">
      <div class="row"><span class="k">קילומטראז' במבחן אחרון</span><span class="v">${km.toLocaleString("he-IL")} ק"מ</span></div>
      <div class="row"><span class="k">גיל הרכב</span><span class="v">${age} ${age === 1 ? "שנה" : "שנים"}</span></div>
      <div class="row"${note ? "" : ' style="border-bottom:none;"'}><span class="k">ממוצע לשנה</span>
        <span class="v">${perYear.toLocaleString("he-IL")} ק"מ <span class="status ${cls}">${verdict}</span></span></div>
      ${note ? `<div style="margin-top:10px;font-size:12.5px;color:var(--muted);line-height:1.5;">${note}</div>` : ""}
      <div class="src">הנורמה היא ${AVG_KM_YEAR.toLocaleString("he-IL")} ק"מ לשנה — קילומטראז' שנתי ממוצע לרכב פרטי (נתוני הלמ"ס).</div>
    </div>`;
}

function renderTavNeche(records) {
  if (!records || records.length === 0) {
    return `<div class="card"><div class="row" style="border-bottom:none;"><span class="k">תו נכה</span><span class="v"><span class="status ok">לא נמצא</span></span></div></div>`;
  }
  const dates = records.map(r => fmtDate(r["TAARICH HAFAKAT TAG"] ?? r.taarich_hafakat_tag)).filter(Boolean);
  return `<div class="card">
    <div class="row"><span class="k">תו נכה</span><span class="v"><span class="status warn">הונפק</span></span></div>
    ${dates.map(d => `<div class="row"><span class="k">תאריך הנפקה</span><span class="v">${esc(d)}</span></div>`).join("")}
  </div>`;
}

function renderOwnership(records) {
  if (!records || records.length === 0) {
    return `<div class="section-title">היסטוריית בעלות</div><div class="card"><div class="empty">אין נתונים — מאגר זה מכסה רק רכבים משנת 2017 ואילך.</div></div>`;
  }
  const sorted = records.slice().sort((a, b) => (a.baalut_dt || 0) - (b.baalut_dt || 0));
  const rows = sorted.map((r, i) => {
    const d = String(r.baalut_dt || "");
    const when = /^\d{6}$/.test(d) ? `${d.slice(4, 6)}.${d.slice(0, 4)}` : d;
    return `<div class="row"><span class="k">יד ${i + 1}</span><span class="v">${esc(translateVal(r.baalut) || "—")}${when ? ` · מ-${esc(when)}` : ""}</span></div>`;
  }).join("");
  return `<div class="section-title">היסטוריית בעלות</div><div class="card">
      <div class="row"><span class="k">סה"כ בעלים</span><span class="v">${records.length}</span></div>
      ${rows}
      <div class="src">מקור: היסטוריית כלי רכב פרטיים (2). שמות הבעלים אינם מתפרסמים על ידי המדינה. הכיסוי — רק רכבים משנת 2017 ואילך.</div>
    </div>`;
}

function renderInactive(records) {
  if (!records || records.length === 0) {
    return `<div class="card"><div class="row" style="border-bottom:none;"><span class="k">סטטוס במרשם</span><span class="v"><span class="status ok">פעיל</span></span></div></div>`;
  }
  return `<div class="card">
    <div class="row"><span class="k">סטטוס במרשם</span><span class="v"><span class="status bad">הוסר מהמרשם / לא פעיל</span></span></div>
    <div style="margin-top:8px; font-size:12.5px; color:var(--muted);">הסיבה אינה מתפרסמת על ידי המדינה.</div>
  </div>`;
}

function fmtVal(key, val) {
  if (key === "automatic_ind") return (val === 1 || val === "1") ? "אוטומט" : "ידני";
  if (/_ind$/.test(key)) { if (val === 1 || val === "1") return "כן"; if (val === 0 || val === "0") return "לא"; }
  if (isDateField(key)) return fmtDate(val);
  return translateVal(val);
}

function isJunk(key, val) {
  if (val === null || val === undefined || val === "") return true;
  if (typeof val === "string" && /לא ידוע/.test(val)) return true;
  if (/^kosher_grira/.test(key) && Number(val) === 0) return true;
  return false;
}

function renderRecalls(records) {
  if (!records || records.length === 0) {
    return `<div class="card"><div class="row" style="border-bottom:none;"><span class="k">ריקול לא מטופל</span><span class="v"><span class="status ok">לא</span></span></div></div>`;
  }
  const items = records.map(r => {
    let rows = "";
    for (const key in r) {
      if (key.startsWith("_") || HIDDEN_FIELDS.has(key) || /MISPAR_RECHEV/i.test(key)) continue;
      let val = r[key];
      if (val === null || val === "") continue;
      rows += `<div class="row"><span class="k">${esc(FIELD_LABELS[key] || key)}</span><span class="v">${esc(fmtVal(key, val))}</span></div>`;
    }
    return `<div class="card">${rows}</div>`;
  }).join("");
  return `<div class="card"><div class="row" style="border-bottom:none;"><span class="k">ריקול לא מטופל</span><span class="v"><span class="status bad">יש: ${records.length}</span></span></div></div>${items}`;
}

function renderScrapped(hits) {
  const found = hits.filter(h => h.records.length > 0);
  if (!found.length) {
    return `<div class="card"><div class="row" style="border-bottom:none;"><span class="k">גריעה סופית</span><span class="v"><span class="status ok">לא</span></span></div></div>`;
  }
  const r = found[0].records[0];
  const when = r.bitul_dt ? fmtDate(r.bitul_dt) : "";
  return `<div class="card">
    <div class="row"><span class="k">גריעה סופית</span><span class="v"><span class="status bad">כן — הוסר מהכביש</span></span></div>
    ${when ? `<div class="row"><span class="k">תאריך גריעה</span><span class="v">${esc(when)}</span></div>` : ""}
  </div>`;
}

function renderUsage(taxiRecords, importRecords) {
  let rows = `<div class="row"><span class="k">מונית / תחבורה ציבורית</span><span class="v">${taxiRecords && taxiRecords.length ? '<span class="status bad">רשום ככזה</span>' : '<span class="status ok">לא</span>'}</span></div>`;
  const imp = importRecords && importRecords.length ? importRecords[0] : null;
  rows += `<div class="row" style="border-bottom:none;"><span class="k">יבוא אישי</span><span class="v">${imp ? `<span class="status warn">כן${imp.sug_yevu ? " · " + esc(translateVal(imp.sug_yevu)) : ""}</span>` : '<span class="status ok">לא</span>'}</span></div>`;
  return `<div class="card">${rows}</div>`;
}

function renderAdas(records) {
  const has = records && records.length > 0;
  return `<div class="card"><div class="row" style="border-bottom:none;"><span class="k">מערכת בטיחות (Mobileye וכו׳)</span><span class="v">${has ? '<span class="status ok">מותקנת</span>' : '<span class="status warn">לא רשומה</span>'}</span></div></div>`;
}

function renderSpecs(records) {
  if (!records || !records.length) return "";
  const r = records[0];
  let rows = "";
  for (const key of SPEC_FIELDS) {
    const val = r[key];
    if (isJunk(key, val)) continue;
    rows += `<div class="row"><span class="k">${esc(FIELD_LABELS[key] || key)}</span><span class="v">${esc(fmtVal(key, val))}</span></div>`;
  }
  if (!rows) return "";
  return `<div class="section-title">אבזור לפי קטלוג הדגם</div><div class="card">${rows}
      <div class="src"><b>נתוני היצרן של דגם ${esc(r.degem_nm || "")} ${esc(String(r.shnat_yitzur || ""))}, לא בדיקה של הרכב הספציפי.</b></div>
    </div>`;
}

function renderPrice(records) {
  if (!records || !records.length) return "";
  const rows = records.map(r => {
    const price = r.mehir ? Number(r.mehir).toLocaleString("he-IL") : null;
    if (!price) return "";
    return `<div class="row"><span class="k">${esc(r.shem_yevuan || "יבואן")}</span><span class="v">${price} ₪</span></div>`;
  }).join("");
  if (!rows) return "";
  return `<div class="section-title">מחיר לפי מחירון בעת ההשקה</div><div class="card">${rows}</div>`;
}

function renderExternalLinks(plate) {
  return `<div class="section-title">מידע נוסף (מקור חיצוני)</div><div class="card">
    <div class="row" style="border-bottom:none;">
      <span class="k">טוטל לוס / היסטוריית ביטוח</span>
      <a href="https://infocar.co.il/" target="_blank" style="color:var(--accent); font-weight:600;">פתיחה ↗</a>
    </div>
    <div style="margin-top:12px; font-size:12px; color:var(--muted);">הזינו את המספר ${esc(plate)} ידנית — מקור זה אינו תומך בפנייה ישירה.</div>
  </div>`;
}

// ---- накопленная история через /api/history/<номер> (Cloudflare Pages Function + KV) ----

function sparkline(points) {
  if (points.length < 2) return "";
  const w = 520, h = 110, pad = 8;
  const ys = points.map(p => p.km);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanY = (maxY - minY) || 1;
  const stepX = (w - pad * 2) / Math.max(1, points.length - 1);
  const coords = points.map((p, i) => {
    const x = pad + i * stepX;
    const y = h - pad - ((p.km - minY) / spanY) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return `<svg class="odo-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <polyline points="${coords.join(" ")}" fill="none" stroke="#4fb0ff" stroke-width="2.5"/>
    ${coords.map(c => `<circle cx="${c.split(",")[0]}" cy="${c.split(",")[1]}" r="3" fill="#33d69f"/>`).join("")}
  </svg>`;
}

async function fetchHistory(plate) {
  // Накопленная история отдаётся ТОЛЬКО поштучно, через Cloudflare Pages Function
  // /api/history/<номер> -> Cloudflare KV. Никакого файла со всеми машинами сразу
  // не существует — так исключается массовый скрейпинг базы (см. README, раздел
  // "Деплой: Cloudflare Pages + Pages Functions + KV").
  try {
    const res = await fetch(`/api/history/${plate}`, { cache: "no-store" });
    if (res.status === 429) return { rateLimited: true };   // штатная ситуация — не ошибка
    if (res.status === 404) return null;                     // штатная ситуация — просто не накоплено
    if (!res.ok) return { fetchError: true };
    return await res.json();
  } catch (e) {
    return { fetchError: true };
  }
}

function renderLocalHistory(local) {
  let html = `<div class="section-title">היסטוריה שנצברה (מאגר עצמאי)</div>`;
  if (local && local.rateLimited) {
    html += `<div class="card"><div class="empty">חריגה ממכסת הבקשות להיסטוריה מהכתובת שלכם —
      נסו שוב בעוד דקה. החיפוש החי למעלה ממשיך לפעול כרגיל, הוא אינו מוגבל.</div></div>`;
    return html;
  }
  if (local && local.fetchError) {
    html += `<div class="card"><div class="empty">היסטוריית הקילומטראז' אינה זמינה כרגע (שגיאת רשת).
      החיפוש החי למעלה ממשיך לפעול כרגיל.</div></div>`;
    return html;
  }
  if (!local || local.available === false) {
    html += `<div class="card"><div class="empty">היסטוריית הקילומטראז' של מספר זה טרם נצברה
      (או שהמספר אינו מכוסה, או שעדיין לא היה צילום שבועי שני).</div></div>`;
    return html;
  }
  if (local.engine_changes && local.engine_changes.length) {
    html += `<div class="alert-block"><div class="alert-title">⚠️ זוהה שינוי במספר המנוע</div>
      ${local.engine_changes.map(c => `<div class="row">
        <span class="k">${esc((c.date || "").slice(0, 10))}</span>
        <span class="v">${esc(c.old_engine)} ← ${esc(c.new_engine)}${c.km ? ` (ב-${Number(c.km).toLocaleString("he-IL")} ק"מ)` : ""}</span>
      </div>`).join("")}
      <div class="src">החלפת מנוע בין שני צילומי מצב שבועיים של משרד התחבורה.</div>
    </div>`;
  }
  if (local.anomalies && local.anomalies.length) {
    html += `<div class="alert-block"><div class="alert-title">⚠️ הקילומטראז' ירד בין הצילומים — חשד לסיבוב מד ק"מ אחורה</div>
      ${local.anomalies.map(a => `<div class="row">
        <span class="k">${esc((a.date || "").slice(0, 10))}</span>
        <span class="v">${Number(a.prev_km).toLocaleString("he-IL")} ק"מ ← ${Number(a.new_km).toLocaleString("he-IL")} ק"מ</span>
      </div>`).join("")}
    </div>`;
  }
  if (local.odometer && local.odometer.length) {
    const rows = local.odometer.map(p => `<tr><td>${esc((p.date || "").slice(0, 10))}</td><td>${p.km != null ? Number(p.km).toLocaleString("he-IL") + ' ק"מ' : "—"}</td></tr>`).join("");
    html += `<div class="card">
      <div style="font-size:13px;color:var(--muted);margin-bottom:4px;">היסטוריית קריאות מד הקילומטראז'</div>
      ${sparkline(local.odometer.filter(p => p.km != null))}
      <table class="odo-table"><thead><tr><th>תאריך צילום</th><th>קילומטראז'</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="src">נצבר אחת לשבוע (GitHub Actions או מאסף מקומי), לא מתפרסם על ידי משרד התחבורה בשום צורה אחרת.</div>
    </div>`;
  } else {
    html += `<div class="card"><div class="empty">טרם נאספו קריאות של מד הקילומטראז'.</div></div>`;
  }
  return html;
}

const LIMITATIONS = [
  "האבזור לפי קטלוג הדגם — נתוני יצרן של הדגם, לא בדיקה של הרכב הספציפי.",
  "הקילומטראז' ממאגר המדינה — רק הקריאה האחרונה בעת מבחן הרישוי.",
  "מאגרי הקילומטראז' והבעלות מכסים רק רכבים שנרשמו החל משנת 2017.",
];

async function search() {
  const btn = document.getElementById("searchBtn");
  const original = btn.textContent;
  btn.textContent = "...";
  btn.disabled = true;

  const plate = document.getElementById("plateInput").value.trim().replace(/\D/g, "");
  const resultEl = document.getElementById("result");
  if (!plate) {
    resultEl.innerHTML = `<div class="error">יש להזין מספר רכב (ספרות בלבד).</div>`;
    btn.textContent = original; btn.disabled = false;
    return;
  }
  resultEl.innerHTML = `<div class="loading"><div class="spinner"></div>מחפש נתונים...</div>`;

  const errors = [];
  let mainData = { records: [] }, historyData = { records: [] };

  try { mainData = await fetchResource(RESOURCE_MAIN, plate); } catch (e) { errors.push("מרשם ראשי: " + e.message); }
  if (mainData.records.length === 0) {
    try { const cont = await fetchResource(RESOURCE_MAIN_CONT, plate); if (cont.records.length) mainData = cont; } catch (e) { /* ignore */ }
  }

  const safe = id => fetchResource(id, plate).catch(e => ({ records: [], error: e.message }));

  const [historyData2, tavNecheData, ownershipData, inactiveData, recallData, adasData,
    taxiData, importData, accumulatedHistory, ...scrapRaw] = await Promise.all([
      safe(RESOURCE_HISTORY), safe(RESOURCE_TAV_NECHE), safe(RESOURCE_OWNERSHIP), safe(RESOURCE_INACTIVE),
      safe(RESOURCE_RECALL), safe(RESOURCE_ADAS), safe(RESOURCE_TAXI), safe(RESOURCE_IMPORT),
      fetchHistory(plate),
      ...SCRAPPED_RESOURCES.map(([id]) => safe(id)),
    ]);
  historyData = historyData2;
  if (historyData.error) errors.push("היסטוריה/קילומטראז': " + historyData.error);

  const scrapHits = SCRAPPED_RESOURCES.map(([id, period], i) => ({ id, period, records: scrapRaw[i].records || [] }));

  let html = "";
  const mainRecord = mainData.records[0];
  const historyRecord = historyData.records[0];
  const merged = mainRecord ? Object.assign({}, mainRecord, historyRecord || {}) : null;

  html += renderMain(merged);
  if (merged) html += renderMileageAnalysis(merged);
  html += renderLocalHistory(accumulatedHistory);

  html += `<div class="section-title">סטטוס ושימוש</div>`;
  html += renderScrapped(scrapHits);
  html += renderUsage(taxiData.records, importData.records);
  html += renderInactive(inactiveData.records);
  html += `<div class="section-title">תו נכה</div>` + renderTavNeche(tavNecheData.records);
  html += renderOwnership(ownershipData.records);
  html += `<div class="section-title">בטיחות וריקולים</div>`;
  html += renderRecalls(recallData.records);
  html += renderAdas(adasData.records);

  if (mainRecord) {
    let specsData = { records: [] }, priceData = { records: [] };
    try { specsData = await fetchByModel(RESOURCE_SPECS, mainRecord); } catch (e) { /* ignore */ }
    try { priceData = await fetchByModel(RESOURCE_PRICE, mainRecord); } catch (e) { /* ignore */ }
    html += renderSpecs(specsData.records);
    html += renderPrice(priceData.records);
  }

  html += renderExternalLinks(plate);
  html += `<div class="limitations"><b>מגבלות הנתונים:</b><br>${LIMITATIONS.join("<br>")}</div>`;

  if (errors.length) {
    html += `<div class="card"><div class="error" style="padding:10px 0;">⚠️ ${errors.map(esc).join("<br>")}</div></div>`;
  }

  resultEl.innerHTML = html;
  btn.textContent = original;
  btn.disabled = false;
}

document.getElementById("searchBtn").addEventListener("click", search);
document.getElementById("plateInput").addEventListener("keydown", e => { if (e.key === "Enter") search(); });

// meta.json — только агрегированные публичные счётчики (без данных по конкретным
// машинам), лежит в корне сайта рядом с index.html, ничего защищать тут не нужно.
fetch("meta.json", { cache: "no-store" }).then(r => r.ok ? r.json() : null).then(m => {
  if (!m) return;
  const el = document.getElementById("metaLine");
  if (el) el.textContent = `מאגר שנצבר: ${m.snapshots_count} צילומים, ${m.plates_covered} רכבים, עודכן ${(m.updated_at || "").slice(0, 16).replace("T", " ")}`;
}).catch(() => {});
