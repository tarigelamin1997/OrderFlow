"""verify_phase4.sh content for Phase 4."""


def get() -> str:
    return """\
#!/usr/bin/env bash
# spark/scripts/verify_phase4.sh -- Phase 4 verification (10 checks)
# Run from the EC2 host after all SparkApplications have completed.
# Requires: mc (MinIO client), clickhouse-client, kubectl
set -euo pipefail

PASS=0
FAIL=0

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
echo " OrderFlow Phase 4 -- Verification"
echo "================================================================"

# Check 1: Spark image loaded in Kind ─────────────────────────────────────────
echo ""
echo "Check 1: Spark image loaded in Kind cluster"
if docker exec orderflow-control-plane crictl images 2>/dev/null \\
        | grep -q "orderflow/spark-orderflow.*3.5.1-delta3"; then
    check 1 "Spark image present in Kind" "pass"
else
    check 1 "Spark image present in Kind" \\
        "fail: image orderflow/spark-orderflow:3.5.1-delta3 not found"
fi

# Check 2: Delta Silver orders files ──────────────────────────────────────────
echo ""
echo "Check 2: Silver orders Delta files in MinIO"
ORDER_FILES=$(mc ls minio/orderflow-silver/delta/orders/ 2>/dev/null | wc -l || echo "0")
if [[ "$ORDER_FILES" -gt 0 ]]; then
    check 2 "Silver orders Delta files exist (count=${ORDER_FILES})" "pass"
else
    check 2 "Silver orders Delta files" \\
        "fail: no files at minio/orderflow-silver/delta/orders/"
fi

# Check 3: is_deleted column ──────────────────────────────────────────────────
echo ""
echo "Check 3: is_deleted column in Silver orders Delta schema"
LOG_COUNT=$(mc ls minio/orderflow-silver/delta/orders/_delta_log/ 2>/dev/null | wc -l || echo "0")
if [[ "$LOG_COUNT" -gt 0 ]]; then
    COMMIT=$(mc cat "minio/orderflow-silver/delta/orders/_delta_log/00000000000000000000.json" 2>/dev/null || echo "")
    if echo "$COMMIT" | grep -q '"name":"is_deleted"'; then
        check 3 "is_deleted column in orders Delta schema" "pass"
    else
        check 3 "is_deleted column in orders Delta schema" \\
            "fail: is_deleted not found in Delta commit log"
    fi
else
    check 3 "is_deleted column in orders Delta schema" "fail: Delta log not found"
fi

# Check 4: total_amount field ─────────────────────────────────────────────────
echo ""
echo "Check 4: total_amount field in Silver orders Delta schema"
COMMIT=$(mc cat "minio/orderflow-silver/delta/orders/_delta_log/00000000000000000000.json" 2>/dev/null || echo "")
if echo "$COMMIT" | grep -q '"name":"total_amount"'; then
    check 4 "total_amount field in orders Delta schema" "pass"
else
    check 4 "total_amount field in orders Delta schema" \\
        "fail: total_amount not found in Delta commit log"
fi

# Check 5: user_events Silver files ───────────────────────────────────────────
echo ""
echo "Check 5: user_events Silver Delta files in MinIO"
UE=$(mc ls minio/orderflow-silver/delta/user_events/ 2>/dev/null | wc -l || echo "0")
if [[ "$UE" -gt 0 ]]; then
    check 5 "user_events Silver Delta files exist (count=${UE})" "pass"
else
    check 5 "user_events Silver Delta files" \\
        "fail: no files at minio/orderflow-silver/delta/user_events/"
fi

# Check 6: delivery_updates lat/lng ───────────────────────────────────────────
echo ""
echo "Check 6: delivery_updates lat/lng fields in Delta schema"
DU=$(mc ls minio/orderflow-silver/delta/delivery_updates/ 2>/dev/null | wc -l || echo "0")
if [[ "$DU" -gt 0 ]]; then
    DU_S=$(mc cat "minio/orderflow-silver/delta/delivery_updates/_delta_log/00000000000000000000.json" 2>/dev/null || echo "")
    if echo "$DU_S" | grep -q '"name":"location_lat"' \\
            && echo "$DU_S" | grep -q '"name":"location_lng"'; then
        check 6 "delivery_updates lat/lng fields present" "pass"
    else
        check 6 "delivery_updates lat/lng fields" \\
            "fail: location_lat or location_lng missing from schema"
    fi
else
    check 6 "delivery_updates lat/lng fields" \\
        "fail: no files at minio/orderflow-silver/delta/delivery_updates/"
fi

# Check 7: All 5 feature tables populated ─────────────────────────────────────
echo ""
echo "Check 7: All 5 feature Delta tables populated in MinIO"
FEATURES=(demand_by_zone driver_efficiency restaurant_performance
          user_cohort_behavior peak_hour_demand)
ALL_FEATURES_OK=true
for feat in "${FEATURES[@]}"; do
    CNT=$(mc ls "minio/orderflow-silver/delta/features/${feat}/" 2>/dev/null | wc -l || echo "0")
    if [[ "$CNT" -eq 0 ]]; then
        ALL_FEATURES_OK=false
        echo "    MISSING feature: ${feat}"
    else
        echo "    OK feature: ${feat} (${CNT} files)"
    fi
done
if $ALL_FEATURES_OK; then
    check 7 "All 5 feature Delta tables populated" "pass"
else
    check 7 "All 5 feature Delta tables populated" \\
        "fail: one or more feature tables missing"
fi

# Check 8: ClickHouse Gold batch tables populated ─────────────────────────────
echo ""
echo "Check 8: ClickHouse Gold batch tables populated"
CH="clickhouse-client --host localhost --port 30900 --query"
ALL_CH_OK=true
for tbl in restaurant_revenue_batch driver_features_batch demand_zone_batch; do
    N=$($CH "SELECT count() FROM gold.${tbl}" 2>/dev/null || echo "0")
    if [[ "$N" -gt 0 ]]; then
        echo "    OK gold.${tbl}: ${N} rows"
    else
        ALL_CH_OK=false
        echo "    FAIL gold.${tbl}: 0 rows or error"
    fi
done
if $ALL_CH_OK; then
    check 8 "ClickHouse Gold batch tables populated" "pass"
else
    check 8 "ClickHouse Gold batch tables populated" \\
        "fail: one or more tables empty"
fi

# Check 9: Phase 3 Gold tables untouched ──────────────────────────────────────
echo ""
echo "Check 9: Phase 3 Gold streaming tables still exist"
P3_OK=true
for tbl in orders_enriched driver_location_enriched; do
    E=$($CH "EXISTS TABLE gold.${tbl}" 2>/dev/null || echo "0")
    if [[ "$E" == "1" ]]; then
        echo "    OK gold.${tbl} exists"
    else
        P3_OK=false
        echo "    MISSING gold.${tbl}"
    fi
done
if $P3_OK; then
    check 9 "Phase 3 Gold streaming tables exist" "pass"
else
    check 9 "Phase 3 Gold streaming tables exist" \\
        "fail: Phase 3 tables missing -- possible cross-phase pollution"
fi

# Check 10: All 3 SparkApplications Completed ─────────────────────────────────
echo ""
echo "Check 10: All 3 SparkApplications in Completed state"
APPS=(silver-ingestion feature-engineering gold-writer)
ALL_DONE=true
for app in "${APPS[@]}"; do
    ST=$(kubectl get sparkapplication "$app" -n spark \\
         -o jsonpath='{.status.applicationState.state}' 2>/dev/null || echo "NOT_FOUND")
    if [[ "$ST" == "COMPLETED" ]]; then
        echo "    OK ${app}: ${ST}"
    else
        ALL_DONE=false
        echo "    FAIL ${app}: ${ST}"
    fi
done
if $ALL_DONE; then
    check 10 "All 3 SparkApplications Completed" "pass"
else
    check 10 "All 3 SparkApplications Completed" \\
        "fail: one or more not COMPLETED"
fi

# Summary ─────────────────────────────────────────────────────────────────────
echo ""
echo "================================================================"
echo " Results: ${PASS} passed, ${FAIL} failed (out of 10)"
echo "================================================================"
if [[ "$FAIL" -eq 0 ]]; then
    echo " Phase 4 VERIFIED"
    exit 0
else
    echo " Phase 4 INCOMPLETE -- fix failures before marking complete."
    exit 1
fi
"""
