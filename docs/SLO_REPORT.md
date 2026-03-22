# OrderFlow Stress Test — SLO Report

Generated: 2026-03-22T14:21:56.669823+00:00

Waves measured: 12

## SLO Definitions

| # | SLO | Threshold |
|---|-----|-----------|
| SLO-1 | CDC latency | < 30s |
| SLO-2 | Batch ingestion duration | < 15min |
| SLO-3 | dbt-clickhouse run duration | < 5min |
| SLO-4 | ClickHouse query latency (p95) | < 2s |
| SLO-5 | Data quality pass rate | 100% |
| SLO-6 | Zero data loss | silver >= PG |

## Per-Wave Results

| Wave | CDC Latency (s) | Batch (s) | dbt (s) | Query p95 (s) | DQ Rate | Data Loss |
|------|-----------------|-----------|---------|---------------|---------|-----------|
| 1 | 40.214 [FAIL] | N/A - no DAG runs recorded [N/A] | N/A - no DAG runs recorded [N/A] | 0.1806 [PASS] | 100.00% [PASS] | diff=0 [PASS] |
| 2 | 40.206 [FAIL] | N/A - no DAG runs recorded [N/A] | N/A - no DAG runs recorded [N/A] | 0.1094 [PASS] | 100.00% [PASS] | diff=0 [PASS] |
| 3 | 40.219 [FAIL] | N/A - no DAG runs recorded [N/A] | N/A - no DAG runs recorded [N/A] | 0.0895 [PASS] | 100.00% [PASS] | diff=0 [PASS] |
| 4 | 40.226 [FAIL] | N/A - no DAG runs recorded [N/A] | N/A - no DAG runs recorded [N/A] | 0.0892 [PASS] | 100.00% [PASS] | diff=0 [PASS] |
| 5 | 40.23 [FAIL] | N/A - no DAG runs recorded [N/A] | N/A - no DAG runs recorded [N/A] | 0.1838 [PASS] | 100.00% [PASS] | diff=0 [PASS] |
| 6 | 40.285 [FAIL] | N/A - no DAG runs recorded [N/A] | N/A - no DAG runs recorded [N/A] | 0.1229 [PASS] | 100.00% [PASS] | diff=0 [PASS] |
| 7 | 40.243 [FAIL] | N/A - no DAG runs recorded [N/A] | N/A - no DAG runs recorded [N/A] | 0.1068 [PASS] | 100.00% [PASS] | diff=0 [PASS] |
| 8 | 40.218 [FAIL] | N/A - no DAG runs recorded [N/A] | N/A - no DAG runs recorded [N/A] | 0.1617 [PASS] | 100.00% [PASS] | diff=0 [PASS] |
| 9 | 40.221 [FAIL] | N/A - no DAG runs recorded [N/A] | N/A - no DAG runs recorded [N/A] | 0.1218 [PASS] | 100.00% [PASS] | diff=0 [PASS] |
| 10 | 40.241 [FAIL] | N/A - no DAG runs recorded [N/A] | N/A - no DAG runs recorded [N/A] | 0.1335 [PASS] | 100.00% [PASS] | diff=0 [PASS] |
| 11 | 40.2 [FAIL] | N/A - no DAG runs recorded [N/A] | N/A - no DAG runs recorded [N/A] | 0.0978 [PASS] | 100.00% [PASS] | diff=0 [PASS] |
| 12 | 40.2 [FAIL] | N/A - no DAG runs recorded [N/A] | N/A - no DAG runs recorded [N/A] | 0.0955 [PASS] | 100.00% [PASS] | diff=0 [PASS] |

## Summary

- **Total SLO checks:** 72
- **Passed:** 36
- **Failed:** 12
- **N/A:** 24
- **Pass rate (excluding N/A):** 75.0%

