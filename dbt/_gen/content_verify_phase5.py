"""verify_phase5.sh content -- 10 checks for Phase 5."""


def get() -> str:
    return """\
#!/usr/bin/env bash
# scripts/verify_phase5.sh -- Phase 5 verification (10 checks)
# Run from the EC2 host after dbt run and dbt snapshot have completed.
# Requires: clickhouse-client, mc (MinIO client), kubectl, dbt (in PATH or venv)
set -euo pipefail

PASS=0
FAIL=0
CH="clickhouse-client --host localhost --port 30900 --query"

check() {
    local num="$1" desc="$2" result="$3"
    if [[ "$result" == "pass" ]]; then
        echo "  [CHECK ${num}] PASS -- ${desc}"
        PASS=$((PASS + 1))
    else
        echo "  [CHECK ${num}] FAIL -- ${desc}: ${result#fail: }"
        FAIL=$((FAIL + 1))
    fi
}

echo "================================================================"
echo " OrderFlow Phase 5 -- Verification"
echo "================================================================"

# Check 1: dbt_dev__gold database has mart tables ─────────────────────────────
echo ""
echo "Check 1: dbt_dev__gold database exists and contains mart tables"
MART_COUNT=$($CH "SELECT count() FROM system.tables
    WHERE database = 'dbt_dev__gold' AND name LIKE 'mart_%'" 2>/dev/null || echo "0")
if [[ "$MART_COUNT" -ge 5 ]]; then
    check 1 "dbt_dev__gold has ${MART_COUNT} mart tables (expected >= 5)" "pass"
else
    check 1 "dbt_dev__gold mart tables" \
        "fail: found ${MART_COUNT} mart tables, expected >= 5"
fi

# Check 2: mart_restaurant_revenue has rows ───────────────────────────────────
echo ""
echo "Check 2: mart_restaurant_revenue has rows"
RR=$($CH "SELECT count() FROM dbt_dev__gold.mart_restaurant_revenue" 2>/dev/null || echo "0")
if [[ "$RR" -gt 0 ]]; then
    check 2 "mart_restaurant_revenue has ${RR} rows" "pass"
else
    check 2 "mart_restaurant_revenue" "fail: 0 rows or table missing"
fi

# Check 3: mart_driver_kpis has rows ──────────────────────────────────────────
echo ""
echo "Check 3: mart_driver_kpis has rows"
DK=$($CH "SELECT count() FROM dbt_dev__gold.mart_driver_kpis" 2>/dev/null || echo "0")
if [[ "$DK" -gt 0 ]]; then
    check 3 "mart_driver_kpis has ${DK} rows" "pass"
else
    check 3 "mart_driver_kpis" "fail: 0 rows or table missing"
fi

# Check 4: mart_order_funnel has rows ─────────────────────────────────────────
echo ""
echo "Check 4: mart_order_funnel has rows"
OF=$($CH "SELECT count() FROM dbt_dev__gold.mart_order_funnel" 2>/dev/null || echo "0")
if [[ "$OF" -gt 0 ]]; then
    check 4 "mart_order_funnel has ${OF} rows" "pass"
else
    check 4 "mart_order_funnel" "fail: 0 rows or table missing"
fi

# Check 5: mart_user_cohorts has rows ─────────────────────────────────────────
echo ""
echo "Check 5: mart_user_cohorts has rows"
UC=$($CH "SELECT count() FROM dbt_dev__gold.mart_user_cohorts" 2>/dev/null || echo "0")
if [[ "$UC" -gt 0 ]]; then
    check 5 "mart_user_cohorts has ${UC} rows" "pass"
else
    check 5 "mart_user_cohorts" "fail: 0 rows or table missing"
fi

# Check 6: mart_demand_zone has rows ──────────────────────────────────────────
echo ""
echo "Check 6: mart_demand_zone has rows"
DZ=$($CH "SELECT count() FROM dbt_dev__gold.mart_demand_zone" 2>/dev/null || echo "0")
if [[ "$DZ" -gt 0 ]]; then
    check 6 "mart_demand_zone has ${DZ} rows" "pass"
else
    check 6 "mart_demand_zone" "fail: 0 rows or table missing"
fi

# Check 7: snap_restaurant_attrs snapshot exists and has rows ─────────────────
echo ""
echo "Check 7: snap_restaurant_attrs snapshot populated"
SNAP=$($CH "SELECT count() FROM dbt_dev__gold.snap_restaurant_attrs" 2>/dev/null || echo "0")
if [[ "$SNAP" -gt 0 ]]; then
    check 7 "snap_restaurant_attrs has ${SNAP} rows" "pass"
else
    check 7 "snap_restaurant_attrs" "fail: 0 rows or snapshot not run"
fi

# Check 8: stg_orders view exists ─────────────────────────────────────────────
echo ""
echo "Check 8: stg_orders view exists in dbt_dev__gold"
VIEW_EXISTS=$($CH "SELECT count() FROM system.tables
    WHERE database = 'dbt_dev__gold' AND name = 'stg_orders'
    AND engine = 'View'" 2>/dev/null || echo "0")
if [[ "$VIEW_EXISTS" -eq 1 ]]; then
    check 8 "stg_orders view exists in dbt_dev__gold" "pass"
else
    check 8 "stg_orders view" "fail: view not found in dbt_dev__gold"
fi

# Check 9: dbt test exit code ─────────────────────────────────────────────────
echo ""
echo "Check 9: dbt test passes (staging schema tests)"
DBT_DIR="${HOME}/OrderFlow/dbt/orderflow_clickhouse"
if [[ -d "$DBT_DIR" ]]; then
    if (cd "$DBT_DIR" && dbt test --select staging --no-version-check \
            --profiles-dir . 2>&1 | tail -5 | grep -q "pass"); then
        check 9 "dbt test staging passed" "pass"
    else
        check 9 "dbt test staging" "fail: one or more tests failed -- check dbt logs"
    fi
else
    check 9 "dbt test staging" "fail: dbt project dir not found at ${DBT_DIR}"
fi

# Check 10: dbt-spark warehouse files in MinIO ────────────────────────────────
echo ""
echo "Check 10: dbt-spark output files present in MinIO"
SPARK_FILES=$(mc ls minio/orderflow-silver/delta/ 2>/dev/null | wc -l || echo "0")
if [[ "$SPARK_FILES" -gt 0 ]]; then
    check 10 "dbt-spark Delta files in MinIO (count=${SPARK_FILES})" "pass"
else
    check 10 "dbt-spark Delta files in MinIO" \
        "fail: no files under minio/orderflow-silver/delta/"
fi

# Summary ─────────────────────────────────────────────────────────────────────
echo ""
echo "================================================================"
echo " Results: ${PASS} passed, ${FAIL} failed (out of 10)"
echo "================================================================"
if [[ "$FAIL" -eq 0 ]]; then
    echo " Phase 5 VERIFIED"
    exit 0
else
    echo " Phase 5 INCOMPLETE -- fix failures before marking complete."
    exit 1
fi
"""
