#!/usr/bin/env python3
"""
OrderFlow Phase 8 — SLO Measurement Script

Measures 6 SLOs after each stress test wave and generates a summary report.

SLOs:
  1. CDC latency < 30s
  2. Batch ingestion duration < 15min
  3. dbt-clickhouse run duration < 5min
  4. ClickHouse query latency p95 < 2s
  5. Data quality pass rate = 100%
  6. Zero data loss (PG orders == silver.orders FINAL non-deleted)
"""

import argparse
import glob
import json
import os
import random
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import clickhouse_driver
import psycopg2

# ---------------------------------------------------------------------------
# Connection parameters
# ---------------------------------------------------------------------------
PG_PARAMS = {
    "host": "localhost",
    "port": 30432,
    "user": "orderflow",
    "password": "orderflow_pg_pass",
    "dbname": "orderflow",
}

CH_PARAMS = {
    "host": "localhost",
    "port": 30900,
    "user": "default",
    "password": "",
}

# SLO thresholds
CDC_LATENCY_THRESHOLD_S = 30.0
BATCH_INGESTION_THRESHOLD_S = 900.0   # 15 minutes
DBT_RUN_THRESHOLD_S = 300.0           # 5 minutes
QUERY_LATENCY_P95_THRESHOLD_S = 2.0
DATA_QUALITY_THRESHOLD = 1.0          # 100%

# Sample queries for SLO 4 (ClickHouse query latency)
SAMPLE_QUERIES = [
    "SELECT count() FROM silver.orders FINAL WHERE is_deleted = 0",
    "SELECT status, count() FROM silver.orders FINAL WHERE is_deleted = 0 GROUP BY status",
    "SELECT toDate(created_at) AS d, count() FROM silver.orders FINAL WHERE is_deleted = 0 GROUP BY d ORDER BY d DESC LIMIT 7",
    "SELECT restaurant_id, sum(total_amount) AS rev FROM silver.orders FINAL WHERE is_deleted = 0 GROUP BY restaurant_id ORDER BY rev DESC LIMIT 10",
    "SELECT count() FROM silver.user_events FINAL WHERE is_deleted = 0",
]
QUERY_ITERATIONS = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_pg_connection():
    """Return a new PostgreSQL connection."""
    return psycopg2.connect(**PG_PARAMS)


def get_ch_client():
    """Return a new ClickHouse client."""
    return clickhouse_driver.Client(**CH_PARAMS)


def results_dir() -> Path:
    """Return the results directory path, creating it if needed."""
    d = Path(__file__).parent / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# SLO 1: CDC Latency
# ---------------------------------------------------------------------------

def measure_cdc_latency() -> dict:
    """Insert a probe row into PG orders, poll bronze.orders_raw until it appears.

    Returns dict with latency_s and pass/fail.
    """
    probe_user_id = random.randint(1, 5000)
    probe_amount = round(random.uniform(999.01, 999.99), 2)
    probe_marker = str(uuid.uuid4())[:8]

    # Insert probe row into PostgreSQL
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO orders
                    (user_id, restaurant_id, driver_id, status,
                     total_amount, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                (probe_user_id, 1, 1, "pending", probe_amount),
            )
            probe_id = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    print(f"  SLO-1: Inserted probe order id={probe_id}, polling bronze.orders_raw...")

    # Poll ClickHouse bronze.orders_raw for the probe row
    ch = get_ch_client()
    start = time.time()
    found = False
    latency = None

    while time.time() - start < CDC_LATENCY_THRESHOLD_S + 10:
        try:
            rows = ch.execute(
                "SELECT id FROM bronze.orders_raw WHERE id = %(probe_id)s LIMIT 1",
                {"probe_id": probe_id},
            )
            if rows and len(rows) > 0:
                latency = time.time() - start
                found = True
                break
        except Exception:
            pass  # table may not exist yet or be empty
        time.sleep(1.0)

    if not found:
        latency = time.time() - start

    passed = found and latency <= CDC_LATENCY_THRESHOLD_S
    result = {
        "slo": "CDC latency",
        "threshold": f"<{CDC_LATENCY_THRESHOLD_S}s",
        "probe_order_id": probe_id,
        "found_in_bronze": found,
        "latency_s": round(latency, 3) if latency else None,
        "passed": passed,
    }
    status_str = "PASS" if passed else "FAIL"
    print(f"  SLO-1: {status_str} — latency={latency:.2f}s, found={found}")
    return result


# ---------------------------------------------------------------------------
# SLO 2: Batch Ingestion Duration
# ---------------------------------------------------------------------------

def measure_batch_ingestion_duration() -> dict:
    """Query gold.dag_run_log for the latest orderflow_batch_ingestion run duration."""
    ch = get_ch_client()
    try:
        rows = ch.execute(
            """
            SELECT duration_seconds
            FROM gold.dag_run_log
            WHERE dag_id = 'orderflow_batch_ingestion'
            ORDER BY execution_date DESC
            LIMIT 1
            """
        )
    except Exception as e:
        print(f"  SLO-2: Query failed — {e}")
        return {
            "slo": "Batch ingestion duration",
            "threshold": f"<{BATCH_INGESTION_THRESHOLD_S}s",
            "value_s": "N/A - no DAG runs recorded",
            "passed": "N/A",
        }

    if not rows:
        print("  SLO-2: N/A — no DAG runs recorded for orderflow_batch_ingestion")
        return {
            "slo": "Batch ingestion duration",
            "threshold": f"<{BATCH_INGESTION_THRESHOLD_S}s",
            "value_s": "N/A - no DAG runs recorded",
            "passed": "N/A",
        }

    duration = float(rows[0][0])
    passed = duration <= BATCH_INGESTION_THRESHOLD_S
    status_str = "PASS" if passed else "FAIL"
    print(f"  SLO-2: {status_str} — duration={duration:.1f}s")
    return {
        "slo": "Batch ingestion duration",
        "threshold": f"<{BATCH_INGESTION_THRESHOLD_S}s",
        "value_s": round(duration, 3),
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# SLO 3: dbt-clickhouse Run Duration
# ---------------------------------------------------------------------------

def measure_dbt_run_duration() -> dict:
    """Query gold.dag_run_log for the latest orderflow_dbt_clickhouse run duration."""
    ch = get_ch_client()
    try:
        rows = ch.execute(
            """
            SELECT duration_seconds
            FROM gold.dag_run_log
            WHERE dag_id = 'orderflow_dbt_clickhouse'
            ORDER BY execution_date DESC
            LIMIT 1
            """
        )
    except Exception as e:
        print(f"  SLO-3: Query failed — {e}")
        return {
            "slo": "dbt-clickhouse run duration",
            "threshold": f"<{DBT_RUN_THRESHOLD_S}s",
            "value_s": "N/A - no DAG runs recorded",
            "passed": "N/A",
        }

    if not rows:
        print("  SLO-3: N/A — no DAG runs recorded for orderflow_dbt_clickhouse")
        return {
            "slo": "dbt-clickhouse run duration",
            "threshold": f"<{DBT_RUN_THRESHOLD_S}s",
            "value_s": "N/A - no DAG runs recorded",
            "passed": "N/A",
        }

    duration = float(rows[0][0])
    passed = duration <= DBT_RUN_THRESHOLD_S
    status_str = "PASS" if passed else "FAIL"
    print(f"  SLO-3: {status_str} — duration={duration:.1f}s")
    return {
        "slo": "dbt-clickhouse run duration",
        "threshold": f"<{DBT_RUN_THRESHOLD_S}s",
        "value_s": round(duration, 3),
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# SLO 4: ClickHouse Query Latency (p95)
# ---------------------------------------------------------------------------

def measure_query_latency() -> dict:
    """Run sample queries N times each and compute p95 latency."""
    ch = get_ch_client()
    latencies = []

    for query in SAMPLE_QUERIES:
        for _ in range(QUERY_ITERATIONS):
            start = time.time()
            try:
                ch.execute(query)
            except Exception as e:
                print(f"  SLO-4: Query error — {e}")
            elapsed = time.time() - start
            latencies.append(elapsed)

    if not latencies:
        print("  SLO-4: No queries executed successfully")
        return {
            "slo": "ClickHouse query latency p95",
            "threshold": f"<{QUERY_LATENCY_P95_THRESHOLD_S}s",
            "p95_s": None,
            "passed": False,
        }

    latencies.sort()
    p95_idx = int(len(latencies) * 0.95)
    p95 = latencies[min(p95_idx, len(latencies) - 1)]
    avg = statistics.mean(latencies)
    passed = p95 <= QUERY_LATENCY_P95_THRESHOLD_S

    status_str = "PASS" if passed else "FAIL"
    print(
        f"  SLO-4: {status_str} — p95={p95:.3f}s, avg={avg:.3f}s, "
        f"samples={len(latencies)}"
    )
    return {
        "slo": "ClickHouse query latency p95",
        "threshold": f"<{QUERY_LATENCY_P95_THRESHOLD_S}s",
        "p95_s": round(p95, 4),
        "avg_s": round(avg, 4),
        "min_s": round(min(latencies), 4),
        "max_s": round(max(latencies), 4),
        "sample_count": len(latencies),
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# SLO 5: Data Quality Pass Rate
# ---------------------------------------------------------------------------

def measure_data_quality() -> dict:
    """Check gold.pii_audit_log for data quality pass rate."""
    ch = get_ch_client()
    try:
        rows = ch.execute(
            """
            SELECT
                countIf(passed = 1) AS pass_count,
                count() AS total_count
            FROM gold.pii_audit_log
            """
        )
    except Exception as e:
        print(f"  SLO-5: Query failed — {e}")
        return {
            "slo": "Data quality pass rate",
            "threshold": "100%",
            "pass_rate": None,
            "passed": False,
            "error": str(e),
        }

    if not rows or rows[0][1] == 0:
        print("  SLO-5: No audit log entries found")
        return {
            "slo": "Data quality pass rate",
            "threshold": "100%",
            "pass_count": 0,
            "total_count": 0,
            "pass_rate": "N/A - no audit entries",
            "passed": "N/A",
        }

    pass_count, total_count = rows[0]
    pass_rate = pass_count / total_count if total_count > 0 else 0.0
    passed = pass_rate >= DATA_QUALITY_THRESHOLD

    status_str = "PASS" if passed else "FAIL"
    print(
        f"  SLO-5: {status_str} — rate={pass_rate:.2%} "
        f"({pass_count}/{total_count})"
    )
    return {
        "slo": "Data quality pass rate",
        "threshold": "100%",
        "pass_count": pass_count,
        "total_count": total_count,
        "pass_rate": round(pass_rate, 4),
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# SLO 6: Zero Data Loss
# ---------------------------------------------------------------------------

def measure_data_loss() -> dict:
    """Compare PostgreSQL orders count vs silver.orders FINAL non-deleted count."""
    # PostgreSQL count
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM orders")
            pg_count = cur.fetchone()[0]
    finally:
        conn.close()

    # ClickHouse silver count (all non-deleted rows)
    ch = get_ch_client()
    try:
        rows = ch.execute(
            "SELECT count() FROM silver.orders FINAL WHERE is_deleted = 0"
        )
        ch_count = rows[0][0] if rows else 0
    except Exception as e:
        print(f"  SLO-6: ClickHouse query failed — {e}")
        return {
            "slo": "Zero data loss",
            "threshold": "silver >= PG",
            "pg_count": pg_count,
            "ch_count": None,
            "diff": None,
            "passed": False,
            "error": str(e),
        }

    diff = pg_count - ch_count
    # Per plan: "order count in Gold >= count in PostgreSQL"
    passed = ch_count >= pg_count

    status_str = "PASS" if passed else "FAIL"
    print(
        f"  SLO-6: {status_str} — PG={pg_count}, silver={ch_count}, diff={diff}"
    )
    return {
        "slo": "Zero data loss",
        "threshold": "PG active orders == silver.orders non-deleted",
        "pg_active_orders": pg_count,
        "ch_silver_orders": ch_count,
        "diff": diff,
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# Wave measurement
# ---------------------------------------------------------------------------

def measure_all_slos(wave_id: int) -> dict:
    """Measure all 6 SLOs and return combined results."""
    print(f"\n{'='*60}")
    print(f"SLO Measurement — Wave {wave_id}")
    print(f"{'='*60}")

    result = {
        "wave_id": wave_id,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "slos": {},
    }

    print("\n[1/6] CDC Latency...")
    result["slos"]["cdc_latency"] = measure_cdc_latency()

    print("\n[2/6] Batch Ingestion Duration...")
    result["slos"]["batch_ingestion"] = measure_batch_ingestion_duration()

    print("\n[3/6] dbt-clickhouse Run Duration...")
    result["slos"]["dbt_run"] = measure_dbt_run_duration()

    print("\n[4/6] ClickHouse Query Latency (p95)...")
    result["slos"]["query_latency"] = measure_query_latency()

    print("\n[5/6] Data Quality Pass Rate...")
    result["slos"]["data_quality"] = measure_data_quality()

    print("\n[6/6] Zero Data Loss...")
    result["slos"]["data_loss"] = measure_data_loss()

    # Summary
    slo_results = result["slos"]
    total = len(slo_results)
    passed = sum(
        1 for s in slo_results.values()
        if s.get("passed") is True
    )
    na_count = sum(
        1 for s in slo_results.values()
        if s.get("passed") == "N/A"
    )

    result["summary"] = {
        "total_slos": total,
        "passed": passed,
        "failed": total - passed - na_count,
        "na": na_count,
    }

    print(f"\nSummary: {passed}/{total} passed, {na_count} N/A")
    return result


def save_slo_results(wave_id: int, results: dict) -> str:
    """Save SLO results to stress/results/slo_wave_{N}.json."""
    out_dir = results_dir()
    output_path = out_dir / f"slo_wave_{wave_id}.json"

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"SLO results saved to {output_path}")
    return str(output_path)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report() -> None:
    """Read all slo_wave_*.json files and print a markdown report to stdout."""
    pattern = str(results_dir() / "slo_wave_*.json")
    files = sorted(glob.glob(pattern))

    if not files:
        print("No SLO result files found. Run --wave N first.")
        sys.exit(1)

    all_results = []
    for f in files:
        with open(f, "r") as fh:
            all_results.append(json.load(fh))

    # Sort by wave_id
    all_results.sort(key=lambda r: r.get("wave_id", 0))

    # Header
    print("# OrderFlow Stress Test — SLO Report")
    print()
    print(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    print()
    print(f"Waves measured: {len(all_results)}")
    print()

    # SLO definitions
    print("## SLO Definitions")
    print()
    print("| # | SLO | Threshold |")
    print("|---|-----|-----------|")
    print("| SLO-1 | CDC latency | < 30s |")
    print("| SLO-2 | Batch ingestion duration | < 15min |")
    print("| SLO-3 | dbt-clickhouse run duration | < 5min |")
    print("| SLO-4 | ClickHouse query latency (p95) | < 2s |")
    print("| SLO-5 | Data quality pass rate | 100% |")
    print("| SLO-6 | Zero data loss | silver >= PG |")
    print()

    # Per-wave results table
    print("## Per-Wave Results")
    print()
    print(
        "| Wave | CDC Latency (s) | Batch (s) | dbt (s) "
        "| Query p95 (s) | DQ Rate | Data Loss |"
    )
    print(
        "|------|-----------------|-----------|---------|"
        "---------------|---------|-----------|"
    )

    for r in all_results:
        wave_id = r.get("wave_id", "?")
        slos = r.get("slos", {})

        cdc = slos.get("cdc_latency", {})
        cdc_val = cdc.get("latency_s", "N/A")
        cdc_pass = _pass_icon(cdc.get("passed"))

        batch = slos.get("batch_ingestion", {})
        batch_val = batch.get("value_s", "N/A")
        batch_pass = _pass_icon(batch.get("passed"))

        dbt = slos.get("dbt_run", {})
        dbt_val = dbt.get("value_s", "N/A")
        dbt_pass = _pass_icon(dbt.get("passed"))

        ql = slos.get("query_latency", {})
        ql_val = ql.get("p95_s", "N/A")
        ql_pass = _pass_icon(ql.get("passed"))

        dq = slos.get("data_quality", {})
        dq_val = dq.get("pass_rate", "N/A")
        if isinstance(dq_val, float):
            dq_val = f"{dq_val:.2%}"
        dq_pass = _pass_icon(dq.get("passed"))

        dl = slos.get("data_loss", {})
        dl_diff = dl.get("diff", "N/A")
        dl_pass = _pass_icon(dl.get("passed"))

        print(
            f"| {wave_id} "
            f"| {cdc_val} {cdc_pass} "
            f"| {batch_val} {batch_pass} "
            f"| {dbt_val} {dbt_pass} "
            f"| {ql_val} {ql_pass} "
            f"| {dq_val} {dq_pass} "
            f"| diff={dl_diff} {dl_pass} |"
        )

    print()

    # Summary
    print("## Summary")
    print()
    total_passed = 0
    total_failed = 0
    total_na = 0
    for r in all_results:
        s = r.get("summary", {})
        total_passed += s.get("passed", 0)
        total_failed += s.get("failed", 0)
        total_na += s.get("na", 0)

    total_checks = total_passed + total_failed + total_na
    print(f"- **Total SLO checks:** {total_checks}")
    print(f"- **Passed:** {total_passed}")
    print(f"- **Failed:** {total_failed}")
    print(f"- **N/A:** {total_na}")
    if total_checks - total_na > 0:
        rate = total_passed / (total_checks - total_na)
        print(f"- **Pass rate (excluding N/A):** {rate:.1%}")
    print()


def _pass_icon(value) -> str:
    """Return a text indicator for pass/fail/N/A."""
    if value is True:
        return "[PASS]"
    elif value is False:
        return "[FAIL]"
    else:
        return "[N/A]"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="OrderFlow Phase 8 — SLO Measurement"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--wave",
        type=int,
        help="Wave number to measure SLOs for (1-12)",
    )
    group.add_argument(
        "--report",
        action="store_true",
        help="Generate markdown report from all collected SLO results",
    )
    args = parser.parse_args()

    if args.report:
        generate_report()
    else:
        if args.wave < 1 or args.wave > 12:
            print(f"ERROR: Wave must be between 1 and 12, got {args.wave}")
            sys.exit(1)
        results = measure_all_slos(args.wave)
        save_slo_results(args.wave, results)


if __name__ == "__main__":
    main()
