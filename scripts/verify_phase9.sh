#!/bin/bash
set -euo pipefail

PASS=0
FAIL=0
TOTAL=12

check() {
    local num=$1 desc="$2" result="$3" expected="$4"
    if [ "$result" = "PASS" ]; then
        echo "  CHECK $num PASS — $desc"
        PASS=$((PASS+1))
    else
        echo "  CHECK $num FAIL — $desc (expected: $expected, got: $result)"
        FAIL=$((FAIL+1))
    fi
}

echo "============================================================"
echo " Phase 9 Verification"
echo "============================================================"
echo ""

# Check 1: Factory generator exists
echo "Check 1: Factory generator exists"
if python3 factory/pipeline_factory.py --help > /dev/null 2>&1; then
    check 1 "Factory generator" "PASS" "exits 0"
else
    check 1 "Factory generator" "FAIL" "exits 0"
fi

# Check 2: All 10 templates present
echo "Check 2: All 10 templates present"
TC=$(ls factory/templates/*.j2 2>/dev/null | wc -l)
if [ "$TC" -ge 10 ]; then
    check 2 "Templates: $TC" "PASS" ">=10"
else
    check 2 "Templates: $TC" "$TC" ">=10"
fi

# Check 3: Unit tests pass
echo "Check 3: Unit tests pass"
if python3 -m pytest factory/tests/ -q --tb=short > /dev/null 2>&1; then
    check 3 "Unit tests" "PASS" "pass"
else
    check 3 "Unit tests" "FAIL" "pass"
fi

# Check 4: Payments demo artifacts generated (10 files)
echo "Check 4: Payments demo artifacts generated"
PC=$(ls factory/output/payments/ 2>/dev/null | wc -l)
if [ "$PC" -ge 10 ]; then
    check 4 "Payments artifacts: $PC" "PASS" ">=10"
else
    check 4 "Payments artifacts: $PC" "$PC" ">=10"
fi

# Check 5: Payments Debezium connector registered
echo "Check 5: Payments connector registered"
if kubectl get kafkaconnector orderflow-postgres-source-payments -n kafka > /dev/null 2>&1; then
    check 5 "Payments connector" "PASS" "registered"
else
    check 5 "Payments connector" "FAIL" "registered"
fi

# Check 6: Payments Bronze table has data
echo "Check 6: Payments Bronze data"
BC=$(clickhouse-client --host localhost --port 30900 -q "SELECT count() FROM bronze.payments_raw" 2>/dev/null || echo "0")
if [ "$BC" -gt 0 ]; then
    check 6 "Bronze payments: $BC" "PASS" ">0"
else
    check 6 "Bronze payments: $BC" "$BC" ">0"
fi

# Check 7: Payments Silver table has data
echo "Check 7: Payments Silver data"
SC=$(clickhouse-client --host localhost --port 30900 -q "SELECT count() FROM silver.payments" 2>/dev/null || echo "0")
if [ "$SC" -gt 0 ]; then
    check 7 "Silver payments: $SC" "PASS" ">0"
else
    check 7 "Silver payments: $SC" "$SC" ">0"
fi

# Check 8: PII column hashed (card_last_four_hash is SHA-256 hex)
echo "Check 8: PII column hashed"
HASH=$(clickhouse-client --host localhost --port 30900 -q "SELECT card_last_four_hash FROM silver.payments WHERE card_last_four_hash != '' LIMIT 1" 2>/dev/null || echo "")
if echo "$HASH" | grep -qE '^[a-f0-9]{64}$'; then
    check 8 "PII hash: ${HASH:0:16}..." "PASS" "^[a-f0-9]{64}$"
else
    check 8 "PII hash: $HASH" "$HASH" "^[a-f0-9]{64}$"
fi

# Check 9: dbt staging model works
echo "Check 9: dbt staging model"
AIRFLOW_POD=$(kubectl get pod -n airflow -l app=airflow -o jsonpath='{.items[0].metadata.name}')
if kubectl exec -n airflow $AIRFLOW_POD -c airflow-webserver -- bash -c "cd /opt/airflow/dbt/orderflow_clickhouse && dbt run --select stg_payments --target dev --profiles-dir ." > /dev/null 2>&1; then
    check 9 "dbt stg_payments" "PASS" "pass"
else
    check 9 "dbt stg_payments" "FAIL" "pass"
fi

# Check 10: Airflow DAG visible
echo "Check 10: Airflow DAG visible"
if kubectl exec -n airflow $AIRFLOW_POD -c airflow-webserver -- airflow dags list 2>/dev/null | grep -q payments; then
    check 10 "Payments DAG" "PASS" "visible"
else
    check 10 "Payments DAG" "FAIL" "visible"
fi

# Check 11: factory/README.md exists
echo "Check 11: Factory README"
if [ -f factory/README.md ]; then
    check 11 "factory/README.md" "PASS" "exists"
else
    check 11 "factory/README.md" "FAIL" "exists"
fi

# Check 12: Existing pipelines untouched
echo "Check 12: Existing pipelines untouched"
OC=$(clickhouse-client --host localhost --port 30900 -q "SELECT count() FROM silver.orders FINAL" 2>/dev/null || echo "0")
if [ "$OC" -ge 100000 ]; then
    check 12 "Silver orders: $OC" "PASS" ">=100000"
else
    check 12 "Silver orders: $OC" "$OC" ">=100000"
fi

echo ""
echo "============================================================"
echo " Results: $PASS/$TOTAL passed, $FAIL/$TOTAL failed"
echo "============================================================"

if [ $PASS -eq $TOTAL ]; then
    echo ""
    echo "Phase 9 COMPLETE — all $TOTAL checks passed"
    exit 0
else
    echo ""
    echo "Phase 9 INCOMPLETE — $FAIL checks failed"
    exit 2
fi
