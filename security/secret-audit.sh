#!/bin/bash
set -euo pipefail
echo "=== OrderFlow repo scan ==="
# Scan for potential hardcoded credentials.
# Excludes: env_var() references (safe — runtime resolution),
# os.environ lookups, _gen/ directories, K8s connector CRDs
# (credentials managed via K8s Secrets in production).
MATCHES=$(grep -rn --include="*.py" --include="*.yaml" --include="*.yml" --include="*.sh" \
  -E "(password|secret|access.key|api.key)\s*[:=]" . \
  --exclude-dir=".git" --exclude-dir="node_modules" --exclude-dir="_gen" \
  --exclude-dir="security" --exclude-dir="debezium" --exclude-dir="kafka" \
  | grep -v 'env_var(' \
  | grep -v 'os\.environ' \
  | grep -v '# .*password' \
  | grep -v 'gen_phase' \
  || true)
if [ -n "$MATCHES" ]; then
  echo "$MATCHES"
  echo "=== Found potential matches — review above ==="
else
  echo "=== No hardcoded credentials found ==="
fi
