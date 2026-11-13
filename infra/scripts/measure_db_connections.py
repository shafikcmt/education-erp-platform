#!/usr/bin/env python3
"""Database-connection measurement for decision D4 (Phase 3 plan §8.4 method, §8.6).

Measures an authenticated, database-backed read (``GET /api/v1/me/``) through the real stack
(Nginx -> Uvicorn workers -> Django -> PostgreSQL) and reports request latency plus how many
PostgreSQL sessions the run opened. Run it once per configuration (``DATABASE_CONN_MAX_AGE=0``,
the only production setting, and a NON-PRODUCTION control such as ``60``) and compare.

Standard library only. It never changes configuration: restart the ``api`` service with the
variable you want to measure, then run this script. Results are printed as JSON; record them,
with the environment, in ``docs/benchmarks/PHASE_03_CONNECTIONS.md``. Numbers from shared or
virtualised machines are noisy: compare configurations measured in the same session only.

Example::

    python3 infra/scripts/measure_db_connections.py --label conn_max_age_0 \\
        --email bench@example.test --password '...' > result.json
"""

from __future__ import annotations

import argparse
import http.client
import json
import statistics
import subprocess
import sys
import threading
import time
from typing import Any

PSQL = [
    "docker",
    "compose",
    "exec",
    "-T",
    "postgres",
    "psql",
    "-U",
    "postgres",
    "-d",
    "erp",
    "-Atc",
]
SESSIONS_SQL = "SELECT sessions FROM pg_stat_database WHERE datname = current_database()"
ACTIVE_SQL = "SELECT count(*) FROM pg_stat_activity WHERE usename = 'erp_app'"


def psql_int(sql: str) -> int:
    out = subprocess.run([*PSQL, sql], capture_output=True, text=True, check=True)  # noqa: S603
    return int(out.stdout.strip() or 0)


def sign_in(args: argparse.Namespace) -> str:
    """Return the Cookie header of a signed-in session (CSRF handshake + password login)."""
    conn = http.client.HTTPConnection(args.address, args.port, timeout=30)
    base = {"Host": args.host_header}
    conn.request("GET", "/api/v1/auth/csrf/", headers=base)
    response = conn.getresponse()
    response.read()
    cookies = _cookies(response)
    csrf = next(v for k, v in cookies.items() if k.endswith("csrftoken"))
    body = json.dumps({"email": args.email, "password": args.password})
    conn.request(
        "POST",
        "/api/v1/auth/login/",
        body=body,
        headers={
            **base,
            "Content-Type": "application/json",
            "X-CSRFToken": csrf,
            "Cookie": _cookie_header(cookies),
            "Origin": f"http://{args.host_header}",
            "Referer": f"http://{args.host_header}/",
        },
    )
    response = conn.getresponse()
    payload = response.read()
    if response.status != 200:
        raise SystemExit(f"sign-in failed: {response.status} {payload[:200]!r}")
    cookies.update(_cookies(response))
    conn.close()
    return _cookie_header(cookies)


def _cookies(response: http.client.HTTPResponse) -> dict[str, str]:
    found: dict[str, str] = {}
    for header in response.headers.get_all("Set-Cookie") or []:
        name, _, rest = header.partition("=")
        found[name.strip()] = rest.split(";", 1)[0]
    return found


def _cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def run_batch(
    args: argparse.Namespace, cookie: str, total: int, concurrency: int
) -> dict[str, Any]:
    latencies: list[float] = []
    statuses: dict[int, int] = {}
    lock = threading.Lock()
    counter = iter(range(total))
    peak_active = 0
    stop = threading.Event()

    def sampler() -> None:
        nonlocal peak_active
        while not stop.is_set():
            try:
                peak_active = max(peak_active, psql_int(ACTIVE_SQL))
            except (subprocess.CalledProcessError, ValueError):
                pass
            stop.wait(0.5)

    def worker() -> None:
        conn = http.client.HTTPConnection(args.address, args.port, timeout=30)
        headers = {"Host": args.host_header, "Cookie": cookie, "Accept": "application/json"}
        while True:
            with lock:
                if next(counter, None) is None:
                    break
            started = time.perf_counter()
            try:
                conn.request("GET", args.path, headers=headers)
                response = conn.getresponse()
                response.read()
                status = response.status
            except (OSError, http.client.HTTPException):
                conn.close()
                conn = http.client.HTTPConnection(args.address, args.port, timeout=30)
                status = 0
            elapsed = (time.perf_counter() - started) * 1000
            with lock:
                latencies.append(elapsed)
                statuses[status] = statuses.get(status, 0) + 1
        conn.close()

    sessions_before = psql_int(SESSIONS_SQL)
    sample_thread = threading.Thread(target=sampler, daemon=True)
    sample_thread.start()
    started = time.perf_counter()
    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.perf_counter() - started
    stop.set()
    sample_thread.join()
    time.sleep(1.0)  # pg_stat_database counters are flushed with a small delay
    sessions_after = psql_int(SESSIONS_SQL)
    ordered = sorted(latencies)

    def pct(p: float) -> float:
        return round(ordered[min(len(ordered) - 1, int(len(ordered) * p))], 2)

    return {
        "requests": total,
        "statuses": statuses,
        "p50_ms": pct(0.50),
        "p95_ms": pct(0.95),
        "p99_ms": pct(0.99),
        "mean_ms": round(statistics.fmean(ordered), 2),
        "requests_per_second": round(total / wall, 1),
        # Includes the sampler's own psql sessions (two per second) and background services.
        "pg_sessions_opened": sessions_after - sessions_before,
        "pg_peak_erp_app_connections": peak_active,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--label", required=True, help="configuration name, e.g. conn_max_age_0")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--address", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host-header", default="localhost:8080")
    parser.add_argument("--path", default="/api/v1/me/")
    parser.add_argument("--warmup", type=int, default=200)
    parser.add_argument("--requests", type=int, default=2000)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 8, 32])
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()

    cookie = sign_in(args)
    results: dict[str, Any] = {"label": args.label, "path": args.path, "host": args.host_header}
    for concurrency in args.concurrency:
        run_batch(args, cookie, args.warmup, concurrency)
        runs = [
            run_batch(args, cookie, args.requests, concurrency) for _ in range(args.repetitions)
        ]
        errors = sum(n for run in runs for status, n in run["statuses"].items() if status != 200)
        results[f"concurrency_{concurrency}"] = {
            "runs": runs,
            "non_200_responses": errors,
            "median_p50_ms": statistics.median(run["p50_ms"] for run in runs),
            "median_p95_ms": statistics.median(run["p95_ms"] for run in runs),
            "median_p99_ms": statistics.median(run["p99_ms"] for run in runs),
            "median_requests_per_second": statistics.median(
                run["requests_per_second"] for run in runs
            ),
            "median_pg_sessions_opened": statistics.median(
                run["pg_sessions_opened"] for run in runs
            ),
            "max_pg_peak_erp_app_connections": max(
                run["pg_peak_erp_app_connections"] for run in runs
            ),
        }
        print(f"[{args.label}] concurrency {concurrency} done", file=sys.stderr)
    json.dump(results, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
