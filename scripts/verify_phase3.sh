#!/bin/bash
set -euo pipefail

PASS=0
FAIL=0
TOTAL=8
CH="clickhouse-client --host localhost --port 30900 --user default"

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
echo " Phase 3 Verification"
echo "============================================================"
echo ""

# Check 1: Silver orders populated >= 50000
echo "Check 1: Silver orders count — expects >= 50000"
ORDERS=$($CH -q "SELECT count() FROM silver.orders" 2>/dev/null || echo "0")
if [ "$ORDERS" -ge 50000 ]; then
    check 1 "Silver orders: $ORDERS" "PASS" ">=50000"
else
    check 1 "Silver orders: $ORDERS" "$ORDERS" ">=50000"
fi

# Check 2: Silver users populated >= 5000
echo "Check 2: Silver users count — expects >= 5000"
USERS=$($CH -q "SELECT count() FROM silver.users" 2>/dev/null || echo "0")
if [ "$USERS" -ge 5000 ]; then
    check 2 "Silver users: $USERS" "PASS" ">=5000"
else
    check 2 "Silver users: $USERS" "$USERS" ">=5000"
fi

# Check 3: Typing correct — total_amount is Decimal(10,2)
echo "Check 3: Typing — total_amount should be Decimal(10, 2)"
TYPE=$($CH -q "SELECT toTypeName(total_amount) FROM silver.orders LIMIT 1" 2>/dev/null || echo "UNKNOWN")
if [ "$TYPE" = "Decimal(10, 2)" ]; then
    check 3 "total_amount type: $TYPE" "PASS" "Decimal(10, 2)"
else
    check 3 "total_amount type: $TYPE" "$TYPE" "Decimal(10, 2)"
fi

# Check 4: Timestamp correct — created_at_dt is DateTime
echo "Check 4: Typing — created_at_dt should be DateTime"
TSTYPE=$($CH -q "SELECT toTypeName(created_at_dt) FROM silver.orders LIMIT 1" 2>/dev/null || echo "UNKNOWN")
if [ "$TSTYPE" = "DateTime" ]; then
    check 4 "created_at_dt type: $TSTYPE" "PASS" "DateTime"
else
    check 4 "created_at_dt type: $TSTYPE" "$TSTYPE" "DateTime"
fi

# Check 5: ReplacingMergeTree deduplicated — FINAL count ~ 50000
echo "Check 5: ReplacingMergeTree FINAL deduplicated — expects ~50000"
FINAL=$($CH -q "SELECT count() FROM silver.orders FINAL" 2>/dev/null || echo "0")
if [ "$FINAL" -ge 49000 ] && [ "$FINAL" -le 55000 ]; then
    check 5 "Silver orders FINAL: $FINAL" "PASS" "~50000"
else
    check 5 "Silver orders FINAL: $FINAL" "$FINAL" "~50000"
fi

# Check 6: Gold revenue populated > 0
echo "Check 6: Gold restaurant_revenue_daily count — expects > 0"
REVENUE=$($CH -q "SELECT count() FROM gold.restaurant_revenue_daily" 2>/dev/null || echo "0")
if [ "$REVENUE" -gt 0 ]; then
    check 6 "Gold revenue rows: $REVENUE" "PASS" ">0"
else
    check 6 "Gold revenue rows: $REVENUE" "$REVENUE" ">0"
fi

# Check 7: AggregatingMergeTree readable
echo "Check 7: AggregatingMergeTree sumMerge — expects numeric value"
AGG=$($CH -q "SELECT sumMerge(total_revenue) FROM gold.order_metrics_by_status" 2>/dev/null || echo "ERROR")
if [ "$AGG" != "ERROR" ] && [ "$AGG" != "" ]; then
    check 7 "sumMerge result: $AGG" "PASS" "numeric"
else
    check 7 "sumMerge result: $AGG" "$AGG" "numeric"
fi

# Check 8: Projections materialised
echo "Check 8: Projections done — expects 0 pending mutations"
MUTATIONS=$($CH -q "SELECT count() FROM system.mutations WHERE table='orders' AND database='silver' AND NOT is_done" 2>/dev/null || echo "1")
if [ "$MUTATIONS" = "0" ]; then
    check 8 "Pending mutations: $MUTATIONS" "PASS" "0"
else
    check 8 "Pending mutations: $MUTATIONS" "$MUTATIONS" "0"
fi

echo ""
echo "============================================================"
echo " Results: $PASS/$TOTAL passed, $FAIL/$TOTAL failed"
echo "============================================================"

if [ $PASS -eq $TOTAL ]; then
    echo ""
    echo "Phase 3 COMPLETE — all $TOTAL checks passed"
else
    echo ""
    echo "Phase 3 INCOMPLETE — $FAIL checks failed"
    exit 1
fi
