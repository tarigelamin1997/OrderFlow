# OrderFlow — Claude Code Rules

## Identity
You are the builder for the OrderFlow Mega DE Project. You execute approved plans. You do not make architecture decisions.

## Source of Truth
- **Execution plans live in Notion.** Every phase has a page under the Master Execution Plan. Read the full phase plan from Notion before writing any code.
- **Master Execution Plan:** https://www.notion.so/323b71eeacba811fa968f66c519caae8
- **Plan Documentation Standard:** https://www.notion.so/326b71eeacba81dd9596cc685c7eb928
- **Cross-Validation Index:** https://www.notion.so/327b71eeacba81babe75d1d8ff33e69e
- **GitHub repo:** https://github.com/tarigelamin1997/OrderFlow

## Project Configuration
- **`.claude/settings.json`** — Claude Code settings with schema validation and hooks. Do not modify.
- **PreToolUse hook active:** Any file write exceeding 800 lines is BLOCKED automatically. If you hit this, split the file into smaller modules. Do not disable the hook.

## Execution Rules

### Read Before You Build
- Read the FULL phase plan from Notion before writing any file.
- Read the Knowledge Transfer page for the current phase (child of the phase page) if it exists.
- Read the Cross-Audit findings for the group containing the current phase — amendments may have been applied to the plan after initial authoring. Use the Cross-Validation Index link above to find the correct group.

### Follow the Plan Exactly
- Every file you create must appear in the phase's Repo Structure section. No extra files. No missing files.
- Configuration blocks in the plan are COMPLETE. Copy them exactly. Do not abbreviate, summarize, refactor, or "improve" them.
- Follow the Apply Sequence in exact numbered order. Each step has WHY, WAIT FOR, and FAILURE MODE — respect all three.
- Do not skip steps. Do not reorder steps. Do not combine steps.

### Versions
- `versions.yaml` at repo root is the single source of truth for ALL component versions.
- Never hard-code a version in a Dockerfile, Helm values, Terraform file, requirements.txt, or pom.xml. Reference versions.yaml or use the exact version declared there.
- If you need a version number, check versions.yaml first.

### Secrets
- NEVER commit secrets, passwords, API keys, or credentials to the repo.
- Follow the Secret Injection Pattern table in Phase 1.
- K8s Secret manifests use placeholder values only. Actual values are injected via `kubectl create secret` commands.
- dbt profiles.yml uses `env_var()` exclusively.
- Debezium connector configs use `${PLACEHOLDER}` syntax.

### .gitignore
- .gitignore must exist before any other file is created.
- Check .gitignore covers any new file type before committing.

### Phase Boundaries — Do Not Cross
- Only create/modify files owned by the current phase.
- Never modify files from prior phases unless the plan explicitly says to (e.g., Airflow Dockerfile update in Phase 5).
- Never write to ClickHouse databases owned by other phases:
  - `bronze` = Phase 2
  - `silver` = Phase 3
  - `gold` streaming tables = Phase 3
  - `gold.*_batch` = Phase 4
  - `gold.pii_audit_log` = Phase 6
  - `gold.dag_run_log`, `gold.schema_drift_log` = Phase 7
  - `dbt_dev__gold` = Phase 5 (via dbt)
  - `dbt_staging__gold` = Phase 6 (via dbt --target staging)

### Verification
- After completing the Apply Sequence, run `make verify-phaseN`. ALL checks must pass.
- If any check fails, report: the check number, the exact error, and what you see in logs.
- Do not mark a phase complete until verify passes.

### Execution Log (Mandatory — write to Notion after each phase)
After completing a phase (verify passes), create a Notion page titled "Phase {N} — Execution Log" as a child of the phase's plan page. This is your audit trail. Structure:

**1. Execution Summary** (2-3 sentences: what was built, total time, final verify result)

**2. Deviations from Plan** (MOST IMPORTANT SECTION)
For each deviation:
- Step number from Apply Sequence
- What the plan said to do
- What you actually did and WHY
- Whether the deviation affects downstream phases

If zero deviations: write "None — executed exactly as planned."

**3. Errors Encountered**
For each error:
- Step number
- Error message (exact)
- Root cause
- Fix applied
- Whether the fix is plan-compatible or a deviation

If zero errors: write "None — all steps completed on first attempt."

**4. Files Created Checklist**
List every file from the Repo Structure section with a checkmark (created) or X (not created, with reason).

**5. Verify Results**
Each verify check number, pass/fail, and the actual output value.

**Rules for this log:**
- Do NOT log steps that went exactly as planned — just confirm them in a single line ("Steps 1-4: executed as planned").
- DO expand on anything that went differently, failed, or required a judgment call.
- This log is for Tarig to review. Write it for a human reader, not for another LLM.
- Create the Notion page AFTER verify passes, not during execution.
- After writing the execution log, update the phase plan page's Status line: change "🔲 Built" to "✅ Built" and "🔲 Verified" to "✅ Verified" using the Notion update tool. This is how Tarig tracks progress without opening each page.

### Error Handling
- If ANY step fails: STOP. Report the step number, the exact error, and relevant logs.
- Do not attempt workarounds or fixes without reporting first.
- Do not silently retry failed commands.
- Do not skip a failed step and continue to the next.

### Code Quality
- All code must be production-grade: idempotent, observable, documented with rationale.
- All SQL uses `CREATE TABLE IF NOT EXISTS` or `CREATE MATERIALIZED VIEW IF NOT EXISTS`.
- All bash scripts start with `set -euo pipefail`.
- All Python follows standard formatting. No unused imports. No bare excepts (except in telemetry where documented).

## Stack Versions (from versions.yaml)
```
kafka:                3.7.0      (Strimzi 0.40.0, KRaft mode)
schema_registry:      7.6.1
debezium:             2.7.0
clickhouse:           24.8 LTS
spark:                3.5.1
delta_lake:           3.1.0
airflow:              2.10.0
dbt_core:             1.8.0
dbt_clickhouse:       1.8.0
dbt_spark:            1.8.0
great_expectations:   0.18.0
dbt_expectations:     0.10.4
terraform:            1.7.5
marquez:              0.48.0
postgres:             15
mongodb:              6.0
hadoop_aws:           3.3.4
aws_java_sdk_bundle:  1.12.367
clickhouse_jdbc:      0.6.3
jinja2:               3.1.3
```

## Runtime Environment
- EC2 t3.2xlarge: 8 vCPU, 32GB RAM, eu-north-1
- Kind cluster: 1 control-plane + 2 workers
- 100GB EBS gp3
- All service access via SSH tunnel (no public NodePorts)

## Port Allocation (locked — do not add new ports)
```
PostgreSQL:          30432
MongoDB:             30017
Kafka:               30092
Schema Registry:     30081
Kafka Connect:       30083
ClickHouse HTTP:     30123
ClickHouse Native:   30900
MinIO S3 API:        30910
MinIO Console:       30901
Airflow UI:          30080
Grafana:             30300
Marquez API:         30500
Marquez UI:          30301
Spark UI:            30404
```

## What You Must Never Do
- Never make architecture decisions. If a choice is not covered in the plan, ask.
- Never run `dbt run --full-refresh` in any scheduled or automated context.
- Never write directly to `silver.*` or `gold.*` streaming tables from DAGs or scripts.
- Never cancel a running SparkApplication without confirming it is safe.
- Never create Grafana dashboards manually in the UI — all provisioned via code.
- Never hard-code ClickHouse credentials in dashboard JSON.
- Never expose NodePorts to the internet — SSH tunnel only.
