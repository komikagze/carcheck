// server/static/app.js
// Клиентский рендер отчёта. Сервер отдаёт готовый JSON (см. server/live_api.py
// build_report + server/history_api.py get_local_data), эта функция превращает
// его в HTML-карточки — тот же визуальный язык, что был в прототипе carcheck.html,
// плюс новые блоки: история одометра, смена двигателя, аномалии пробега.

const STATUS_LABELS = { ok: "תקף", warn: "עומד לפוג", bad: "פג תוקף" };

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function statusBadge(cls) {
  if (!cls) return "";
  return `<span class="status ${cls}">${STATUS_LABELS[cls] || cls}</span>`;
}

function renderRows(rows) {
  return rows.map(r => `<div class="row"><span class="k">${esc(r.label)}</span>
    <span class="v">${esc(r.value)}${r.status ? " " + statusBadge(r.status) : ""}</span></div>`).join("");
}

function renderMain(report) {
  if (!report.main) {
    return `<div class="card"><div class="empty">לא נמצא רכב עם המספר הזה במאגר משרד התחבורה.<br>
      בדקו את המספר (ללא רווחים ומקפים).</div></div>`;
  }
  const m = report.main;
  let html = `<div class="card">
    <div class="car-title"><h2>${esc(m.model)}</h2><span class="plate">${esc(m.plate)}</span></div>
    ${renderRows(m.rows)}
    <div class="src">מקור: מספרי רישוי של כלי רכב — המרשם הפעיל של משרד התחבורה,
    ובנוסף שדה הקילומטראז' מתוך היסטוריית כלי רכב פרטיים (1).</div>
  </div>`;
  if (report.main_extra && report.main_extra.length) {
    html += `<div class="section-title">מידע נוסף</div><div class="card">
      ${renderRows(report.main_extra.map(r => ({ label: r.label, value: r.value })))}
    </div>`;
  }
  return html;
}

function renderMileage(a) {
  if (!a) return "";
  const yearsWord = a.age_years === 1 ? "שנה" : "שנים";
  return `<div class="section-title">ניתוח קילומטראז'</div>
    <div class="card">
      <div class="row"><span class="k">קילומטראז' במבחן אחרון</span>
        <span class="v">${a.km.toLocaleString("he-IL")} ק"מ</span></div>
      <div class="row"><span class="k">גיל הרכב</span><span class="v">${a.age_years} ${yearsWord}</span></div>
      <div class="row"${a.note ? "" : ' style="border-bottom:none;"'}><span class="k">ממוצע לשנה</span>
        <span class="v">${a.km_per_year.toLocaleString("he-IL")} ק"מ
        <span class="status ${a.verdict_class}">${esc(a.verdict)}</span></span></div>
      ${a.note ? `<div style="margin-top:10px;font-size:12.5px;color:var(--muted);line-height:1.5;">${esc(a.note)}</div>` : ""}
      <div class="src">קילומטראז': היסטוריית כלי רכב פרטיים, שדה «נסועה במועד טסט אחרון».
      הנורמה היא ${a.avg_km_year.toLocaleString("he-IL")} ק"מ לשנה — קילומטראז' שנתי ממוצע לרכב פרטי (נתוני הלמ"ס).
      החישוב מקורב: הקילומטראז' מחולק בגיל הרכב.</div>
    </div>`;
}

function renderStatusBlock(report) {
  let html = `<div class="section-title">סטטוס ושימוש</div>`;

  if (report.scrapped.found) {
    html += `<div class="card">
      <div class="row"><span class="k">גריעה סופית</span>
        <span class="v"><span class="status bad">כן — הוסר מהכביש</span></span></div>
      ${report.scrapped.date ? `<div class="row"><span class="k">תאריך גריעה</span><span class="v">${esc(report.scrapped.date)}</span></div>` : ""}
      <div class="src">מקור: כלי רכב שירדו מהכביש ובסטטוס ביטול סופי (תקופה: ${esc(report.scrapped.period)}).
      הרכב רשום כמבוטל סופית ואינו יכול לחזור לכביש.</div>
    </div>`;
  } else {
    html += `<div class="card"><div class="row" style="border-bottom:none;">
      <span class="k">גריעה סופית<br><small style="color:var(--muted);">ביטול סופי — נבדק החל משנת 2000</small></span>
      <span class="v"><span class="status ok">לא</span></span></div></div>`;
  }

  html += `<div class="card">
    <div class="row"><span class="k">מונית / תחבורה ציבורית</span>
      <span class="v">${report.taxi ? '<span class="status bad">רשום ככזה</span>' : '<span class="status ok">לא</span>'}</span></div>
    <div class="row" style="border-bottom:none;"><span class="k">יבוא אישי</span>
      <span class="v">${report.personal_import
        ? `<span class="status warn">כן${typeof report.personal_import === "string" ? " · " + esc(report.personal_import) : ""}</span>`
        : '<span class="status ok">לא</span>'}</span></div>
  </div>`;

  html += `<div class="card"><div class="row" style="border-bottom:none;">
    <span class="k">סטטוס במרשם</span>
    <span class="v">${report.inactive
      ? '<span class="status bad">הוסר מהמרשם / לא פעיל</span>'
      : '<span class="status ok">פעיל</span>'}</span></div>
    ${report.inactive ? '<div style="margin-top:8px;font-size:12.5px;color:var(--muted);">הסיבה אינה מתפרסמת על ידי המדינה: יכול להיות פירוק לחלקים, יציאה מהארץ, טסט לא בתוקף וכו׳.</div>' : ""}
  </div>`;

  return html;
}

function renderTavNeche(t) {
  if (!t.has) {
    return `<div class="section-title">תו נכה</div><div class="card">
      <div class="row" style="border-bottom:none;"><span class="k">תו נכה</span>
      <span class="v"><span class="status ok">לא נמצא</span></span></div></div>`;
  }
  return `<div class="section-title">תו נכה</div><div class="card">
    <div class="row"><span class="k">תו נכה</span><span class="v"><span class="status warn">הונפק</span></span></div>
    ${t.dates.map(d => `<div class="row"><span class="k">תאריך הנפקה</span><span class="v">${esc(d)}</span></div>`).join("")}
  </div>`;
}

// ---- анализ истории владения ----
// Перекупщик (סוחר) владельцем НЕ считается: машина у него не эксплуатируется,
// это транзит между настоящими владельцами. Поэтому "יד N" нумеруются только
// по реальным владельцам, а проходы через перекупщика показываются отдельно.
const DEALER = "סוחר";

// Даты владения приходят с точностью до месяца (YYYYMM) — это ограничение
// самого data.gov.il, дня там нет.
function parseOwnMonth(v) {
  const s = String(v || "");
  if (/^\d{6}$/.test(s) || /^\d{8}$/.test(s)) {
    return { y: +s.slice(0, 4), m: +s.slice(4, 6) };
  }
  return null;
}

const monthsBetween = (a, b) => (b.y - a.y) * 12 + (b.m - a.m);

function monthsText(n) {
  if (n == null) return "";
  if (n < 1) return "פחות מחודש";
  const y = Math.floor(n / 12), m = n % 12;
  const parts = [];
  if (y === 1) parts.push("שנה");
  else if (y === 2) parts.push("שנתיים");
  else if (y > 2) parts.push(`${y} שנים`);
  if (m === 1) parts.push("חודש");
  else if (m === 2) parts.push("חודשיים");
  else if (m > 2) parts.push(`${m} חודשים`);
  return parts.join(" ו-");
}

const fmtOwnMonth = (d) => (d ? `${String(d.m).padStart(2, "0")}.${d.y}` : "—");

// Дата теста одометра (YYYY-MM-DD) -> {y,m} для сравнения с датами владения.
function parseTestMonth(v) {
  const s = String(v || "");
  const m = s.match(/^(\d{4})-(\d{2})/);
  if (m) return { y: +m[1], m: +m[2] };
  if (/^\d{8}$/.test(s) || /^\d{6}$/.test(s)) return { y: +s.slice(0, 4), m: +s.slice(4, 6) };
  return null;
}

const cmpMonth = (a, b) => (a.y - b.y) || (a.m - b.m);

// Последнее показание одометра НЕ ПОЗЖЕ указанного месяца.
function kmAt(odometer, when) {
  let best = null;
  for (const p of odometer || []) {
    if (p.km == null) continue;
    const d = parseTestMonth(p.test_date);
    if (!d || cmpMonth(d, when) > 0) continue;
    if (!best || cmpMonth(d, best.d) > 0) best = { d, km: Number(p.km) };
  }
  return best;
}

// Сколько километров проехали за период владения. Считается по разнице
// показаний одометра на его границах. Вернёт null, если подходящих показаний
// нет — а так будет почти всегда, пока история не накопится: государство
// публикует только ПОСЛЕДНИЙ пробег, всё остальное копим мы сами, начиная
// с первого прогона сборщика.
function kmDriven(odometer, from, to) {
  const a = kmAt(odometer, from);
  const b = kmAt(odometer, to);
  if (!a || !b) return null;
  if (cmpMonth(a.d, b.d) === 0) return null;   // одно и то же показание — разницы нет
  const diff = b.km - a.km;
  return diff >= 0 ? diff : null;
}

// Строит список периодов владения. Перекупщик (סוחר) своей строки не получает
// и номер руки не увеличивает: он показывается тонкой строкой-перемычкой между
// владельцами, потому что машина у него не эксплуатируется.
function analyzeOwnership(records, odometer) {
  const now = new Date();
  const today = { y: now.getFullYear(), m: now.getMonth() + 1 };

  const items = records
    .map(r => ({ date: parseOwnMonth(r.baalut_dt), type: r.baalut || "—" }))
    .filter(r => r.date)
    .sort((a, b) => (a.date.y - b.date.y) || (a.date.m - b.date.m));

  // Конец периода каждой записи — начало следующей (неважно, владелец это
  // или перекуп): именно так владение и заканчивается фактически.
  items.forEach((it, i) => {
    const next = items[i + 1];
    it.end = next ? next.date : today;
    it.isCurrent = !next;
    it.isDealer = it.type === DEALER;
  });

  const rows = [];
  let hand = 0;
  let pendingDealers = [];

  for (const it of items) {
    if (it.isDealer) { pendingDealers.push(it); continue; }
    if (pendingDealers.length) {
      rows.push({
        kind: "transit",
        count: pendingDealers.length,
        months: monthsBetween(pendingDealers[0].date, it.date),
      });
      pendingDealers = [];
    }
    rows.push({
      kind: "owner",
      hand: ++hand,
      type: it.type,
      from: it.date,
      to: it.end,
      isCurrent: it.isCurrent,
      months: monthsBetween(it.date, it.end),
      km: kmDriven(odometer, it.date, it.end),
    });
  }
  // Машина прямо сейчас стоит у перекупщика — тоже честно показываем.
  if (pendingDealers.length) {
    rows.push({
      kind: "transit",
      count: pendingDealers.length,
      months: monthsBetween(pendingDealers[0].date, today),
      isCurrent: true,
    });
  }

  const owners = rows.filter(r => r.kind === "owner");
  const dealerPasses = items.filter(i => i.isDealer).length;

  // Сигналы быстрой перепродажи. Пороги подобраны так, чтобы не срабатывать
  // на обычной машине (купил -> ездил годами -> продал), но ловить ситуацию
  // "машину гоняют по рукам", которая часто означает скрытую проблему.
  const flags = [];
  if (dealerPasses >= 3) {
    flags.push(`הרכב עבר ${dealerPasses} פעמים דרך סוחר`);
  }
  const quick = owners.filter(o => !o.isCurrent && o.months < 12).length;
  if (quick >= 2) {
    flags.push(`${quick} בעלים החזיקו את הרכב פחות משנה`);
  }
  return { rows, owners, dealerPasses, flags };
}

function renderOwnershipRows(a) {
  return a.rows.map(r => {
    if (r.kind === "transit") {
      const when = r.isCurrent ? " — הרכב אצלו כעת" : "";
      return `<tr><td colspan="5" style="color:var(--muted);font-size:12px;padding:4px;">
        ⟵ עבר דרך סוחר ${r.count > 1 ? `${r.count} פעמים` : ""} (${monthsText(r.months)})${when}
      </td></tr>`;
    }
    return `<tr>
      <td><b>יד ${r.hand}</b></td>
      <td>${esc(r.type)}</td>
      <td>${fmtOwnMonth(r.from)} – ${r.isCurrent ? "היום" : fmtOwnMonth(r.to)}</td>
      <td>${monthsText(r.months)}</td>
      <td>${r.km == null ? "—" : Number(r.km).toLocaleString("he-IL") + ' ק"מ'}</td>
    </tr>`;
  }).join("");
}

function renderOwnership(records, odometer) {
  const empty = `<div class="section-title">היסטוריית בעלות</div><div class="card">
      <div class="empty">אין נתונים — מאגר זה מכסה רק רכבים משנת 2017 ואילך.</div></div>`;
  if (!records || !records.length) return empty;
  const a = analyzeOwnership(records, odometer);
  if (!a.owners.length && !a.rows.length) return empty;

  const warn = a.flags.length
    ? `<div class="alert-block" style="margin-top:12px;">
         <div class="alert-title">⚠️ סימני החלפות ידיים תכופות</div>
         ${a.flags.map(f => `<div class="row" style="border-bottom:none;"><span class="v">${esc(f)}</span></div>`).join("")}
         <div class="src">רכב שעובר הרבה ידיים בזמן קצר — סיבה לבדוק אותו ביסודיות אצל מוסך.</div>
       </div>`
    : "";

  const noKm = a.owners.every(o => o.km == null);

  return `<div class="section-title">היסטוריית בעלות</div><div class="card">
    <div class="row"><span class="k">מספר ידיים</span><span class="v">${a.owners.length}</span></div>
    <div class="row"><span class="k">מעברים דרך סוחר</span><span class="v">${a.dealerPasses}</span></div>
    <div style="overflow-x:auto;margin-top:8px;">
      <table class="odo-table"><thead><tr>
        <th>יד</th><th>סוג בעלות</th><th>תקופה</th><th>משך</th><th>ק"מ שנסע</th>
      </tr></thead><tbody>${renderOwnershipRows(a)}</tbody></table>
    </div>
    ${warn}
    <div class="src">מקור: היסטוריית כלי רכב פרטיים (2). שמות הבעלים אינם מתפרסמים על ידי המדינה.
    סוחר אינו נספר כיד — הרכב אינו בשימוש אצלו, זו רק תחנת מעבר בין בעלים.
    התאריכים ברמת חודש (כך הם מתפרסמים). הכיסוי — רק רכבים משנת 2017 ואילך.
    ${noKm ? `עמודת הק"מ תתמלא ככל שתצטבר היסטוריית מבחני רישוי: המדינה מפרסמת
    רק את הקילומטראז' האחרון, את השאר אנחנו צוברים בעצמנו מרגע ההפעלה.` : ""}</div>
  </div>`;
}

function renderRecalls(r) {
  if (!r.count) {
    return `<div class="card"><div class="row" style="border-bottom:none;">
      <span class="k">ריקול לא מטופל<br><small style="color:var(--muted);">נשלח מכתב מהיבואן, התיקון לא בוצע</small></span>
      <span class="v"><span class="status ok">לא</span></span></div></div>`;
  }
  const items = r.records.map(rec => `<div class="card">${renderRows(rec)}</div>`).join("");
  return `<div class="card"><div class="row" style="border-bottom:none;">
    <span class="k">ריקול לא מטופל</span>
    <span class="v"><span class="status bad">יש: ${r.count}</span></span></div></div>${items}`;
}

function renderAdas(has) {
  return `<div class="card"><div class="row" style="border-bottom:none;">
    <span class="k">מערכת בטיחות (Mobileye וכו׳)<br><small style="color:var(--muted);">מזכה בהנחה באגרה השנתית</small></span>
    <span class="v">${has ? '<span class="status ok">מותקנת</span>' : '<span class="status warn">לא רשומה</span>'}</span>
  </div></div>`;
}

function renderSpecs(specs) {
  if (!specs || !specs.rows || !specs.rows.length) return "";
  return `<div class="section-title">אבזור לפי קטלוג הדגם</div><div class="card">
    ${renderRows(specs.rows)}
    <div class="src">מקור: מרשם הדגמים של משרד התחבורה (תוצרים ודגמים, WLTP).<br>
    <b>אלו נתוני היצרן של הדגם ${esc(specs.model_label)}, לא בדיקה של הרכב הספציפי.</b>
    אם ברכב הזה בוצעו שינויים או הותקנו אבזרים נוספים — הם לא יופיעו כאן.</div>
  </div>`;
}

function renderPrice(price) {
  if (!price || !price.length) return "";
  const rows = price.map(p => `<div class="row"><span class="k">${esc(p.importer)}</span>
    <span class="v">${Number(p.price).toLocaleString("he-IL")} ₪</span></div>`).join("");
  return `<div class="section-title">מחיר לפי מחירון בעת ההשקה</div><div class="card">${rows}
    <div class="src">מקור: מחירוני רכב חדש — מחירון היבואנים כפי שהוגש למשרד התחבורה.
    זהו מחיר הרכב כשהיה חדש, לא השווי בשוק כיום.</div></div>`;
}

function renderExternalLinks(plate) {
  return `<div class="section-title">מידע נוסף (מקור חיצוני)</div><div class="card">
    <div class="row" style="border-bottom:none;">
      <span class="k">טוטל לוס / היסטוריית ביטוח<br><small style="color:var(--muted);">אובדן גמור/להלכה — בתשלום (כ-10 ₪), ניתן להזמין רק על ידי הבעלים עצמו</small></span>
      <a href="https://infocar.co.il/" target="_blank" style="color:var(--accent); font-weight:600;">פתיחה ↗</a>
    </div>
    <div style="margin-top:12px; font-size:12px; color:var(--muted);">הזינו את המספר ${esc(plate)} ידנית — מקור זה אינו תומך בפנייה ישירה דרך ה-API שלנו.</div>
  </div>`;
}

// ---- новые блоки из накопленной локальной базы (Часть 2 ТЗ) ----
// График-спарклайн убран вместе с переходом на плоскую таблицу
// "последний тест / предыдущий тест": рисовать линию по двум точкам незачем,
// разница между ними показана числом прямо в таблице.

const CHANGE_KIND_LABELS = {
  new_car: "הרכב נוסף למאגר",
  changed: "שינוי בנתונים",
  anomaly: "ירידה בקילומטראז' (חשד לסיבוב מד)",
};

const kmText = (v) => (v == null ? "—" : Number(v).toLocaleString("he-IL") + ' ק"מ');

// Полная история всех тестов + разница между соседними.
// Приходит уже отсортированной от новых к старым (см. server/history_api.py),
// поэтому первая строка — последний тест.
function renderOdometerTable(odometer) {
  if (!odometer || !odometer.length) {
    return `<div class="card"><div class="empty">היסטוריית הקילומטראז' של מספר זה טרם נצברה.
      היא תופיע לאחר ריצה של המאסף שתאסוף גם את מרשם הרכבים (משם מגיע תאריך המבחן).</div></div>`;
  }
  const rows = odometer.map((p, i) => {
    const next = odometer[i + 1];   // предыдущий по времени тест
    let delta = "—";
    if (next && p.km != null && next.km != null) {
      const d = Number(p.km) - Number(next.km);
      delta = d < 0
        ? `<span style="color:var(--danger);font-weight:700;">${kmText(Math.abs(d))} ירידה!</span>`
        : `+${Number(d).toLocaleString("he-IL")}`;
    }
    return `<tr>
      <td>${esc(p.test_date || "—")}</td>
      <td>${kmText(p.km)}</td>
      <td>${delta}</td>
    </tr>`;
  }).join("");
  return `<div class="card">
    <div style="font-size:13px;color:var(--muted);margin-bottom:8px;">
      כל מבחני הרישוי שנצברו (${odometer.length})</div>
    <div style="overflow-x:auto;">
      <table class="odo-table"><thead><tr>
        <th>תאריך המבחן</th><th>קילומטראז'</th><th>שינוי מהמבחן הקודם</th>
      </tr></thead><tbody>${rows}</tbody></table>
    </div>
    <div class="src">התאריכים הם תאריכי מבחן הרישוי בפועל (לפי משרד התחבורה), לא מועד האיסוף שלנו.
    השורה העליונה היא המבחן האחרון. "ירידה" בעמודה הימנית = הקילומטראז' קטן בין מבחנים,
    מה שאינו קורה בשימוש רגיל.</div>
  </div>`;
}

// Подробный журнал "когда, что, было -> стало" — то, ради чего вообще
// копится собственная база: государство таких изменений не публикует.
function renderChangeLog(changes) {
  if (!changes || !changes.length) return "";
  const rows = changes.map(c => {
    const kind = CHANGE_KIND_LABELS[c.change_kind] || c.change_kind;
    const what = c.field_label || (c.change_kind === "new_car" ? "—" : (c.field || "—"));
    const from = c.old_value == null || c.old_value === "" ? "—" : c.old_value;
    const to = c.new_value == null || c.new_value === "" ? "—" : c.new_value;
    const cls = c.change_kind === "anomaly" ? ' style="color:var(--danger);font-weight:700;"' : "";
    return `<tr>
      <td>${esc((c.detected_at || "").slice(0, 10))}</td>
      <td${cls}>${esc(kind)}</td>
      <td>${esc(what)}</td>
      <td>${esc(from)}</td>
      <td>${esc(to)}</td>
    </tr>`;
  }).join("");
  return `<div class="card">
    <div style="font-size:13px;color:var(--muted);margin-bottom:4px;">יומן שינויים מפורט</div>
    <div style="overflow-x:auto;">
      <table class="odo-table"><thead><tr>
        <th>מתי</th><th>סוג</th><th>שדה</th><th>לפני</th><th>אחרי</th>
      </tr></thead><tbody>${rows}</tbody></table>
    </div>
    <div class="src">כל שינוי שזוהה בין שני צילומי מצב שבועיים של משרד התחבורה, שדה אחר שדה.
    "מתי" הוא מועד הזיהוי על ידי המאסף.</div>
  </div>`;
}

function renderLocalHistory(local) {
  let html = `<div class="section-title">היסטוריה שנצברה (מאגר עצמאי)</div>`;

  if (!local.available) {
    html += `<div class="card"><div class="empty">${esc(local.note)}</div></div>`;
    return html;
  }

  if (local.engine_changes && local.engine_changes.length) {
    html += `<div class="alert-block">
      <div class="alert-title">⚠️ זוהה שינוי במספר המנוע</div>
      ${local.engine_changes.map(c => `<div class="row">
        <span class="k">${esc(c.detected_at ? c.detected_at.slice(0,10) : "")}</span>
        <span class="v">${esc(c.old_engine)} ← ${esc(c.new_engine)}${c.km_at_change ? ` (ב-${Number(c.km_at_change).toLocaleString("he-IL")} ק"מ)` : ""}</span>
      </div>`).join("")}
      <div class="src">החלפת מנוע בין שני צילומי מצב שבועיים של משרד התחבורה. לא מתפרסם באף שירות אחר.</div>
    </div>`;
  }

  if (local.anomalies && local.anomalies.length) {
    html += `<div class="alert-block">
      <div class="alert-title">⚠️ הקילומטראז' ירד בין הצילומים — חשד לסיבוב מד ק"מ אחורה</div>
      ${local.anomalies.map(a => `<div class="row">
        <span class="k">${esc(a.detected_at ? a.detected_at.slice(0,10) : "")}</span>
        <span class="v">${Number(a.prev_km).toLocaleString("he-IL")} ק"מ ← ${Number(a.new_km).toLocaleString("he-IL")} ק"מ</span>
      </div>`).join("")}
      <div class="src">קריאת מד הקילומטראז' בצילום החדש נמוכה מזו שבצילום הקודם — דבר שאינו קורה בשימוש רגיל.</div>
    </div>`;
  }

  html += renderOdometerTable(local.odometer);

  html += renderChangeLog(local.changes);
  return html;
}

function renderLimitations(list) {
  if (!list || !list.length) return "";
  return `<div class="limitations"><b>מגבלות הנתונים:</b><br>${list.map(esc).join("<br>")}</div>`;
}

function renderReport(report) {
  if (report.errors && report.errors.length && report.not_found && !report.main) {
    // критичная ошибка сети/API — main так и не получили
  }
  let html = "";
  html += renderMain(report);
  if (report.mileage_analysis) html += renderMileage(report.mileage_analysis);
  html += renderLocalHistory(report.local_history || { available: false, note: "אין נתונים" });
  html += renderStatusBlock(report);
  html += renderTavNeche(report.tav_neche);
  // Пробег по владельцам считается из накопленных показаний одометра,
  // поэтому передаём их сюда же.
  html += renderOwnership(report.ownership.records, (report.local_history || {}).odometer);
  html += `<div class="section-title">בטיחות וריקולים</div>`;
  html += renderRecalls(report.recalls);
  html += renderAdas(report.adas);
  html += renderSpecs(report.specs);
  html += renderPrice(report.price);
  html += renderExternalLinks(report.plate);
  html += renderLimitations(report.limitations);

  if (report.errors && report.errors.length) {
    html += `<div class="card"><div class="error" style="padding:10px 0;">⚠️ ${report.errors.map(esc).join("<br>")}</div></div>`;
  }
  return html;
}

async function search(plateOverride) {
  const btn = document.getElementById("searchBtn");
  const input = document.getElementById("plateInput");
  const resultEl = document.getElementById("result");
  const original = btn.textContent;

  const plate = (plateOverride || input.value).trim().replace(/\D/g, "");
  if (plateOverride) input.value = plateOverride;

  if (!plate) {
    resultEl.innerHTML = `<div class="error">יש להזין מספר רכב (ספרות בלבד).</div>`;
    return;
  }

  btn.textContent = "...";
  btn.disabled = true;
  resultEl.innerHTML = `<div class="loading"><div class="spinner"></div>מחפש נתונים...</div>`;

  try {
    const res = await fetch(`/api/car/${plate}`);
    if (res.status === 401) {
      resultEl.innerHTML = `<div class="error">הפעילה פגה. רעננו את הדף עם קישור שמכיל ?token=...</div>`;
      return;
    }
    const data = await res.json();
    if (data.error) {
      resultEl.innerHTML = `<div class="error">${esc(data.error)}</div>`;
      return;
    }
    resultEl.innerHTML = renderReport(data);
  } catch (e) {
    resultEl.innerHTML = `<div class="error">שגיאת בקשה: ${esc(e.message)}</div>`;
  } finally {
    btn.textContent = original;
    btn.disabled = false;
  }
}

document.getElementById("searchBtn").addEventListener("click", () => search());
document.getElementById("plateInput").addEventListener("keydown", e => { if (e.key === "Enter") search(); });
document.querySelectorAll(".test-plate-btn").forEach(b => {
  b.addEventListener("click", () => search(b.dataset.plate));
});

fetch("/api/status").then(r => r.json()).then(s => {
  const el = document.getElementById("statusLine");
  if (!el) return;
  if (s.available) {
    el.textContent = `מסד נתונים מקומי: ${s.snapshots_count} צילומים, ${s.plates_covered} רכבים, איסוף אחרון ${s.last_snapshot_at ? s.last_snapshot_at.slice(0,16).replace('T',' ') : '—'}`;
  } else {
    el.textContent = "המסד המקומי טרם נוצר — הריצו את המאסף.";
  }
}).catch(() => {});
