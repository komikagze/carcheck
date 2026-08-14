// export/dist_template/worker/index.js
//
// Cloudflare Worker. Отдаёт накопленную историю ОДНОЙ конкретной машины
// по номеру — и только так: единственный способ прочитать данные из хранилища
// на этом сайте. Никакого эндпоинта "дай список всех номеров" или "дай весь
// дамп" не существует в принципе, поэтому массово скачать всю базу через сайт
// нельзя, даже без всякого логина на сам поиск.
//
// ПОЧЕМУ WORKER, А НЕ PAGES FUNCTION (важно, не переигрывать).
// Раньше это был файл functions/api/history/[plate].js — Pages Function с
// маршрутизацией по имени файла. В августе 2026 выяснилось, что Cloudflare
// убрал создание новых проектов Pages из панели: в диалоге "Create" остались
// только Workers. Проверено вживую — вкладки Pages нет, а официальный гайд
// теперь называется "Migrate from Pages to Workers".
//
// Cloudflare предлагает компилировать папку functions/ в воркер командой
// `wrangler pages functions build`. Мы этого НЕ делаем: маршрут ровно один,
// точка входа была ровно одна, и обвязка занимает полтора десятка строк.
// Отказ от шага сборки убирает из конвейера npm-зависимость и команду, которую
// сам Cloudflare называет переходной. Логика запросов к Turso, рейт-лимит и
// формат ответа ниже — не менялись при переезде вообще.
//
// СТАТИКА отдаётся не отсюда: она лежит в public/ и раздаётся механизмом
// static assets (см. wrangler.jsonc, поле assets.directory). Ассеты имеют
// приоритет, и до воркера доходит только то, что не совпало ни с одним файлом,
// то есть фактически /api/*. Поэтому адреса страниц не изменились.
//
// ХРАНИЛИЩЕ: Turso (облачный SQLite), а не Cloudflare KV.
// Почему поменяли: на бесплатном тарифе KV разрешает всего 1000 операций записи
// в СУТКИ, а нам нужно залить ~2.4 млн машин — заливка падала с 429. У Turso
// бесплатно 5 ГБ, 10 млн записей строк в месяц и 500 млн чтений. Подробности
// и разбор альтернатив — в README и в export/turso_upload.py.
//
// Требует две переменные окружения воркера:
//   TURSO_DATABASE_URL  — libsql://<база>-<организация>.turso.io
//   TURSO_AUTH_TOKEN    — токен доступа к базе
// Заводить в панели: воркер -> Settings -> Variables and Secrets, тип Secret.
// (У Pages это называлось Environment variables — отсюда путаница в старых
// заметках. Pages-проекта у нас нет и не было.)
//
// Анти-скрапинг: рейт-лимит по IP на той же базе (таблица rate_limit, корзина
// на минуту). Это НЕ железная защита — при желании её можно обойти (менять IP,
// распределять запросы). Она подобрана так, чтобы не мешать обычному человеку,
// проверяющему 1-2 машины, но делала перебор всего диапазона номеров (десятки
// миллионов вариантов) заметно медленнее и дороже, чем оно того стоит. Честно
// написано и в README: это "затрудняет и делает нерентабельным", а не гарантия.

const RATE_LIMIT_PER_MINUTE = 25;

function jsonResponse(body, status) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      // сайт и так публичный, никаких ограничений по origin для самого запроса не нужно
      "access-control-allow-origin": "*",
    },
  });
}

function apiUrl(raw) {
  let url = String(raw || "").trim().replace(/\/+$/, "");
  if (url.startsWith("libsql://")) url = "https://" + url.slice("libsql://".length);
  else if (!url.startsWith("http")) url = "https://" + url;
  return url + "/v2/pipeline";
}

// Значение -> типизированный аргумент протокола Turso.
// Целые числа передаются строкой — так требует протокол (точность i64).
function arg(value) {
  if (value === null || value === undefined) return { type: "null", value: null };
  if (typeof value === "number" && Number.isInteger(value)) {
    return { type: "integer", value: String(value) };
  }
  if (typeof value === "number") return { type: "float", value };
  return { type: "text", value: String(value) };
}

async function turso(env, statements) {
  const requests = statements.map((st) => {
    if (typeof st === "string") return { type: "execute", stmt: { sql: st } };
    return { type: "execute", stmt: { sql: st[0], args: (st[1] || []).map(arg) } };
  });
  requests.push({ type: "close" });

  const res = await fetch(apiUrl(env.TURSO_DATABASE_URL), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.TURSO_AUTH_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ requests }),
  });
  if (!res.ok) throw new Error(`Turso HTTP ${res.status}`);
  const data = await res.json();
  for (const r of data.results || []) {
    if (r.type === "error") throw new Error(`Turso: ${JSON.stringify(r.error)}`);
  }
  return data.results || [];
}

// Ответ Turso: строки — массивы объектов {type, value}. Превращаем в обычные
// объекты по именам колонок, чтобы дальше работать с ними как с записями.
function rowsOf(result) {
  const r = result?.response?.result;
  if (!r) return [];
  const cols = (r.cols || []).map((c) => c.name);
  return (r.rows || []).map((row) => {
    const obj = {};
    row.forEach((cell, i) => {
      let v = cell?.value ?? null;
      if (cell?.type === "integer" && v !== null) v = Number(v);
      obj[cols[i]] = v;
    });
    return obj;
  });
}

async function handleHistory(request, env, rawPlate) {
  if (!env.TURSO_DATABASE_URL || !env.TURSO_AUTH_TOKEN) {
    return jsonResponse(
      { error: "אחסון ההיסטוריה אינו מוגדר (TURSO_DATABASE_URL / TURSO_AUTH_TOKEN). ראו README." },
      500,
    );
  }

  // --- валидация номера: только цифры, разумная длина ---
  const digitsOnly = String(rawPlate || "").replace(/\D/g, "");
  if (!digitsOnly || digitsOnly.length > 10) {
    return jsonResponse({ error: "מספר רכב לא תקין." }, 400);
  }
  const plate = digitsOnly.replace(/^0+/, "") || "0";

  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const minute = Math.floor(Date.now() / 60000);

  try {
    // Рейт-лимит и выборка данных — одним HTTP-вызовом, чтобы не платить
    // за вторую поездку до базы на каждый запрос.
    const results = await turso(env, [
      // Инкремент корзины и сразу получение счётчика (RETURNING поддерживается).
      [
        "INSERT INTO rate_limit (bucket, minute, hits) VALUES (?, ?, 1) " +
          "ON CONFLICT(bucket) DO UPDATE SET hits = hits + 1 RETURNING hits",
        [`${ip}:${minute}`, minute],
      ],
      // Подчищаем корзины старше двух минут, чтобы таблица не росла бесконечно.
      ["DELETE FROM rate_limit WHERE minute < ?", [minute - 2]],
      // Все показания одометра по этой машине, от новых к старым:
      // первые две строки — это и есть "последний" и "предыдущий" тест.
      ["SELECT test_date, km FROM odometer WHERE plate = ? ORDER BY test_date DESC", [plate]],
      // Полный журнал изменений по этой машине.
      [
        "SELECT detected_at, change_kind, field, field_label, old_value, new_value " +
          "FROM changes WHERE plate = ? ORDER BY detected_at ASC, local_id ASC",
        [plate],
      ],
    ]);

    const hits = rowsOf(results[0])[0]?.hits ?? 0;
    if (hits > RATE_LIMIT_PER_MINUTE) {
      return jsonResponse({ error: "יותר מדי בקשות מכתובת זו. נסו שוב בעוד דקה." }, 429);
    }

    const odometer = rowsOf(results[2]);
    const changes = rowsOf(results[3]);

    if (odometer.length === 0 && changes.length === 0) {
      return jsonResponse(
        {
          available: false,
          plate,
          note:
            "היסטוריית הקילומטראז' של מספר זה טרם נצברה (או שהמספר אינו מכוסה, " +
            "או שעדיין לא היה צילום שבועי שני).",
        },
        404,
      );
    }

    // Смена двигателя и аномалии не хранятся отдельно — выводим их из журнала,
    // чтобы одни и те же факты не лежали в базе в двух местах.
    const engineChanges = changes
      .filter((c) => c.field === "engine_no" && c.change_kind === "changed")
      .map((c) => ({ date: c.detected_at, old_engine: c.old_value, new_engine: c.new_value }));

    const anomalies = changes
      .filter((c) => c.change_kind === "anomaly")
      .map((c) => ({ date: c.detected_at, prev_km: Number(c.old_value), new_km: Number(c.new_value) }));

    return jsonResponse(
      {
        available: true,
        plate,
        odometer,
        changes,
        engine_changes: engineChanges,
        anomalies,
      },
      200,
    );
  } catch (e) {
    return jsonResponse({ error: `שגיאה בקריאת ההיסטוריה: ${e.message}` }, 502);
  }
}

// Единственная точка входа воркера. Сюда попадает только то, что не совпало
// со статическим файлом из public/ — см. шапку файла. Маршрут ровно один:
// GET /api/history/<номер>. Всё остальное — 404 обычным JSON-ответом, чтобы
// клиент всегда получал предсказуемый формат.
export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    const match = pathname.match(/^\/api\/history\/([^/]+)\/?$/);

    if (!match) {
      return jsonResponse({ error: "לא נמצא." }, 404);
    }
    if (request.method !== "GET") {
      return jsonResponse({ error: "שיטה לא נתמכת." }, 405);
    }

    return handleHistory(request, env, decodeURIComponent(match[1]));
  },
};
