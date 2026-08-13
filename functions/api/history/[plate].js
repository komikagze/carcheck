// export/dist_template/functions/api/history/[plate].js
//
// Cloudflare Pages Function. Отдаёт накопленную историю ОДНОЙ конкретной машины
// по номеру — и только так: единственный способ прочитать данные из KV на этом
// сайте. Никакого эндпоинта "дай список всех номеров" или "дай весь дамп" не
// существует в принципе, поэтому массово скачать всю базу через сайт нельзя,
// даже без всякого логина на сам поиск.
//
// Требует привязку KV namespace к проекту Cloudflare Pages с именем CARCHECK_KV
// (Settings -> Functions -> KV namespace bindings, см. README).
//
// Анти-скрапинг: простой рейт-лимит по IP на той же KV (ключ вида rl:<ip>:<минута>,
// TTL ~70 секунд). Это НЕ железная защита — при желании её можно обойти (менять IP,
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

export async function onRequestGet(context) {
  const { params, request, env } = context;

  if (!env.CARCHECK_KV) {
    return jsonResponse({ error: "KV namespace אינו מקושר לפרויקט (CARCHECK_KV). ראו README." }, 500);
  }

  // --- валидация номера: только цифры, разумная длина ---
  const rawPlate = String(params.plate || "");
  const digitsOnly = rawPlate.replace(/\D/g, "");
  if (!digitsOnly || digitsOnly.length > 10) {
    return jsonResponse({ error: "מספר רכב לא תקין." }, 400);
  }
  const plate = digitsOnly.replace(/^0+/, "") || "0";

  // --- рейт-лимит по IP, чтобы затруднить перебор диапазона номеров ---
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const minuteBucket = Math.floor(Date.now() / 60000);
  const rlKey = `rl:${ip}:${minuteBucket}`;

  const currentRaw = await env.CARCHECK_KV.get(rlKey);
  const current = currentRaw ? parseInt(currentRaw, 10) : 0;

  if (current >= RATE_LIMIT_PER_MINUTE) {
    return jsonResponse({ error: "יותר מדי בקשות מכתובת זו. נסו שוב בעוד דקה." }, 429);
  }

  // put не атомарен относительно get (KV eventually consistent) — при параллельных
  // запросах возможен небольшой перехлёст лимита, это осознанный компромисс ради
  // простоты (без Durable Objects/платных фич).
  context.waitUntil(env.CARCHECK_KV.put(rlKey, String(current + 1), { expirationTtl: 70 }));

  // --- сама история ---
  const value = await env.CARCHECK_KV.get(`car:${plate}`);
  if (!value) {
    return jsonResponse({
      available: false,
      plate,
      note: "היסטוריית הקילומטראז' של מספר זה טרם נצברה (או שהמספר אינו מכוסה, "
          + "או שעדיין לא היה צילום שבועי שני).",
    }, 404);
  }

  return new Response(value, {
    status: 200,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
    },
  });
}
