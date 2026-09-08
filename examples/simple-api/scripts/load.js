// load.js — constant arrival rate against the mock API.
//
// Open model on purpose: k6 fires TARGET_RATE requests per second whether or
// not the previous ones came back. A closed model ("N virtual users looping")
// offers less load as the server slows, so the saturation this execution is
// looking for would never appear — the client would throttle itself and the
// curve would flatten into a plateau that says nothing.
//
// The end-of-test summary is what M1/M2/M3 are read from; Prometheus supplies
// the server-side view (M4/M5).

import http from 'k6/http';
import { check } from 'k6';

const RATE = Number(__ENV.TARGET_RATE || 10);
const DURATION = __ENV.DURATION || '45s';
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8081';

// Each request costs the server ~40 ms of CPU and the client waits for it, so
// one VU sustains roughly 20 req/s at best. Allocate with headroom: too few
// and k6 reports dropped iterations instead of the server's real latency.
const PER_VU = 10;

export const options = {
  scenarios: {
    constant: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: Math.max(10, Math.ceil(RATE / PER_VU) * 4),
      maxVUs: Math.max(50, Math.ceil(RATE / PER_VU) * 20),
    },
  },
  // Thresholds are not the execution's guards — those live in guards.txt and
  // are checked against Prometheus. This one only marks the run as failed so
  // the runner can flag a point whose offered load was not actually served.
  thresholds: {
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  const res = http.get(`${BASE_URL}/`, { timeout: '10s' });
  check(res, { 'status 200': (r) => r.status === 200 });
}
