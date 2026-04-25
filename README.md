# OrderFlow

**OrderFlow is not a pipeline project — it is a data platform that happens to contain pipelines.**

A production-grade food-tech data platform demonstrating senior-level, end-to-end data engineering across the full modern data stack. Built on Kubernetes (Kind), all 9 phases complete, 92 verification checks passed. Designed for the KSA Data Platform Engineer / Data Architect market.

---

## What OrderFlow Demonstrates

Five platform archetypes in a single deployable system:

| Archetype | What was built |
|-----------|---------------|
| Event-driven | PostgreSQL WAL + MongoDB Change Streams → Debezium → Kafka KRaft — full CDC pipeline with custom SMT chain (PII hashing, schema flattening, event routing) |
| Lakehouse | Kafka S3 Sink → MinIO → Spark 3.5 → Delta Lake (ACID MERGE INTO, Z-ORDER, schema evolution) → ClickHouse Gold |
| IaC | Terraform 7-module multi-environment (dev/staging/prod) — full platform provisionable from scratch |
| Observability | OpenLineage → Marquez lineage, Grafana 5 dashboards + 5 alert rules provisioned as YAML, Great Expectations quality gates |
| Self-service | Config-driven pipeline factory — one YAML file auto-generates a DAG + dbt staging model + Debezium connector |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Source Databases                              │
│   PostgreSQL 15 (orders, users, restaurants, drivers)               │
│   MongoDB 6.0  (user_events, delivery_updates)                      │
└──────────────┬──────────────────────────────┬───────────────────────┘
               │ WAL / pgoutput               │ Change Streams
               ▼                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│           Debezium 2.7  —  Custom SMT Chain                          │
│   FlattenMetadata → HashPII (SHA-256, per-field salt) →              │
│   RouteByEventType                                                   │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│     Kafka KRaft 3.7 (Strimzi 0.40) + Schema Registry 7.6.1          │
│     Avro + BACKWARD compatibility on PG topics                       │
│     JSON on MongoDB topics (schema-flexible documents)               │
└────────────┬─────────────────────────────────┬──────────────────────┘
             │ Real-time path                  │ Batch path
             ▼                                 ▼
┌────────────────────────┐     ┌───────────────────────────────────────┐
│  ClickHouse 24.8 LTS   │     │  S3 Sink → MinIO (Hive-partitioned    │
│                        │     │  Parquet, Snappy) → Spark 3.5.1       │
│  Bronze:               │     │  → Delta Lake 3.1 Silver              │
│    Kafka Engine tables │     │    (ACID upserts, Z-ORDER,            │
│    Full Debezium        │     │    schema evolution)                  │
│    envelope retained   │     │  → Feature engineering                │
│                        │     │  → ClickHouse Gold (_batch)           │
│  Silver:               │     └───────────────────────────────────────┘
│    ReplacingMergeTree  │
│    (mutable entities)  │
│    MergeTree           │
│    (immutable facts)   │
│                        │
│  Gold:                 │
│    SummingMergeTree    │
│    AggregatingMergeTree│
│    + Projections       │
└────────────────────────┘
             │                                 │
             ▼                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  dbt-clickhouse 1.8  (staging → intermediate → marts, SCD Type 2)   │
│  dbt-spark 1.8  (PySpark Python models: driver score, demand index)  │
│  21 models total, 2 dbt projects, multi-environment separation       │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Airflow 2.10  —  8 DAGs                                             │
│    Idempotent batch  |  Quality-gated dbt  |  Spark CRD submission  │
│    Delta OPTIMIZE    |  Great Expectations  |  Schema drift detect   │
│    PII audit         |  Self-service factory DAG                     │
│                                                                      │
│  Grafana  —  5 dashboards + 5 alert rules (provisioned as YAML)      │
│  OpenLineage → Marquez 0.48  —  full pipeline lineage                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Stack

| Component | Version | Role |
|-----------|---------|------|
| Kafka | 3.7.0 (Strimzi 0.40, KRaft) | Event streaming, no ZooKeeper |
| Schema Registry | 7.6.1 | Avro schema management, BACKWARD compatibility |
| Debezium | 2.7.0 | CDC — PostgreSQL WAL + MongoDB Change Streams |
| ClickHouse | 24.8 LTS | Analytical database — full MergeTree family |
| Spark | 3.5.1 | Batch processing on Kubernetes via spark-operator |
| Delta Lake | 3.1.0 | ACID lakehouse storage — MERGE INTO, Z-ORDER |
| Airflow | 2.10.0 | Orchestration — 8 production DAG patterns |
| dbt-core | 1.8.0 | Transformation — 2 adapters, 21 models |
| Great Expectations | 0.18.0 | Data quality gates |
| Terraform | 1.7.5 | IaC — 7 modules, 3 environments |
| Marquez | 0.48.0 | Data lineage |
| PostgreSQL | 15 | Relational source (WAL-level CDC) |
| MongoDB | 6.0 | Document source (Change Streams, replica set) |

---

## Build Phases

All 9 phases complete. 92 verification checks passed.

| Phase | Title | Status |
|-------|-------|--------|
| 1 | Infrastructure Foundation — Terraform + Kind + all services | ✅ Built & Verified |
| 2 | CDC Pipeline — Data Contracts + Debezium + Avro + S3 Sink | ✅ Built & Verified |
| 3 | ClickHouse Deep Schema — full MergeTree family + Projections | ✅ Built & Verified |
| 4 | Spark Batch + Delta Lake — Silver + features + Gold writer | ✅ Built & Verified |
| 5 | Advanced dbt Layer — 2 projects, 21 models, SCD Type 2 | ✅ Built & Verified |
| 6 | Airflow Orchestration — 8 DAGs, 7 patterns | ✅ Built & Verified |
| 7 | Observability + FinOps + OpenLineage + Marquez | ✅ Built & Verified |
| 8 | Multi-Env + Stress Test + Documentation | ✅ Built & Verified |
| 9 | Self-Service Pipeline Factory — YAML-driven | ✅ Built & Verified |

---

## Key Design Decisions

These are the decisions that distinguish OrderFlow from a tutorial build.

**Full Debezium envelope retained at Bronze.** `ExtractNewRecordState` SMT was deliberately not applied. Bronze stores `op`, `before`, and `after` intact. Reason: `op = 'd'` (delete) is required for SCD Type 2 logic in dbt Silver; `before` is required for update diff tracking. Flattening at the connector destroys both — unrecoverable without a full resnapshot.

**Three-SMT chain on MongoDB connector.** `FlattenMetadata → HashPII → RouteByEventType` runs inside the Connect worker before serialization. PII (email, phone) is SHA-256 hashed with a per-field salt before any record reaches Kafka. Bronze and MinIO Parquet never contain plaintext PII. Hash function uses `ThreadLocal<MessageDigest>` to avoid per-record instantiation cost.

**Engine selection in ClickHouse is semantic, not performance-driven.** `ReplacingMergeTree` for mutable entities (orders, users) — converges to latest state at merge time. `SummingMergeTree` for purely additive Gold metrics (revenue, delivery counts). `AggregatingMergeTree` for non-additive Gold metrics (order counts by status — orders transition between statuses, counts are not purely additive). Engine selection is driven by what the data represents, not by query patterns.

**`decimal.handling.mode: double` on the PostgreSQL connector.** `DECIMAL(10,2)` maps to Avro `double` to avoid Avro `bytes` + logical type complexity in ClickHouse Kafka Engine deserialization. Float imprecision is acceptable at Bronze. Silver dbt model casts to `Decimal(10,2)` for financial accuracy. The cast happens exactly once, at the Silver boundary.

**MongoDB Silver stores `after` as raw `String`.** `user_events` has three schema versions (V1/V2/V3) co-existing in production data. Avro would require a rigid schema. Bronze stores the full MongoDB document as a JSON string. Silver extracts fields using `JSONExtractString`, `JSONExtractFloat` etc., with `multiIf(JSONHas(...))` for schema version detection. Evolution never breaks the pipeline.

**S3 Sink uses CDC event timestamp for Hive partitioning.** `timestamp.field: ts_ms` not wall clock. Seed data spans 2023–2025. Wall clock partitioning would land all historical data in a single 2026 folder, making Spark date-range queries useless.

**dbt owns `dbt_dev__gold` and `dbt_staging__gold` exclusively.** Phase 3 streaming Gold tables (`gold.*`) are owned by ClickHouse Materialized Views. dbt never writes to `gold.*`. This prevents dbt full-refresh runs from dropping live AggregatingMergeTree state.

---

## Known Deviations from Original Design

Documented decisions made during execution that differ from the original plan. These are architectural decisions, not bugs.

| Deviation | Decision | Rationale |
|-----------|----------|-----------|
| Services deployed in dedicated namespaces, not `default` | Kept as-is | Better isolation; all service mesh references updated accordingly |
| Airflow runs as StatefulSet, not Deployment | Kept as-is | Persistent volume for DAG logs requires stable pod identity |
| dbt-spark skipped | Architectural decision | Kind/S3A incompatibility — IRSA unavailable on Kind; dbt-spark requires S3A credentials at model run time which is not injectable via Kind's service account model |
| SparkApplications run in `default` namespace | Kept as-is | spark-operator RBAC is scoped to `default` in the Kind deployment |
| Flat Bronze column names from Flatten SMT | Kept as-is | Prefixed column names (`before_id`, `after_id`) are more queryable than nested Struct columns in ClickHouse Kafka Engine |
| MongoDB requires no-auth configuration | Kept as-is | Kind networking does not expose MongoDB's authSource mechanism correctly on the replica set bootstrap path |
| Telemetry listener plugin ephemeral | Documented | Wiped on pod restart — must be re-copied manually on cluster resume |

---

## Seed Data

| Entity | Volume | Notes |
|--------|--------|-------|
| Users | 5,000 | PII hashed at CDC source |
| Restaurants | 200 | |
| Drivers | 300 | PII hashed at CDC source |
| Orders | 50,000 | ~3 status changes per order in CDC history |
| user_events | ~30,000 | 3 schema versions (V1/V2/V3) co-existing |
| delivery_updates | ~15,000 | Nested location struct `{lat, lng, accuracy}` |

---

## Runtime Environment

- **EC2:** t3.2xlarge (8 vCPU, 32GB RAM), eu-north-1, 100GB EBS gp3 (`delete_on_termination=false`)
- **Kubernetes:** Kind cluster (1 control-plane + 2 workers)
- **Access:** All services via SSH tunnel — 14 forwarded NodePorts

| Service | NodePort | Internal |
|---------|----------|----------|
| PostgreSQL | 30432 | postgres:5432 |
| MongoDB | 30017 | mongodb:27017 |
| Kafka | 30092 | kafka-bootstrap:9092 |
| Schema Registry | 30081 | schema-registry:8081 |
| Kafka Connect | 30083 | kafka-connect:8083 |
| ClickHouse HTTP | 30123 | clickhouse:8123 |
| ClickHouse Native | 30900 | clickhouse:9000 |
| MinIO S3 API | 30910 | minio:9000 |
| MinIO Console | 30901 | minio:9001 |
| Airflow | 30080 | airflow:8080 |
| Grafana | 30300 | grafana:3000 |
| Marquez API | 30500 | marquez:5000 |
| Marquez UI | 30301 | marquez-web:3000 |
| Spark UI | 30404 | spark-ui:4040 |

---

## Quick Start

```bash
# Prerequisites: AWS CLI configured, Terraform 1.7.5, make

# 1. Clone
git clone https://github.com/tarigelamin1997/OrderFlow.git
cd OrderFlow

# 2. Provision EC2
export TF_VAR_allowed_ssh_cidr="YOUR_IP/32"
make ec2-apply

# 3. SSH into EC2
ssh orderflow

# 4. Deploy platform
make apply

# 5. Seed data
make seed

# 6. Verify all phases
make verify
```

Cost discipline: `make pause` after every session to stop the EC2 instance. Infrastructure is pause/resume safe — EBS volume persists with `delete_on_termination=false`.

---

## Cost Model

| State | Monthly cost |
|-------|-------------|
| Running (24/7) | ~$120/month (t3.2xlarge + EBS) |
| Paused (EC2 stopped) | ~$8/month (EBS only) |
| Destroyed | $0/month |

---

## Author

**Tarig Elamin** — Data Platform Engineer, Riyadh, KSA

- AWS SAA-C03 (823) | CLF-C02 (734) | AIF-C01 (754) | DEA-C01 (pending)
- GitHub: [tarigelamin1997](https://github.com/tarigelamin1997)
- LinkedIn: [linkedin.com/in/tarigelamin](https://linkedin.com/in/tarigelamin)
