#!/bin/bash
set -euo pipefail
echo "Scanning for potential secrets in repo..."
grep -rn --include="*.py" --include="*.yaml" --include="*.yml" --include="*.sh" \
  -E "(password|secret|access.key|api.key)\s*[:=]" . \
  --exclude-dir=".git" --exclude-dir="node_modules" || true
echo "Scan complete. Review any matches above."
