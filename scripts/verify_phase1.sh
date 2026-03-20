#!/usr/bin/env bash
# verify_phase1.sh — all 10 checks must pass before Phase 1 is marked complete.
# Run via: make verify-phase1
# Each check prints PASS or FAIL with the actual value observed.

set -euo pipefail

PASS=0
FAIL=0
FAILURES=()

check() {
  local number="$1"
  local description="$2"
  local result="$3"
  local expected="$4"

  if [[ "$result" == *"$expected"* ]]; then
    echo "  CHECK $number PASS — $description: $result"
    PASS=$((PASS + 1))
  else
    echo "  CHECK $number FAIL — $description"
    echo "           expected: $expected"
    echo "           got:      $result"
    FAIL=$((FAIL + 1))
    FAILURES+=("$number: $description")
  fi
}

echo "============================================================"
echo " Phase 1 Verification"
echo "============================================================"
echo ""

# CHECK 1: 3 nodes in Ready state
echo "Check 1: Kind cluster — 3 nodes Ready"
result=$(kubectl get nodes --no-headers 2>/dev/null | grep -c "Ready" || echo "0")
check 1 "Kind nodes Ready" "$result" "3"

# CHECK 2: All pods Running or Completed, zero CrashLoopBackOff
echo "Check 2: All pods Running/Completed, zero CrashLoopBackOff"
crash_count=$(kubectl get pods -A --no-headers 2>/dev/null | grep -c "CrashLoopBackOff" || true)
if [[ "$crash_count" == "0" ]]; then
  echo "  CHECK 2 PASS — No CrashLoopBackOff pods"
  PASS=$((PASS + 1))
else
  echo "  CHECK 2 FAIL — $crash_count pod(s) in CrashLoopBackOff"
  FAIL=$((FAIL + 1))
  FAILURES+=("2: CrashLoopBackOff pods ($crash_count)")
  kubectl get pods -A --no-headers | grep "CrashLoopBackOff" || true
fi

# CHECK 3: ClickHouse HTTP ping
echo "Check 3: ClickHouse HTTP ping — expects 'Ok.'"
result=$(curl -s --max-time 5 http://localhost:30123/ping 2>/dev/null || echo "UNREACHABLE")
check 3 "ClickHouse ping" "$result" "Ok."

# CHECK 4: Schema Registry — expects '[]' (zero subjects)
echo "Check 4: Schema Registry subjects — expects '[]'"
result=$(curl -s --max-time 5 http://localhost:30081/subjects 2>/dev/null || echo "UNREACHABLE")
check 4 "Schema Registry subjects" "$result" "[]"

# CHECK 5: Kafka topics — all 7 must be present
echo "Check 5: Kafka topics — 7 topics expected"
EXPECTED_TOPICS=(
  "orderflow.public.orders"
  "orderflow.public.users"
  "orderflow.public.restaurants"
  "orderflow.public.drivers"
  "mongo.foodtech.user_events"
  "mongo.foodtech.delivery_updates"
  "orderflow.public.orders.dlq"
)
TOPIC_LIST=$(kubectl exec -n kafka \
  $(kubectl get pod -n kafka -l strimzi.io/name=orderflow-kafka-kafka \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null) \
  -- bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list 2>/dev/null || echo "")

topic_ok=true
for topic in "${EXPECTED_TOPICS[@]}"; do
  if ! echo "$TOPIC_LIST" | grep -q "^$topic$"; then
    echo "  CHECK 5 FAIL — missing topic: $topic"
    topic_ok=false
    FAIL=$((FAIL + 1))
    FAILURES+=("5: missing topic $topic")
    break
  fi
done
if $topic_ok; then
  echo "  CHECK 5 PASS — all 7 Kafka topics present"
  PASS=$((PASS + 1))
fi

# CHECK 6: PostgreSQL users count = 5000
echo "Check 6: PostgreSQL users — expects 5000"
result=$(kubectl exec -n databases deployment/postgres -- \
  psql -U orderflow -d orderflow -t -c "SELECT COUNT(*) FROM users;" 2>/dev/null \
  | tr -d '[:space:]' || echo "0")
check 6 "PostgreSQL users count" "$result" "5000"

# CHECK 7: PostgreSQL wal_level = logical
echo "Check 7: PostgreSQL wal_level — expects 'logical'"
result=$(kubectl exec -n databases deployment/postgres -- \
  psql -U orderflow -d orderflow -t -c "SHOW wal_level;" 2>/dev/null \
  | tr -d '[:space:]' || echo "unknown")
check 7 "PostgreSQL wal_level" "$result" "logical"

# CHECK 8: MongoDB user_events count >= 29000
echo "Check 8: MongoDB user_events — expects ~30000 (>= 29000)"
result=$(kubectl exec -n databases deployment/mongodb -- \
  mongosh --quiet \
  "mongodb://localhost:27017/foodtech?directConnection=true" \
  --eval "db.user_events.countDocuments()" 2>/dev/null \
  | tail -1 || echo "0")
if [[ "$result" -ge 29000 ]] 2>/dev/null; then
  echo "  CHECK 8 PASS — MongoDB user_events count: $result"
  PASS=$((PASS + 1))
else
  echo "  CHECK 8 FAIL — MongoDB user_events count: $result (expected >= 29000)"
  FAIL=$((FAIL + 1))
  FAILURES+=("8: MongoDB user_events count too low ($result)")
fi

# CHECK 9: MinIO buckets exist
echo "Check 9: MinIO buckets — orderflow-raw, orderflow-silver, orderflow-checkpoints"
BUCKET_LIST=$(kubectl exec -n spark deployment/minio -- \
  sh -c "mc alias set local http://localhost:9000 orderflow orderflow_minio_pass 2>/dev/null && mc ls local" \
  2>/dev/null || echo "")
bucket_ok=true
for bucket in "orderflow-raw" "orderflow-silver" "orderflow-checkpoints"; do
  if ! echo "$BUCKET_LIST" | grep -q "$bucket"; then
    echo "  CHECK 9 FAIL — missing bucket: $bucket"
    bucket_ok=false
    FAIL=$((FAIL + 1))
    FAILURES+=("9: missing bucket $bucket")
    break
  fi
done
if $bucket_ok; then
  echo "  CHECK 9 PASS — all 3 MinIO buckets present"
  PASS=$((PASS + 1))
fi

# CHECK 10: Airflow health endpoint
echo "Check 10: Airflow health — expects '{\"status\": \"healthy\"}'"
result=$(curl -s --max-time 10 http://localhost:30080/health 2>/dev/null || echo "UNREACHABLE")
check 10 "Airflow health" "$result" "healthy"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo " Results: $PASS/10 passed, $FAIL/10 failed"
echo "============================================================"

if [[ $FAIL -gt 0 ]]; then
  echo ""
  echo "Failed checks:"
  for f in "${FAILURES[@]}"; do
    echo "  - $f"
  done
  echo ""
  echo "Phase 1 INCOMPLETE — fix failures before proceeding to Phase 2"
  exit 1
else
  echo ""
  echo "Phase 1 COMPLETE — all 10 checks passed"
  exit 0
fi
