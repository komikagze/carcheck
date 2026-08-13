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

function renderOwnership(o) {
  if (!o.records.length) {
    return `<div class="section-title">היסטוריית בעלות</div><div class="card">
      <div class="empty">אין נתונים — מאגר זה מכסה רק רכבים משנת 2017 ואילך.</div></div>`;
  }
  const rows = o.records.map(r => `<div class="row">
    <span class="k">יד ${r.index}</span>
    <span class="v">${esc(r.type || "—")}${r.since ? ` · מ-${esc(r.since)}` : ""}</span></div>`).join("");
  return `<div class="section-title">היסטוריית בעלות</div><div class="card">
    <div class="row"><span class="k">סה"כ בעלים</span><span class="v">${o.records.length}</span></div>
    ${rows}
    <div class="src">מקור: היסטוריית כלי רכב פרטיים (2). שמות הבעלים אינם מתפרסמים על ידי המדינה.
    הכיסוי — רק רכבים משנת 2017 ואילך.</div>
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

function sparkline(points) {
  if (points.length < 2) return "";
  const w = 520, h = 110, pad = 8;
  const xs = points.map((_, i) => i);
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

  if (local.odometer_series && local.odometer_series.length) {
    const rows = local.odometer_series.map(p => `<tr>
      <td>${esc((p.detected_at || "").slice(0,10))}</td>
      <td>${p.km != null ? Number(p.km).toLocaleString("he-IL") + ' ק"מ' : "—"}</td>
    </tr>`).join("");
    html += `<div class="card">
      <div style="font-size:13px;color:var(--muted);margin-bottom:4px;">היסטוריית קריאות מד הקילומטראז' (לפי צילומי המאסף)</div>
      ${sparkline(local.odometer_series.filter(p => p.km != null))}
      <table class="odo-table"><thead><tr><th>תאריך צילום</th><th>קילומטראז'</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <div class="src">נצבר אחת לשבוע על ידי המאסף המקומי (מאגר עצמאי, לא מתפרסם על ידי משרד התחבורה).
      אם מוצגת כאן רק שורה אחת — נאסף עדיין רק צילום אחד, ההיסטוריה תופיע לאחר ריצה שנייה של המאסף.</div>
    </div>`;
  } else {
    html += `<div class="card"><div class="empty">היסטוריית הקילומטראז' של מספר זה טרם נצברה.
      היא תופיע לאחר שהמאסף יאסוף לפחות שני צילומים במרווח (אחת לשבוע).</div></div>`;
  }

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
  html += renderOwnership(report.ownership);
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
