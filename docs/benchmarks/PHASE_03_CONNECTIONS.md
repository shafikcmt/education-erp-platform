# Phase 3 M3 — Database Connection Measurement (decision D4)

- **Status:** measured once, on a development machine. **Indicative only.** No threshold was applied and nothing was changed because of these numbers (ADR-048 M3-Q7).
- **Date:** 2026-11-13. **Commit:** `246b6f0` (branch `feat/phase-03-m3`).
- **Question (plan §8.6, D4):** what does `CONN_MAX_AGE = 0` (a new PostgreSQL connection per request) cost under ASGI, compared with persistent connections?
- **Raw results:** `PHASE_03_CONNECTIONS.conn_max_age_0.json` and `PHASE_03_CONNECTIONS.conn_max_age_60_control.json` in this directory.

## 1. Result in short

1. **`CONN_MAX_AGE = 0` served every request** (18,000 measured requests, 0 errors) and never held more than 30 PostgreSQL connections.
2. **The `CONN_MAX_AGE = 60` control failed under concurrency:** it held up to 97 connections against PostgreSQL's limit of 100 and returned HTTP 500 for 13% of requests at concurrency 8 and 60% at concurrency 32. Even at concurrency 1 it accumulated about 50 connections.
3. **Cost of `0` where both worked (concurrency 1):** p50 +3.2%, p95 +2.1%. That is about 1 ms per request on this machine.
4. At concurrency 8 and 32 the latency columns are **not a valid comparison**, because the control was answering a large share of requests with fast errors.

**Reading:** on this stack, persistent connections are not a free speed-up; without a connection pool sized to the worker threads they exhaust PostgreSQL. This supports keeping `CONN_MAX_AGE = 0` (D4). The cause of the 500s was not confirmed from server logs; it is inferred from the connection count reaching the server limit.

## 2. Numbers

Medians of 3 repetitions; each repetition is 2,000 measured requests after a 200-request warm-up.

### 2.1 Latency (ms) and throughput

| Concurrency | p50 `0` | p50 `60` | Δ p50 | p95 `0` | p95 `60` | Δ p95 | p99 `0` | p99 `60` | req/s `0` | req/s `60` |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 36.04 | 34.91 | +3.2% | 45.92 | 44.96 | +2.1% | 53.46 | 51.62 | 27.2 | 28.0 |
| 8 | 122.01 | 103.89 | (invalid) | 192.29 | 179.68 | (invalid) | 234.86 | 222.48 | 64.1 | 73.4 |
| 32 | 514.33 | 324.66 | (invalid) | 733.71 | 615.2 | (invalid) | 810.82 | 721.54 | 60.8 | 88.3 |

"(invalid)": the control's figures include failed requests (see 2.2), so the difference says nothing about connection cost.

### 2.2 Connections and errors

| Concurrency | PG sessions opened per 2,000 requests, `0` | same, `60` | Peak `erp_app` connections, `0` | same, `60` | Non-200 responses of 6,000, `0` | same, `60` |
|---|---|---|---|---|---|---|
| 1 | 2115 | 2112 | 1 | 51 | 0 | 0 |
| 8 | 2046 | 1790 | 8 | 97 | 0 | 760 (all HTTP 500) |
| 32 | 2047 | 845 | 30 | 97 | 0 | 3579 (all HTTP 500) |

- "Sessions opened" is the growth of `pg_stat_database.sessions`. It includes the sampler's own `psql` sessions (two per second) and background services, so it is an upper bound.
- The control still opened about one session per request at concurrency 1. The measurement does not explain why; it was not investigated.

### 2.3 Spread between repetitions (p95 ms; sessions opened)

| `CONN_MAX_AGE` | Concurrency | p95 per repetition | Sessions per repetition |
|---|---|---|---|
| 0 | 1 | 44.56 / 45.92 / 48.63 | 2112 / 2115 / 2116 |
| 0 | 8 | 173.99 / 192.29 / 192.5 | 2046 / 2046 / 2046 |
| 0 | 32 | 913.43 / 678.33 / 733.71 | 2047 / 2045 / 2047 |
| 60 | 1 | 44.96 / 45.02 / 43.11 | 2112 / 2113 / 2108 |
| 60 | 8 | 225.32 / 179.68 / 177.51 | 1815 / 1790 / 1759 |
| 60 | 32 | 615.2 / 679.3 / 614.18 | 1036 / 632 / 845 |

## 3. Method

- **Script:** `infra/scripts/measure_db_connections.py` (standard library; threads with keep-alive HTTP connections).
- **Request:** `GET /api/v1/me/` on the platform host, signed in as an ordinary user without roles or MFA. It reads the session, the session record and the user's permissions from PostgreSQL.
- **Procedure:** per concurrency level (1, 8, 32): 200 warm-up requests, then 3 repetitions of 2,000 requests; p50, p95 and p99 per repetition and the median of the repetitions.
- **Configurations:** `DATABASE_CONN_MAX_AGE=0` (the only value production accepts) and `60` as a non-production control. The API service was restarted between them; nothing else changed.
- **Server:** Gunicorn with 2 Uvicorn workers (ASGI), `DJANGO_DEBUG=false`, development settings, source bind-mounted into the existing development image.

## 4. Deviations from the plan's method (plan §8.4, §8.6)

| Planned | Done | Why |
|---|---|---|
| Through Nginx and Uvicorn | Directly against the API container (port published for the measurement only), Gunicorn + Uvicorn workers | Nginx limits each client address to 30 requests/second, so a single-client load test through it mostly measures 429 responses |
| Production server settings | 2 workers instead of the production image's 3; development settings with debug off | The production image could not be rebuilt in this environment; the development compose file starts `runserver`, so the command was overridden for the measurement only (not committed) |
| Tenant-host path | **Not measured** | Tenant hosts stay disabled outside the test suite. The isolation-overhead benchmark against the D9 targets is an M10 deliverable |
| Connection-setup cost in isolation | Not measured separately; only its effect on request latency | — |

## 5. Environment

| Item | Value |
|---|---|
| CPU | Intel Xeon @ 2.10 GHz, 4 cores (virtual machine, shared) |
| RAM | 15 GB |
| OS / kernel | Linux 6.18.44 |
| Docker / Compose | 29.9.2 / v5.6.1 |
| PostgreSQL | 17.11; `shared_buffers` 128 MB, `work_mem` 4 MB, `max_connections` 100 |
| API server | Gunicorn, 2 `uvicorn_worker.UvicornWorker` workers |
| Client | Same machine as the stack |

Client and server shared four cores, so absolute latencies (and the rise at concurrency 32) reflect CPU contention on this machine, not production capacity.

## 6. What this does and does not establish

- **Does:** `CONN_MAX_AGE = 0` is workable on this stack, with a small measured cost at low concurrency, and it bounds connection use to the number of in-flight requests.
- **Does:** a persistent-connection setting without a pool is unsafe here under concurrency.
- **Does not:** give production capacity numbers, a comparison at concurrency 8 or 32, the cost of the tenant path, or behaviour behind PgBouncer (Phase 19).
- **Decision needed from the owner:** none now. If connection cost becomes material later, the options (a pool, PgBouncer) need owner approval, leak tests and, for a pool library, dependency approval (D4).

### Change notes
- 2026-11-13 — First measurement recorded.
