# OrderFlow Bug Log

Bugs encountered and resolved during Phases 1-7 of the OrderFlow project.
Each entry captures the symptom, root cause, fix, and lesson learned.

---

## Phase 1: Infrastructure & Terraform

### BUG-1: Ubuntu dash vs bash breaks pipefail
**Phase:** 1
**Symptom:** `/bin/sh: Illegal option -o pipefail` on Terraform local-exec provisioners.
**Root cause:** Ubuntu `/bin/sh` is dash, not bash. `set -euo pipefail` is a bash-ism that dash does not support.
**Fix:** Added `interpreter = ["/bin/bash", "-c"]` to all 12 local-exec provisioners.
**Lesson:** Never assume `/bin/sh` is bash. Always specify the interpreter explicitly.

### BUG-2: Strimzi operator crashes on Kubernetes 1.35
**Phase:** 1
**Symptom:** Strimzi operator pod in CrashLoopBackOff immediately after deployment.
**Root cause:** K8s v1.35 adds `emulationMajor` field to version API. Strimzi 0.40.0's fabric8 client 6.10.0 cannot parse this field.
**Fix:** Pinned Kind cluster to K8s v1.31.4 (latest compatible with Strimzi 0.40.0).
**Lesson:** Kubernetes version upgrades break operators. Pin K8s versions and test operator compatibility before upgrading.

### BUG-3: Schema Registry CrashLoopBackOff from K8s service port injection
**Phase:** 1
**Symptom:** Schema Registry pod CrashLoopBackOff with port binding error.
**Root cause:** K8s automatically injects `SCHEMA_REGISTRY_PORT=tcp://10.96.x.x:8081` from the Service object. Confluent Schema Registry reads this env var expecting a port number, gets a URL, and crashes.
**Fix:** Added `enable_service_links = false` to the pod spec.
**Lesson:** Kubernetes service link injection can collide with application env vars. Disable it for apps that use common env var names.

### BUG-17: PostgreSQL refuses to start when command overrides entrypoint
**Phase:** 1
**Symptom:** PostgreSQL pod exits immediately with permissions error.
**Root cause:** Using `command` in the K8s container spec bypasses `docker-entrypoint.sh`, which handles data directory initialization and permission setup. Without the entrypoint, PostgreSQL tries to start as root and refuses.
**Fix:** Changed from `command` to `args` (preserves the image's ENTRYPOINT).
**Lesson:** PostgreSQL and similar stateful images rely on their entrypoint scripts. Use `args` to pass additional flags, never `command` to override the entrypoint.

---

## Phase 2: Ingestion (Debezium, Kafka, ClickHouse Bronze)

### BUG-4: ClickHouse refuses Nullable columns in ORDER BY keys
**Phase:** 2
**Symptom:** `Partition key contains nullable columns` error when creating Bronze MergeTree tables.
**Root cause:** Avro union types produce Nullable columns. ClickHouse 24.8 requires explicit opt-in for Nullable ORDER BY keys.
**Fix:** Added `allow_nullable_key = 1` to all affected tables.
**Lesson:** ClickHouse's strictness around Nullable keys catches schema design issues early. Always check key column nullability.

### BUG-5: ClickHouse Kafka Engine produces all NULL values
**Phase:** 2
**Symptom:** Bronze raw tables populated with rows but ALL column values are NULL.
**Root cause:** Flatten SMT converts Debezium's `io.debezium.time.Timestamp` (Int64 millis) to `io.debezium.time.ZonedTimestamp` (String ISO-8601). Kafka Engine tables declared these as Int64, causing silent type mismatch.
**Fix:** Changed Kafka Engine timestamp columns to String type, added conversion in Materialized Views.
**Lesson:** Schema transformations (SMTs) can silently change types. Always verify downstream column types after adding transforms.

### BUG-6: Debezium connector connects to wrong MongoDB host
**Phase:** 2
**Symptom:** MongoDB Debezium connector fails to connect with "Connection refused".
**Root cause:** MongoDB replica set was initialized with `localhost:27017` as member hostname. The Java driver resolves the advertised hostname from `rs.conf()`, then connects to `localhost:27017` inside the Connect pod -- which has no MongoDB.
**Fix:** `rs.reconfig()` to update member host to `mongodb.databases.svc.cluster.local:27017`.
**Lesson:** MongoDB replica set member hostnames must be resolvable from ALL clients, not just the local pod.

### BUG-7: S3 Sink Parquet writer crashes on schemaless JSON data
**Phase:** 2
**Symptom:** S3 Sink connector for MongoDB topics throws NullPointerException.
**Root cause:** MongoDB topics use JsonConverter with `schemas.enable: false`. The Parquet format writer requires schema metadata to define columns.
**Fix:** Changed MongoDB S3 Sink from Parquet to JSON format.
**Lesson:** Parquet requires schema. When using schemaless JSON converters, use JSON output format for S3 sinks.

### BUG-8: Strimzi removes REST-API-created connectors silently
**Phase:** 2
**Symptom:** S3 Sink connectors created via REST API disappear within seconds.
**Root cause:** KafkaConnect CRD has `strimzi.io/use-connector-resources: "true"`, which makes Strimzi reconcile connectors from CRDs only. Any REST-API-created connector is treated as unmanaged and deleted.
**Fix:** Created KafkaConnector CRDs instead of using REST API.
**Lesson:** When using Strimzi with CRD mode, ALL connectors must be managed as CRDs. The REST API becomes read-only.

### BUG-18: ImagePullBackOff for locally-built container images
**Phase:** 2
**Symptom:** Kafka Connect pod stuck in ImagePullBackOff.
**Root cause:** Image tagged as `:latest`, which forces `imagePullPolicy: Always`. Since the image is loaded locally into Kind (not from a registry), K8s tries to pull from Docker Hub and fails.
**Fix:** Changed to versioned tag `:1.0.0` which triggers `imagePullPolicy: IfNotPresent`.
**Lesson:** Never use `:latest` tag for locally-built images in Kind. Use versioned tags to ensure IfNotPresent pull policy.

---

## Phase 3: Silver Layer & Streaming Gold

### BUG-9: ClickHouse TOO_MANY_PARTS on backfill INSERT
**Phase:** 3
**Symptom:** `TOO_MANY_PARTS` error when backfilling Silver user_events from Bronze.
**Root cause:** user_events partitioned by (event_type, month) across 6 types x ~24 months = ~144 partitions, exceeding the default 100-partition-per-insert limit.
**Fix:** `SET max_partitions_per_insert_block = 500` for user_events, `= 1000` for order_metrics.
**Lesson:** Backfill operations with fine-grained partitioning can hit ClickHouse safety limits. Temporarily increase `max_partitions_per_insert_block` for bulk loads.

### BUG-10: ClickHouse projections fail on ReplacingMergeTree
**Phase:** 3
**Symptom:** `SUPPORT_IS_DISABLED` error when adding projections to Silver orders table.
**Root cause:** ClickHouse 24.8 requires explicit `deduplicate_merge_projection_mode` setting for projections on ReplacingMergeTree tables.
**Fix:** `ALTER TABLE silver.orders MODIFY SETTING deduplicate_merge_projection_mode = 'drop'`.
**Lesson:** ClickHouse projection support varies by engine. Always check engine-specific requirements before adding projections.

---

## Phase 4: Spark Batch & Delta Lake

### BUG-11: SparkApplication runs in wrong namespace
**Phase:** 4
**Symptom:** SparkApplications submitted to `spark` namespace are never reconciled by the operator.
**Root cause:** spark-operator Helm deployment configured with `--namespaces=default`. The operator's ServiceAccount only has RBAC permissions for the `default` namespace.
**Fix:** Changed all SparkApplication submissions to target `default` namespace.
**Lesson:** Spark operator namespace configuration must match where SparkApplications are deployed. Check operator --namespaces flag.

---

## Phase 5: Advanced dbt Layer

### BUG-12: dbt SummingMergeTree fails with aggregate-inside-aggregate
**Phase:** 5
**Symptom:** `CREATE TABLE AS SELECT` with SummingMergeTree engine fails when SELECT contains aggregate functions.
**Root cause:** SummingMergeTree tries to auto-sum columns that are already aggregated in the SELECT, producing nested aggregate errors.
**Fix:** Changed all mart tables from SummingMergeTree to MergeTree (full-refresh pattern).
**Lesson:** SummingMergeTree is for incremental append workloads, not full-refresh materializations. Use MergeTree for dbt table materializations.

### BUG-13: ClickHouse preserves table alias prefix in view columns
**Phase:** 5
**Symptom:** `Unknown identifier restaurant_id` when querying downstream views.
**Root cause:** ClickHouse 24.8 query analyzer preserves table alias prefix in view column names (e.g., `o.restaurant_id` instead of `restaurant_id`). Downstream queries using unqualified column names fail.
**Fix:** Added explicit `AS` aliases to all join columns in views.
**Lesson:** Always use explicit column aliases in ClickHouse views, especially in JOINs. Don't rely on implicit column name resolution.

### BUG-14: dbt-spark requires Databricks for Python models
**Phase:** 5
**Symptom:** dbt-spark Python models fail with "Databricks cluster_id is required".
**Root cause:** dbt-spark adapter's Python model support only works on Databricks or Serverless Spark, not in session mode.
**Fix:** Skipped dbt-spark entirely. Phase 4 Spark jobs already deliver equivalent feature computation.
**Lesson:** dbt adapter capabilities vary by deployment mode. Verify adapter features work in your target environment before building models.

---

## Phase 7: Observability

### BUG-15: Airflow CrashLoopBackOff from ConfigMap symlinks
**Phase:** 7
**Symptom:** Airflow pod in CrashLoopBackOff with "Detected recursive loop when walking DAG directory".
**Root cause:** K8s ConfigMap volume mounts create symlink structures (..data, ..timestamp) in the mounted directory. Airflow 2.10's plugin loader walks the plugins directory and interprets these symlinks as recursive loops.
**Fix:** Deployed telemetry listener plugin via `kubectl cp` instead of ConfigMap volume mount.
**Lesson:** Airflow's file discovery walks directories recursively and does not tolerate K8s ConfigMap symlink structures. Use direct file copy or subPath mounts for Airflow plugins.

### BUG-16: Grafana crashes on missing relativeTimeRange in alert rules
**Phase:** 7
**Symptom:** Grafana pod in CrashLoopBackOff with "invalid relative time range [From: 0s, To: 0s]".
**Root cause:** Alert rule YAML omitted the `relativeTimeRange` field from data queries. Grafana Unified Alerting requires this field on all non-expression data queries.
**Fix:** Added `relativeTimeRange: {from: 3600, to: 0}` to all data queries in the alerting YAML.
**Lesson:** Grafana alerting YAML is strict about field requirements. Missing optional-looking fields can cause crashes, not graceful defaults.

---

## Summary by Phase

| Phase | Bug Count | Key Theme |
|-------|-----------|-----------|
| 1     | 4         | Shell assumptions, K8s version pinning, service link collisions, entrypoint handling |
| 2     | 6         | Schema type mismatches, connector management, image tagging, MongoDB hostnames |
| 3     | 2         | ClickHouse partition limits and projection engine restrictions |
| 4     | 1         | Spark operator namespace RBAC |
| 5     | 3         | dbt engine selection, ClickHouse column aliasing, adapter limitations |
| 7     | 2         | ConfigMap symlinks, Grafana alerting YAML strictness |

**Total: 18 bugs across 6 phases.**

## Cross-Cutting Patterns

1. **Silent failures are the most dangerous.** BUG-5 (NULL values) and BUG-8 (connector deletion) caused no errors in logs. The system appeared healthy while producing wrong results or losing configuration.

2. **Kubernetes injects more than you think.** BUG-3 (service links), BUG-15 (ConfigMap symlinks), and BUG-18 (image pull policy) all stem from K8s doing implicit work that conflicts with application expectations.

3. **ClickHouse is strict by default.** BUG-4 (Nullable keys), BUG-9 (partition limits), BUG-10 (projection settings), and BUG-13 (alias preservation) all required explicit configuration to resolve. This strictness catches real issues but demands thorough knowledge of engine-specific behaviors.

4. **Version pinning prevents cascading failures.** BUG-2 (K8s 1.35 vs Strimzi) and BUG-14 (dbt-spark capabilities) show that version mismatches between components can surface as cryptic runtime errors far from the actual incompatibility.

5. **Always verify the full data path end-to-end.** BUG-5, BUG-6, and BUG-7 all appeared at integration boundaries where two systems hand off data. Unit-testing each component individually would not have caught these issues.
