"""verify_phase7.sh content -- 12 checks for Phase 7."""


def verify_phase7_sh() -> str:
    return """\
#!/usr/bin/env bash
# scripts/verify_phase7.sh -- Phase 7 verification (12 checks).
# Requires: clickhouse-client (port 30900), kubectl, curl (Grafana :30300,
#           Marquez :30500, Airflow :30080).
set -euo pipefail

PASS=0
FAIL=0
CH="clickhouse-client --host localhost --port 30900 --query"
GRAFANA_URL="http://localhost:30300"
GRAFANA_CREDS="admin:orderflow"
MARQUEZ_URL="http://localhost:30500"
AIRFLOW_API="http://localhost:30080/api/v1"
AIRFLOW_USER="${AIRFLOW_USER:-admin}"
AIRFLOW_PASS="${AIRFLOW_PASS:-admin}"

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
echo " OrderFlow Phase 7 -- Verification"
echo "================================================================"

# Check 1: gold.dag_run_log table exists
echo ""
echo "Check 1: gold.dag_run_log table exists in ClickHouse"
DRL=$($CH "SELECT count() FROM system.tables
    WHERE database = 'gold' AND name = 'dag_run_log'" 2>/dev/null || echo "0")
if [[ "$DRL" -eq 1 ]]; then
    check 1 "gold.dag_run_log table exists" "pass"
else
    check 1 "gold.dag_run_log table exists" \
        "fail: table not found -- run clickhouse/gold/13_dag_run_log.sql"
fi

# Check 2: gold.schema_drift_log table exists
echo ""
echo "Check 2: gold.schema_drift_log table exists in ClickHouse"
SDL=$($CH "SELECT count() FROM system.tables
    WHERE database = 'gold' AND name = 'schema_drift_log'" 2>/dev/null || echo "0")
if [[ "$SDL" -eq 1 ]]; then
    check 2 "gold.schema_drift_log table exists" "pass"
else
    check 2 "gold.schema_drift_log table exists" \
        "fail: table not found -- run clickhouse/gold/14_schema_drift_log.sql"
fi

# Check 3: Grafana is reachable
echo ""
echo "Check 3: Grafana API reachable at :30300"
GF_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -u "${GRAFANA_CREDS}" "${GRAFANA_URL}/api/health" 2>/dev/null || echo "000")
if [[ "$GF_STATUS" == "200" ]]; then
    check 3 "Grafana API reachable" "pass"
else
    check 3 "Grafana API reachable" \
        "fail: HTTP ${GF_STATUS} -- is Grafana running and SSH tunnel active?"
fi

# Check 4: ClickHouse datasource present in Grafana
echo ""
echo "Check 4: ClickHouse datasource UID PDEE91DDB90597936 present in Grafana"
DS_COUNT=$(curl -s -u "${GRAFANA_CREDS}" \
    "${GRAFANA_URL}/api/datasources" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    ds = json.load(sys.stdin)
    uids = [d.get('uid','') for d in ds]
    print('1' if 'PDEE91DDB90597936' in uids else '0')
except Exception:
    print('0')
" 2>/dev/null || echo "0")
if [[ "$DS_COUNT" == "1" ]]; then
    check 4 "ClickHouse datasource UID PDEE91DDB90597936 found" "pass"
else
    check 4 "ClickHouse datasource UID PDEE91DDB90597936 found" \
        "fail: datasource not found in Grafana -- check Phase 3 datasource provisioning"
fi

# Check 5: All 5 dashboards present in Grafana
echo ""
echo "Check 5: All 5 OrderFlow dashboards present in Grafana"
DB_LIST=$(curl -s -u "${GRAFANA_CREDS}" \
    "${GRAFANA_URL}/api/search?type=dash-db" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    items = json.load(sys.stdin)
    uids = [d.get('uid','') for d in items]
    expected = [
        'of-pipeline-health', 'of-data-quality',
        'of-clickhouse-ops', 'of-business-metrics', 'of-finops-resources'
    ]
    missing = [u for u in expected if u not in uids]
    print('OK' if not missing else 'MISSING:' + ','.join(missing))
except Exception as e:
    print('ERROR:' + str(e))
" 2>/dev/null || echo "ERROR:curl failed")
if [[ "$DB_LIST" == "OK" ]]; then
    check 5 "All 5 OrderFlow dashboards present in Grafana" "pass"
else
    check 5 "All 5 OrderFlow dashboards present in Grafana" \
        "fail: ${DB_LIST} -- apply grafana-volume-patch.yaml and restart Grafana"
fi

# Check 6: Grafana alert rules present
echo ""
echo "Check 6: Grafana alert rules present (at least 1)"
ALERT_COUNT=$(curl -s -u "${GRAFANA_CREDS}" \
    "${GRAFANA_URL}/api/v1/provisioning/alert-rules" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    rules = json.load(sys.stdin)
    print(str(len(rules)))
except Exception:
    print('0')
" 2>/dev/null || echo "0")
if [[ "$ALERT_COUNT" -ge 1 ]]; then
    check 6 "Grafana alert rules present (found ${ALERT_COUNT})" "pass"
else
    check 6 "Grafana alert rules present" \
        "fail: no alert rules found -- check alerting ConfigMap and Grafana restart"
fi

# Check 7: Telemetry plugin loaded in Airflow
echo ""
echo "Check 7: dag_telemetry_listener plugin loaded in Airflow"
PLUGIN_CHECK=$(kubectl exec -n airflow airflow-0 -- \
    airflow plugins list 2>/dev/null \
    | grep -c "orderflow_telemetry_plugin" || echo "0")
if [[ "$PLUGIN_CHECK" -ge 1 ]]; then
    check 7 "orderflow_telemetry_plugin loaded in Airflow" "pass"
else
    check 7 "orderflow_telemetry_plugin loaded in Airflow" \
        "fail: plugin not found -- check airflow-plugins ConfigMap and pod restart"
fi

# Check 8: OpenLineage env vars set in Airflow pod
echo ""
echo "Check 8: OpenLineage env vars set in Airflow statefulset pod"
OL_ENV=$(kubectl exec -n airflow airflow-0 -- \
    env 2>/dev/null | grep "AIRFLOW__OPENLINEAGE__DISABLED" || echo "")
if echo "$OL_ENV" | grep -q "false"; then
    check 8 "AIRFLOW__OPENLINEAGE__DISABLED=false set in Airflow pod" "pass"
else
    check 8 "AIRFLOW__OPENLINEAGE__DISABLED=false set in Airflow pod" \
        "fail: env var not found -- apply airflow-openlineage-patch.yaml"
fi

# Check 9: Marquez API reachable
echo ""
echo "Check 9: Marquez API reachable at :30500"
MQ_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    "${MARQUEZ_URL}/api/v1/namespaces" 2>/dev/null || echo "000")
if [[ "$MQ_STATUS" == "200" ]]; then
    check 9 "Marquez API reachable" "pass"
else
    check 9 "Marquez API reachable" \
        "fail: HTTP ${MQ_STATUS} -- is Marquez running and SSH tunnel active?"
fi

# Check 10: Marquez orderflow namespace exists
echo ""
echo "Check 10: Marquez 'orderflow' namespace exists"
MQ_NS=$(curl -s "${MARQUEZ_URL}/api/v1/namespaces" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    names = [n.get('name','') for n in data.get('namespaces', [])]
    print('1' if 'orderflow' in names else '0')
except Exception:
    print('0')
" 2>/dev/null || echo "0")
if [[ "$MQ_NS" == "1" ]]; then
    check 10 "Marquez 'orderflow' namespace exists" "pass"
else
    check 10 "Marquez 'orderflow' namespace exists" \
        "fail: namespace not found -- trigger a DAG run to push lineage events"
fi

# Check 11: gold.dag_run_log has data
echo ""
echo "Check 11: gold.dag_run_log has at least 1 row"
DRL_ROWS=$($CH "SELECT count() FROM gold.dag_run_log" 2>/dev/null || echo "0")
if [[ "$DRL_ROWS" -ge 1 ]]; then
    check 11 "gold.dag_run_log has ${DRL_ROWS} row(s)" "pass"
else
    check 11 "gold.dag_run_log has at least 1 row" \
        "fail: no rows -- trigger a DAG and confirm the telemetry plugin is active"
fi
# Check 12: dbt_dev__gold mart tables reachable
echo ""
echo "Check 12: dbt_dev__gold.mart_orders accessible"
MART_CHECK=$($CH "SELECT count() FROM system.tables
    WHERE database = 'dbt_dev__gold' AND name = 'mart_orders'" 2>/dev/null || echo "0")
if [[ "$MART_CHECK" -ge 1 ]]; then
    check 12 "dbt_dev__gold.mart_orders table exists" "pass"
else
    check 12 "dbt_dev__gold.mart_orders table exists" \
        "fail: table not found -- run orderflow_dbt_clickhouse DAG (Phase 6)"
fi
# Summary
echo ""
echo "================================================================"
echo " Results: ${PASS} passed, ${FAIL} failed (out of 12)"
echo "================================================================"
if [[ "$FAIL" -eq 0 ]]; then
    echo " Phase 7 VERIFIED"
    exit 0
else
    echo " Phase 7 INCOMPLETE -- fix failures before marking complete."
    exit 1
fi
"""
