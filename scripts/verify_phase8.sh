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
echo " Phase 8 Verification"
echo "============================================================"
echo ""

# Check 1: README exists with framing sentence
echo "Check 1: README exists with framing sentence"
RC=$(grep -c "OrderFlow is not a pipeline project" docs/README.md 2>/dev/null || echo "0")
if [ "$RC" -ge 1 ]; then
    check 1 "README framing sentence" "PASS" ">=1"
else
    check 1 "README framing sentence" "$RC" ">=1"
fi

# Check 2: Architecture doc exists
echo "Check 2: Architecture doc exists"
if [ -f docs/ARCHITECTURE.md ]; then
    check 2 "ARCHITECTURE.md exists" "PASS" "exists"
else
    check 2 "ARCHITECTURE.md exists" "missing" "exists"
fi

# Check 3: Runbook exists
echo "Check 3: Runbook exists"
if [ -f docs/RUNBOOK.md ]; then
    check 3 "RUNBOOK.md exists" "PASS" "exists"
else
    check 3 "RUNBOOK.md exists" "missing" "exists"
fi

# Check 4: Bug log has 15+ entries
echo "Check 4: Bug log has 15+ entries"
BC=$(grep -c "^### BUG-" docs/BUGLOG.md 2>/dev/null || echo "0")
if [ "$BC" -ge 15 ]; then
    check 4 "BUGLOG entries: $BC" "PASS" ">=15"
else
    check 4 "BUGLOG entries: $BC" "$BC" ">=15"
fi

# Check 5: SLO report exists with 6 SLOs
echo "Check 5: SLO report exists with 6 SLOs"
SC=$(grep -ci "SLO" docs/SLO_REPORT.md 2>/dev/null || echo "0")
if [ "$SC" -ge 6 ]; then
    check 5 "SLO references: $SC" "PASS" ">=6"
else
    check 5 "SLO references: $SC" "$SC" ">=6"
fi

# Check 6: Cloud portability docs exist
echo "Check 6: Cloud portability docs exist"
if [ -f cloud/aws/README.md ] && [ -f cloud/aws/eks-cluster.tf ]; then
    check 6 "Cloud docs exist" "PASS" "exists"
else
    check 6 "Cloud docs exist" "missing" "exists"
fi

# Check 7: Terraform env files exist (3)
echo "Check 7: Terraform env files (3)"
TF=$(ls terraform/environments/*.tfvars 2>/dev/null | wc -l)
if [ "$TF" -ge 3 ]; then
    check 7 "tfvars files: $TF" "PASS" ">=3"
else
    check 7 "tfvars files: $TF" "$TF" ">=3"
fi

# Check 8: ggshield config exists
echo "Check 8: ggshield pre-commit config"
if [ -f .pre-commit-config.yaml ]; then
    check 8 ".pre-commit-config.yaml exists" "PASS" "exists"
else
    check 8 ".pre-commit-config.yaml exists" "missing" "exists"
fi

# Check 9: Stress test results present (12 waves)
echo "Check 9: Stress test results (12 waves)"
WC=$(ls stress/results/wave_*.json 2>/dev/null | wc -l)
if [ "$WC" -ge 12 ]; then
    check 9 "Wave results: $WC" "PASS" ">=12"
else
    check 9 "Wave results: $WC" "$WC" ">=12"
fi

# Check 10: ClickHouse order count >= 100K
echo "Check 10: ClickHouse orders >= 100K"
OC=$(clickhouse-client --host localhost --port 30900 --query "SELECT count() FROM silver.orders FINAL" 2>/dev/null || echo "0")
if [ "$OC" -ge 100000 ]; then
    check 10 "Silver orders: $OC" "PASS" ">=100000"
else
    check 10 "Silver orders: $OC" "$OC" ">=100000"
fi

# Check 11: Phase 7 still passes
echo "Check 11: Phase 7 verify still passes"
if make verify-phase7 > /dev/null 2>&1; then
    check 11 "Phase 7 verify" "PASS" "pass"
else
    check 11 "Phase 7 verify" "FAIL" "pass"
fi

# Check 12: Secret audit clean
echo "Check 12: Secret audit clean"
SA=$(bash security/secret-audit.sh 2>&1 | grep -cE "password\s*[:=]|secret\s*[:=]" || true)
SA=${SA:-0}
if [ "$SA" -eq 0 ]; then
    check 12 "Secret audit: clean" "PASS" "0 secrets"
else
    check 12 "Secret audit: $SA matches" "$SA" "0 secrets"
fi

echo ""
echo "============================================================"
echo " Results: $PASS/$TOTAL passed, $FAIL/$TOTAL failed"
echo "============================================================"

if [ $PASS -eq $TOTAL ]; then
    echo ""
    echo "Phase 8 COMPLETE — all $TOTAL checks passed"
    exit 0
else
    echo ""
    echo "Phase 8 INCOMPLETE — $FAIL checks failed"
    exit 2
fi
