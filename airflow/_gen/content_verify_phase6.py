"""verify_phase6.sh content -- 10 checks for Phase 6."""

def verify_phase6_sh() -> str:
    return """\
#!/usr/bin/env bash
# scripts/verify_phase6.sh -- Phase 6 verification (10 checks).
# Requires: clickhouse-client (port 30900), kubectl, curl (Airflow at :30080).
set -euo pipefail

PASS=0
FAIL=0
CH="clickhouse-client --host localhost --port 30900 --query"
AIRFLOW_API="http://localhost:30080/api/v1"
# Airflow basic auth (admin:admin default -- override via AIRFLOW_USER / AIRFLOW_PASS env vars)
AIRFLOW_USER="${AIRFLOW_USER:-admin}"; AIRFLOW_PASS="${AIRFLOW_PASS:-admin}"

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
echo " OrderFlow Phase 6 -- Verification"
echo "================================================================"

# Check 1: gold.pii_audit_log table exists ─────────────────────────────────
echo ""
echo "Check 1: gold.pii_audit_log table exists in ClickHouse"
PAL=$($CH "SELECT count() FROM system.tables
    WHERE database = 'gold' AND name = 'pii_audit_log'" 2>/dev/null || echo "0")
if [[ "$PAL" -eq 1 ]]; then
    check 1 "gold.pii_audit_log table exists" "pass"
else
    check 1 "gold.pii_audit_log table exists" \
        "fail: table not found in gold database"
fi

# Check 2: All Phase 6 DAGs visible in Airflow ────────────────────────────
echo ""
echo "Check 2: All 8 Phase 6 DAGs visible in Airflow REST API"
DAG_LIST=$(curl -s -u "${AIRFLOW_USER}:${AIRFLOW_PASS}" \
    "${AIRFLOW_API}/dags?limit=100" 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(x['dag_id'] for x in d.get('dags',[])))" \
    2>/dev/null || echo "")
EXPECTED_DAGS=(
    "orderflow_batch_ingestion"
    "orderflow_dbt_clickhouse"
    "orderflow_dbt_clickhouse_staging"
    "orderflow_dbt_spark"
    "orderflow_delta_optimize"
    "orderflow_quality_gate"
    "orderflow_pii_audit"
    "orderflow_schema_drift"
)
ALL_FOUND=1
MISSING_DAGS=""
for dag_id in "${EXPECTED_DAGS[@]}"; do
    if ! echo "$DAG_LIST" | grep -q "$dag_id"; then
        ALL_FOUND=0
        MISSING_DAGS="${MISSING_DAGS} ${dag_id}"
    fi
done
if [[ "$ALL_FOUND" -eq 1 ]]; then
    check 2 "All 8 Phase 6 DAGs found in Airflow" "pass"
else
    check 2 "Phase 6 DAGs in Airflow" "fail: missing DAGs:${MISSING_DAGS}"
fi

# Check 3: DAG 1 (batch ingestion) exists ─────────────────────────────────
echo ""
echo "Check 3: orderflow_batch_ingestion DAG exists"
DAG1=$(curl -s -u "${AIRFLOW_USER}:${AIRFLOW_PASS}" \
    "${AIRFLOW_API}/dags/orderflow_batch_ingestion" 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('dag_id',''))" \
    2>/dev/null || echo "")
if [[ "$DAG1" == "orderflow_batch_ingestion" ]]; then
    check 3 "orderflow_batch_ingestion DAG exists" "pass"
else
    check 3 "orderflow_batch_ingestion DAG exists" \
        "fail: DAG not found or API unreachable"
fi

# Check 4: DAG 2 (dbt clickhouse) exists ─────────────────────────────────
echo ""
echo "Check 4: orderflow_dbt_clickhouse DAG exists"
DAG2=$(curl -s -u "${AIRFLOW_USER}:${AIRFLOW_PASS}" \
    "${AIRFLOW_API}/dags/orderflow_dbt_clickhouse" 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('dag_id',''))" \
    2>/dev/null || echo "")
if [[ "$DAG2" == "orderflow_dbt_clickhouse" ]]; then
    check 4 "orderflow_dbt_clickhouse DAG exists" "pass"
else
    check 4 "orderflow_dbt_clickhouse DAG exists" \
        "fail: DAG not found or API unreachable"
fi

# Check 5: DAG 5 (quality gate) exists ────────────────────────────────────
echo ""
echo "Check 5: orderflow_quality_gate DAG exists"
DAG5=$(curl -s -u "${AIRFLOW_USER}:${AIRFLOW_PASS}" \
    "${AIRFLOW_API}/dags/orderflow_quality_gate" 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('dag_id',''))" \
    2>/dev/null || echo "")
if [[ "$DAG5" == "orderflow_quality_gate" ]]; then
    check 5 "orderflow_quality_gate DAG exists" "pass"
else
    check 5 "orderflow_quality_gate DAG exists" \
        "fail: DAG not found or API unreachable"
fi

# Check 6: DAG 6 (schema drift) exists ────────────────────────────────────
echo ""
echo "Check 6: orderflow_schema_drift DAG exists"
DAG6=$(curl -s -u "${AIRFLOW_USER}:${AIRFLOW_PASS}" \
    "${AIRFLOW_API}/dags/orderflow_schema_drift" 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('dag_id',''))" \
    2>/dev/null || echo "")
if [[ "$DAG6" == "orderflow_schema_drift" ]]; then
    check 6 "orderflow_schema_drift DAG exists" "pass"
else
    check 6 "orderflow_schema_drift DAG exists" \
        "fail: DAG not found or API unreachable"
fi

# Check 7: DAG 7 (pii audit) exists ───────────────────────────────────────
echo ""
echo "Check 7: orderflow_pii_audit DAG exists"
DAG7=$(curl -s -u "${AIRFLOW_USER}:${AIRFLOW_PASS}" \
    "${AIRFLOW_API}/dags/orderflow_pii_audit" 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('dag_id',''))" \
    2>/dev/null || echo "")
if [[ "$DAG7" == "orderflow_pii_audit" ]]; then
    check 7 "orderflow_pii_audit DAG exists" "pass"
else
    check 7 "orderflow_pii_audit DAG exists" \
        "fail: DAG not found or API unreachable"
fi

# Check 8: dbt_staging__gold database exists in ClickHouse ────────────────
echo ""
echo "Check 8: dbt_staging__gold database exists in ClickHouse"
STAGING_DB=$($CH "SELECT count() FROM system.databases
    WHERE name = 'dbt_staging__gold'" 2>/dev/null || echo "0")
if [[ "$STAGING_DB" -eq 1 ]]; then
    check 8 "dbt_staging__gold database exists" "pass"
else
    check 8 "dbt_staging__gold database exists" \
        "fail: database not found -- run DAG 2b (orderflow_dbt_clickhouse_staging) first"
fi

# Check 9: Airflow connections configured ─────────────────────────────────
echo ""
echo "Check 9: Airflow connections present (clickhouse_default, spark_default)"
CONN_LIST=$(kubectl exec -n airflow airflow-0 -- \
    airflow connections list 2>/dev/null || echo "")
CONN_PASS=1
for conn in "clickhouse_default" "spark_default"; do
    if ! echo "$CONN_LIST" | grep -q "$conn"; then
        CONN_PASS=0
        echo "  WARNING: Missing Airflow connection: $conn"
    fi
done
if [[ "$CONN_PASS" -eq 1 ]]; then
    check 9 "Airflow connections clickhouse_default and spark_default present" "pass"
else
    check 9 "Airflow connections" \
        "fail: one or more expected connections missing -- check Airflow UI Admin > Connections"
fi

# Check 10: SparkApplication RBAC exists ──────────────────────────────────
echo ""
echo "Check 10: SparkApplication RBAC (ServiceAccount spark in default namespace)"
SA_EXISTS=$(kubectl get serviceaccount spark -n default --ignore-not-found 2>/dev/null | wc -l || echo "0")
CR_EXISTS=$(kubectl get clusterrole spark-role --ignore-not-found 2>/dev/null | wc -l || echo "0")
if [[ "$SA_EXISTS" -gt 1 || "$CR_EXISTS" -gt 1 ]]; then
    check 10 "SparkApplication RBAC found in default namespace" "pass"
else
    check 10 "SparkApplication RBAC" \
        "fail: spark ServiceAccount and ClusterRole not found in default namespace"
fi

# Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "================================================================"
echo " Results: ${PASS} passed, ${FAIL} failed (out of 10)"
echo "================================================================"
if [[ "$FAIL" -eq 0 ]]; then
    echo " Phase 6 VERIFIED"
    exit 0
else
    echo " Phase 6 INCOMPLETE -- fix failures before marking complete."
    exit 1
fi
"""
