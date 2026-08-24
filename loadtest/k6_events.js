import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 100,
  duration: "30s",
  thresholds: {
    http_req_failed: ["rate<0.05"],
    http_req_duration: ["p(95)<50"],
  },
};

const BASE = __ENV.BASE_URL || "http://localhost:8000";
const EMAIL = __ENV.LOADTEST_EMAIL || "admin@local.dev";
const PASSWORD = __ENV.LOADTEST_PASSWORD || "adminadmin";

export function setup() {
  const res = http.post(`${BASE}/api/v1/auth/login`, {
    username: EMAIL,
    password: PASSWORD,
  });
  return { token: res.json("access_token") };
}

export default function (data) {
  const headers = {
    Authorization: `Bearer ${data.token}`,
    "Content-Type": "application/json",
  };
  const res = http.post(
    `${BASE}/api/v1/events`,
    JSON.stringify({ event_type: "load.ping", payload: { src: "k6" } }),
    { 
      headers,
      responseCallback: http.expectedStatuses(200, 429),
    }
  );
  check(res, {
    "accepted or rate-limited": (r) => r.status === 200 || r.status === 429,
  });
  sleep(0.01);
}
