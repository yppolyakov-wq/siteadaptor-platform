// Hardening H6: нагрузочный тест anti-oversell (k6) против реального сервера.
//
// Толпа VU ломится бронировать одну акцию; после прогона остаток и сумма броней
// сверяются вручную (см. scripts/load/README.md). Скрипт ходит как браузер:
// GET страницы акции (csrftoken-cookie + csrfmiddlewaretoken) → POST формы.
//
//   k6 run -e BASE_URL=http://127.0.0.1:8000 -e PROMO_ID=<uuid> \
//          -e HOST_HEADER=shop.siteadaptor.de scripts/load/anti_oversell.js

import http from "k6/http";
import { check } from "k6";

const BASE = __ENV.BASE_URL;
const PROMO = __ENV.PROMO_ID;
const HOST = __ENV.HOST_HEADER || "";

export const options = {
  scenarios: {
    rush: {
      executor: "shared-iterations",
      vus: Number(__ENV.VUS || 50),
      iterations: Number(__ENV.ITERATIONS || 500),
      maxDuration: "2m",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<1500"],
    checks: ["rate>0.99"],
  },
};

function params(extra = {}) {
  const headers = { ...extra };
  if (HOST) headers["Host"] = HOST;
  // Рандомный клиентский IP, чтобы per-IP rate-limit не схлопнул прогон с одной
  // машины. Работает только при прямом обращении к gunicorn (см. README) —
  // в проде Caddy перезаписывает X-Forwarded-For.
  headers["X-Forwarded-For"] = `10.${__VU % 250}.${(__ITER >> 8) % 250}.${__ITER % 250}`;
  return { headers };
}

export default function () {
  const page = http.get(`${BASE}/p/${PROMO}/`, params());
  const m = /name="csrfmiddlewaretoken" value="([^"]+)"/.exec(page.body || "");
  if (!check(m, { "got csrf token": (x) => x !== null })) return;

  const res = http.post(
    `${BASE}/p/${PROMO}/reserve/`,
    {
      csrfmiddlewaretoken: m[1],
      name: `LoadTest ${__VU}-${__ITER}`,
      email: `lt-${__VU}-${__ITER}@example.com`,
      quantity: "1",
      form_token: `${__VU}-${__ITER}-${Date.now()}`,
    },
    params({ Referer: `${BASE}/p/${PROMO}/` })
  );
  // 302 → бронь создана; 200 → ре-рендер (ausverkauft / rate-limit) — оба легитимны,
  // важен инвариант остатка в БД, а не доля успешных броней.
  check(res, { "reserve answered": (r) => r.status === 302 || r.status === 200 });
}
