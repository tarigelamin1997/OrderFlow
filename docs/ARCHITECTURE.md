# OrderFlow Architecture

## 1. System Context Diagram

The full system context diagram is maintained as a structured spec at
[`docs/architecture/architecture_spec.yaml`](architecture/architecture_spec.yaml).
To regenerate the visual diagram, run `make diagram`.

```
┌─────────────────────────── AWS eu-north-1 ──────────────────────────────┐
│  EC2 t3.2xlarge · 8 vCPU · 32 GB RAM · 100 GB EBS gp3                  │
│  ┌──────────── Kind Cluster (1 control-plane + 2 workers) ───────────┐  │
│  │                                                                   │  │
│  │  PostgreSQL 15 ──┐                                                │  │
│  │                  ├─ Debezium 2.7.0 ─► Kafka 3.7.0 (KRaft) ───┐   │  │
│  │  MongoDB 6.0 ────┘  (Kafka Connect)   Schema Registry 7.6.1  │   │  │
│  │                          │                                    │   │  │
│  │           S3 Sink ───► MinIO ──► Spark 3.5.1 ──► ClickHouse  │   │  │
│  │                                  Delta Lake 3.1.0  24.8 LTS ◄┘   │  │
│  │                                       │                │          │  │
│  │           Airflow 2.10.0 ────► dbt 1.8.0 ──────────►  │          │  │
│  │                │                                       │          │  │
│  │                └──► Marquez 0.48.0        Grafana ◄────┘          │  │
│  │                     (OpenLineage)       (5 dashboards)            │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Data Flow

OrderFlow implements a Medallion architecture (Bronze / Silver / Gold) with two
parallel processing paths feeding into a common Gold layer and Grafana dashboards.

### 2.1 PostgreSQL CDC Path

```
PostgreSQL 15                 Kafka Connect             Kafka 3.7.0
(users, orders,          ──►  Debezium PG connector ──► Topics (Avro,
 restaurants, drivers)        + Flatten SMT              Schema Registry 7.6.1)
 wal_level=logical            + HashPII SMT (SHA-256)
```

Four source tables are captured via logical replication. Debezium applies the
Flatten SMT to produce flat column structures and the HashPII SMT to hash PII
fields (email, phone, name) with SHA-256 at the source before data enters Kafka.

### 2.2 MongoDB CDC Path

```
MongoDB 6.0                   Kafka Connect             Kafka 3.7.0
(user_events,            ──►  Debezium MongoDB       ──► Topics (Avro,
 delivery_updates)            connector + Flatten SMT    Schema Registry 7.6.1)
                              (no auth)
```

MongoDB runs without authentication. The Flatten SMT is applied on the MongoDB
connector as well, producing flat Bronze columns.

### 2.3 Real-Time Streaming Path (ClickHouse)

```
Kafka Topics ──► ClickHouse Bronze          ──► Silver              ──► Gold Streaming
                 (Kafka Engine tables           (ReplacingMergeTree)    (SummingMergeTree,
                  + Materialized Views,                                  AggregatingMergeTree)
                  AvroConfluent format)
```

ClickHouse Kafka Engine tables consume from Kafka using the **AvroConfluent**
format with Schema Registry integration. Materialized Views flush rows into
Bronze MergeTree tables. Further MVs deduplicate into Silver
(ReplacingMergeTree) and aggregate into Gold streaming tables.

### 2.4 Batch Path (Spark + Delta Lake)

```
Kafka Connect ──► MinIO (S3 Sink)          ──► Spark 3.5.1        ──► Delta Lake 3.1.0
                  orflow-raw bucket              (SparkApplication      Silver tables
                  Parquet (PG topics)             CRDs, default ns)     (MinIO)
                  JSON (MongoDB topics)                                    │
                                                                           ▼
                                                                    Feature tables ──► ClickHouse
                                                                    (5 features)       Gold batch
                                                                                       (JDBC)
```

The S3 Sink connector writes Parquet files for PostgreSQL topics and JSON files
for MongoDB topics into MinIO's `orflow-raw` bucket. Spark reads these via Delta
Lake, produces Silver Delta tables, computes 5 feature tables, and writes Gold
batch aggregates to ClickHouse via JDBC.

**Deviation:** SparkApplication CRDs run in the `default` namespace (not
`spark`) because the Spark Operator watches `default` by default.

### 2.5 dbt Transformation Layer

```
dbt-clickhouse 1.8.4
  ├── staging/       6 views     (source mapping)
  ├── intermediate/  4 views     (business logic joins)
  ├── marts/         5 tables    (MergeTree, CREATE TABLE AS SELECT)
  ├── snapshots/     1 SCD Type 2 snapshot
  └── tests/         14 tests    (schema + dbt_expectations)
```

dbt connects to ClickHouse and materializes into two target databases:

| Target             | Database           | Contents                          |
|--------------------|--------------------|-----------------------------------|
| `dev` (default)    | `dbt_dev__gold`    | Staging views, intermediate views, 5 mart tables, SCD snapshot |
| `staging` (manual) | `dbt_staging__gold`| Views only (no mart tables)       |

**Deviation:** dbt-spark is skipped entirely. The dbt-spark adapter requires the
Databricks thrift server, and S3A authentication on Kind has an unresolved
limitation. The `dbt_spark` and `delta_optimize` DAGs are no-op placeholders.

### 2.6 End-to-End Summary

```
Source DBs ──► Debezium ──► Kafka ──► ClickHouse Bronze ──► Silver ──► Gold (streaming)
                              │                                            │
                              ▼                                            ▼
                           MinIO ──► Spark ──► Delta Silver ──► Gold (batch) ──► Grafana
                                                                               (5 dashboards)
                                                    dbt ──► dbt_dev__gold ─────┘
```

---

## 3. Real-Time Path vs Batch Path

| Dimension         | Real-Time (Streaming)                    | Batch                                   |
|-------------------|------------------------------------------|------------------------------------------|
| **Latency**       | Sub-second (Kafka → ClickHouse MV chain) | Hourly / Daily (Spark CRDs + dbt runs)  |
| **Processing**    | ClickHouse Materialized Views            | Spark 3.5.1 + Delta Lake 3.1.0          |
| **Storage**       | ClickHouse (Bronze → Silver → Gold)      | MinIO (Delta) → ClickHouse (Gold batch) |
| **Orchestration** | Autonomous (MV chain, always-on)         | Airflow DAGs (scheduled triggers)        |
| **Use case**      | Live dashboards, real-time KPIs          | Feature engineering, historical rollups  |
| **Grafana**       | Both paths feed Grafana dashboards       | Both paths feed Grafana dashboards       |

The streaming path handles continuously updating metrics (order counts, revenue
sums, delivery statuses). The batch path handles computationally heavier
workloads (feature engineering, full-table aggregations, Delta Lake compaction).
Both converge in the Gold layer and are queryable from the same Grafana
dashboards.

---

## 4. Technology Selection Rationale

| Component              | Technology                 | Rationale                                                    |
|------------------------|----------------------------|--------------------------------------------------------------|
| **CDC**                | Debezium 2.7.0             | Industry standard for database CDC; native PG + Mongo support |
| **Messaging**          | Kafka 3.7.0 (KRaft)       | ZooKeeper-free mode reduces operational overhead              |
| **Cluster operator**   | Strimzi 0.40.0             | K8s-native Kafka management with CRD-driven configuration     |
| **Schema management**  | Confluent Schema Registry  | Avro schema evolution with backward/forward compatibility     |
| **OLAP warehouse**     | ClickHouse 24.8 LTS        | Columnar engine optimized for real-time analytical queries    |
| **Object storage**     | MinIO                      | S3-compatible storage for Delta Lake on a single-node cluster |
| **Batch processing**   | Spark 3.5.1                | Distributed compute for Delta Lake reads/writes and features  |
| **Lake format**        | Delta Lake 3.1.0           | ACID transactions on object storage with time travel          |
| **Transformation**     | dbt-clickhouse 1.8.4       | SQL-first transformation with lineage and testing built in    |
| **Orchestration**      | Airflow 2.10.0             | DAG-based scheduling with KubernetesPodOperator and SparkKubernetes |
| **Data quality**       | Great Expectations 0.18.0  | Programmable expectations integrated into Airflow quality gate |
| **Lineage**            | Marquez 0.48.0             | OpenLineage-compatible lineage server with REST API and UI    |
| **Lineage backend**    | PostgreSQL 15              | Marquez uses PG backend (not H2) for production durability    |
| **Dashboards**         | Grafana + Altinity plugin  | Native ClickHouse datasource with provisioned-as-code dashboards |
| **Infrastructure**     | Terraform 1.7.5            | Declarative IaC for AWS resources                             |
| **K8s runtime**        | Kind                       | Lightweight local K8s for dev/staging on a single EC2 instance |

---

## 5. ClickHouse Engine Selection

Each ClickHouse table uses a deliberately chosen engine. The table below lists
the engine, rationale, and the rejected alternative with the reason for rejection.

| Layer            | Engine                  | Rationale                                      | Rejected Alternative          | Rejection Reason                          |
|------------------|-------------------------|-------------------------------------------------|-------------------------------|-------------------------------------------|
| **Bronze**       | MergeTree               | Append-only ingestion from Kafka Engine         | ReplicatedMergeTree           | Single-node cluster; replication overhead unnecessary |
| **Silver**       | ReplacingMergeTree      | Deduplication by version column on merge        | CollapsingMergeTree           | Requires a sign column (+1/-1) in source data |
| **Gold streaming** | SummingMergeTree / AggregatingMergeTree | Auto-aggregation on merge reduces query-time computation | MergeTree | No automatic aggregation; queries must aggregate at read time |
| **Gold batch**   | MergeTree               | Full-refresh writes from Spark; no incremental merge needed | SummingMergeTree | Full refresh overwrites all data; auto-summing would corrupt totals |
| **Mart tables**  | MergeTree               | dbt uses `CREATE TABLE AS SELECT` materialization | SummingMergeTree | `CREATE TABLE AS SELECT` is incompatible with SummingMergeTree |

### Notable ClickHouse Settings

- **`allow_nullable_key = 1`** — Enabled on tables where ORDER BY columns are
  Nullable (required because Debezium CDC can produce NULLs for certain keys
  during deletes or schema changes).
- **`deduplicate_merge_projection_mode = 'drop'`** — Set on ReplacingMergeTree
  Silver tables that use projections, preventing projection deduplication
  conflicts during background merges.

---

## 6. Airflow DAG Dependency Graph

Eight DAGs are deployed in Airflow. Six are operational; two are no-op
placeholders awaiting S3A authentication resolution.

```
                          ┌──────────────────┐
        hourly ──────────►│ batch_ingestion  │ (Spark CRDs → Delta → Gold batch)
                          └────────┬─────────┘
                                   │ triggers
                                   ▼
                          ┌──────────────────┐
        daily ───────────►│ dbt_clickhouse   │ (dbt run --target dev)
                          └────────┬─────────┘
                                   │ triggers
                                   ▼
                          ┌──────────────────┐
        daily ───────────►│ quality_gate     │ (Great Expectations checks)
                          └──────────────────┘

                          ┌──────────────────────────┐
        manual ──────────►│ dbt_clickhouse_staging   │ (dbt run --target staging)
                          └──────────────────────────┘

                          ┌──────────────────┐
        daily ───────────►│ schema_drift     │ (schema drift detection → gold.schema_drift_log)
                          └──────────────────┘

                          ┌──────────────────┐
        weekly ──────────►│ pii_audit        │ (PII audit check → gold.pii_audit_log)
                          └──────────────────┘

                          ┌──────────────────┐
        placeholder ─────►│ dbt_spark        │ (no-op: S3A auth limitation)
                          └──────────────────┘

                          ┌──────────────────┐
        placeholder ─────►│ delta_optimize   │ (no-op: S3A auth limitation)
                          └──────────────────┘
```

| DAG                      | Schedule  | Description                                        |
|--------------------------|-----------|----------------------------------------------------|
| `batch_ingestion`        | Hourly    | Submits SparkApplication CRDs for silver ingestion, feature engineering, and gold batch writes |
| `dbt_clickhouse`         | Daily     | Runs `dbt run` and `dbt test` against the `dev` target (dbt_dev__gold) |
| `dbt_clickhouse_staging` | Manual    | Runs `dbt run` against the `staging` target (dbt_staging__gold, views only) |
| `dbt_spark`              | Placeholder | No-op DAG; dbt-spark skipped due to Databricks thrift requirement |
| `delta_optimize`         | Placeholder | No-op DAG; Delta OPTIMIZE/VACUUM requires functional S3A auth |
| `quality_gate`           | Daily     | Runs Great Expectations suites and logs results     |
| `schema_drift`           | Daily     | Detects column-level schema changes and writes to `gold.schema_drift_log` |
| `pii_audit`              | Weekly    | Audits PII hashing compliance and writes to `gold.pii_audit_log` |

---

## 7. Security

### 7.1 PII Protection

PII fields (email, phone, name) are hashed with **SHA-256** at the source using
the Debezium **HashPII** Single Message Transform (SMT). This means PII never
enters Kafka, ClickHouse, or MinIO in cleartext. The hashing is irreversible and
applied on both the PostgreSQL and MongoDB connectors.

### 7.2 Secret Management

| Context                 | Pattern                                             |
|-------------------------|-----------------------------------------------------|
| Kubernetes Secrets      | Manifests use placeholder values only; actual values injected via `kubectl create secret` at deploy time |
| dbt profiles.yml        | Uses `env_var()` exclusively for credentials        |
| Debezium connector JSON | Uses `${PLACEHOLDER}` syntax for database passwords |
| Grafana                 | Admin password set to `orderflow` (not default `admin`); ClickHouse datasource credentials provisioned via YAML, not hard-coded in dashboard JSON |

No secrets are committed to the repository.

### 7.3 RBAC and Network Isolation

- Services are deployed in **dedicated Kubernetes namespaces**: `kafka`,
  `databases`, `spark`, `clickhouse`, `airflow`, `monitoring`, `marquez`.
- Namespace isolation provides a logical RBAC boundary per component.
- No NodePorts are exposed to the internet. All service access is via **SSH
  tunnel** to the EC2 instance.

### 7.4 MongoDB Authentication

**Deviation:** MongoDB runs without authentication. This is acceptable for the
single-node Kind development environment but would require auth in production.

---

## 8. Observability

### 8.1 Grafana Dashboards

Five dashboards are provisioned as code (JSON files in `observability/`), not
created manually in the Grafana UI. All use the Altinity ClickHouse datasource
plugin.

| Dashboard           | Purpose                                              |
|---------------------|------------------------------------------------------|
| **Pipeline Health** | Kafka lag, ClickHouse insert rates, Spark job status |
| **Data Quality**    | Great Expectations pass/fail rates, row counts       |
| **ClickHouse Ops**  | Query latency, merge activity, disk/memory usage     |
| **Business Metrics**| Revenue, order volume, driver utilization, delivery times |
| **FinOps**          | Resource consumption, cost attribution per pipeline stage |

### 8.2 Alert Rules

Five Grafana alert rules monitor critical pipeline health indicators. Alerts
fire when thresholds are breached (e.g., Kafka consumer lag exceeding limits,
ClickHouse insert failures, Spark job failures).

### 8.3 Data Lineage

**Marquez 0.48.0** serves as the OpenLineage-compatible lineage server.

- Marquez uses a **PostgreSQL backend** (not the default H2 in-memory database)
  for durability.
- Marquez API is accessible at port **30500**; the UI at port **30301**.
- Airflow emits OpenLineage events to Marquez for all DAG runs, providing
  end-to-end lineage from source tables through transformations to Gold tables.

### 8.4 Airflow Telemetry

A custom **telemetry listener** plugin captures DAG execution metadata and writes
it to `gold.dag_run_log` in ClickHouse.

**Deviation:** The telemetry listener is deployed to the Airflow pod via
`kubectl cp` rather than a ConfigMap mount. This approach was chosen because
Airflow's plugin discovery requires files in the plugins directory, and ConfigMap
volume mounts would conflict with the existing Airflow deployment configuration.

---

## Appendix A: Namespace Layout

| Namespace    | Services                                    |
|--------------|---------------------------------------------|
| `databases`  | PostgreSQL 15, MongoDB 6.0                  |
| `kafka`      | Kafka 3.7.0 (Strimzi), Schema Registry 7.6.1, Kafka Connect (Debezium 2.7.0) |
| `clickhouse` | ClickHouse 24.8 LTS                         |
| `spark`      | MinIO (S3 API)                              |
| `default`    | SparkApplication CRDs (Spark jobs)          |
| `airflow`    | Airflow 2.10.0, dbt                         |
| `monitoring` | Grafana                                     |
| `marquez`    | Marquez 0.48.0                              |

## Appendix B: Port Allocation

| Service              | NodePort |
|----------------------|----------|
| PostgreSQL           | 30432    |
| MongoDB              | 30017    |
| Kafka                | 30092    |
| Schema Registry      | 30081    |
| Kafka Connect        | 30083    |
| ClickHouse HTTP      | 30123    |
| ClickHouse Native    | 30900    |
| MinIO S3 API         | 30910    |
| MinIO Console        | 30901    |
| Airflow UI           | 30080    |
| Grafana              | 30300    |
| Marquez API          | 30500    |
| Marquez UI           | 30301    |
| Spark UI             | 30404    |

All ports are accessed exclusively via SSH tunnel. No public exposure.

## Appendix C: Key Deviations from Default Configurations

This section consolidates all non-obvious configuration choices for quick
reference during troubleshooting.

| Deviation                              | Reason                                                        |
|----------------------------------------|---------------------------------------------------------------|
| Flatten SMT on both connectors         | Produces flat Bronze columns instead of nested Debezium structs |
| AvroConfluent format in Kafka Engine   | Required for Schema Registry integration with ClickHouse      |
| MongoDB no auth                        | Kind dev environment; not for production                      |
| SparkApplication in `default` namespace| Spark Operator watches `default` by default                   |
| dbt-spark skipped                      | S3A auth limitation + Databricks thrift requirement on Kind   |
| Marquez uses PostgreSQL backend        | Durability over default H2 in-memory                          |
| `allow_nullable_key = 1`              | Debezium CDC can produce NULLs in ORDER BY columns            |
| `deduplicate_merge_projection_mode = 'drop'` | Prevents projection conflicts on ReplacingMergeTree    |
| Grafana admin password: `orderflow`    | Changed from default `admin` for minimal security             |
| Telemetry listener via `kubectl cp`    | ConfigMap mount conflicts with Airflow deployment volumes      |
| `dbt_staging__gold` has views only     | Mart tables materialize only in `dbt_dev__gold` (dev target)  |
