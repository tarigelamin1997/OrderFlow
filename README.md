# OrderFlow

**OrderFlow is not a pipeline project — it is a data platform that happens to contain pipelines.**

A production-grade food-tech data platform demonstrating senior-level, end-to-end data engineering across the full modern data stack. Built on Kubernetes (Kind), designed for interview-readiness in the KSA Data Platform Engineer / Data Architect market.

## What OrderFlow Does

Simulates a food delivery marketplace (orders, restaurants, drivers, users) with a hybrid real-time + batch data platform:

- **Real-time CDC path:** PostgreSQL WAL + MongoDB Change Streams → Debezium (custom SMT for PII hashing + schema flattening) → Kafka KRaft (Strimzi) + Schema Registry (Avro) → ClickHouse Bronze/Silver/Gold
- **Batch path:** Kafka S3 Sink → MinIO → Spark 3.5 → Delta Lake Silver → feature engineering → ClickHouse Gold
- **Transformation:** dbt-clickhouse (staging, intermediate, marts, SCD Type 2 snapshots) + dbt-spark (PySpark Python models)
- **Orchestration:** 8 Airflow DAGs (idempotent batch, quality-gated dbt, Spark CRD submission, Delta OPTIMIZE, Great Expectations, schema drift detection, PII audit)
- **Observability:** Grafana (5 dashboards + 5 alert rules) + OpenLineage → Marquez lineage
- **IaC:** Terraform (7 modules, dev/staging/prod environments)
- **Self-service:** Config-driven pipeline factory (YAML → auto-generated DAG + dbt staging + Debezium connector)

## Stack (exact versions)

| Component | Version | Role |
|-----------|---------|------|
| Kafka | 3.7.0 (Strimzi 0.40.0, KRaft) | Event streaming |
| Schema Registry | 7.6.1 | Avro schema management |
| Debezium | 2.7.0 | Change Data Capture |
| ClickHouse | 24.8 LTS | Analytical database |
| Spark | 3.5.1 | Batch processing |
| Delta Lake | 3.1.0 | ACID lakehouse storage |
| Airflow | 2.10.0 (LocalExecutor) | Orchestration |
| dbt-core | 1.8.0 | Transformation |
| Great Expectations | 0.18.0 | Data quality |
| Terraform | 1.7.5 | Infrastructure as Code |
| Marquez | 0.48.0 | Data lineage |
| PostgreSQL | 15 | Source database (relational) |
| MongoDB | 6.0 | Source database (document) |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Source Databases                              │
│   PostgreSQL 15 (orders, users, restaurants, drivers)               │
│   MongoDB 6.0 (user_events, delivery_updates)                       │
└──────────────┬──────────────────────────────────┬───────────────────┘
               │ WAL (CDC)                        │ Change Streams
               ▼                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Debezium 2.7 (Custom SMT: PII SHA-256 hashing + schema flattening)│
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│           Kafka KRaft 3.7 (Strimzi) + Schema Registry 7.6.1        │
└────────────┬─────────────────────────────────────┬──────────────────┘
             │ Real-time path                      │ Batch path
             ▼                                     ▼
┌────────────────────────┐          ┌──────────────────────────────────┐
│ ClickHouse 24.8 LTS    │          │ S3 Sink → MinIO → Spark 3.5     │
│ Bronze (Kafka Engine)   │          │ → Delta Lake 3.1 Silver         │
│ Silver (ReplacingMT)    │          │ → Feature Engineering           │
│ Gold (AggregatingMT)    │          │ → ClickHouse Gold (_batch)      │
└────────────────────────┘          └──────────────────────────────────┘
             │                                     │
             ▼                                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│  dbt-clickhouse 1.8 (staging → intermediate → marts, SCD Type 2)   │
│  dbt-spark 1.8 (PySpark Python models: driver score, demand)        │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Airflow 2.10 — 8 DAGs (batch, dbt, Spark, OPTIMIZE, GE, PII)     │
│  Grafana — 5 dashboards + 5 alert rules                             │
│  OpenLineage → Marquez 0.48 — full pipeline lineage                 │
└──────────────────────────────────────────────────────────────────────┘
```

## Build Phases

| Phase | Title | Status |
|-------|-------|--------|
| 1 | Infrastructure Foundation (Terraform + Kind + all services) | 🔲 In Progress |
| 2 | CDC Pipeline (Data Contracts + Debezium + Avro + S3 Sink) | 🔲 Planned |
| 3 | ClickHouse Deep Schema (full MergeTree family + Projections) | 🔲 Planned |
| 4 | Spark Batch + Delta Lake (Silver + features + Gold writer) | 🔲 Planned |
| 5 | Advanced dbt Layer (2 projects, 21 models, SCD Type 2) | 🔲 Planned |
| 6 | Airflow Orchestration (8 DAGs, 7 patterns) | 🔲 Planned |
| 7 | Observability + FinOps + OpenLineage + Marquez | 🔲 Planned |
| 8 | Multi-Env + Stress Test + Documentation | 🔲 Planned |
| 9 | Self-Service Pipeline Factory (YAML-driven) | 🔲 Planned |

## Quick Start

```bash
# Prerequisites: AWS account with t3.2xlarge access, Terraform 1.7.5

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

# 6. Verify
make verify-phase1
```

## Runtime Environment

- **EC2:** t3.2xlarge (8 vCPU, 32GB RAM), eu-north-1, 100GB EBS gp3
- **Kubernetes:** Kind cluster (1 control-plane + 2 workers)
- **Access:** All services via SSH tunnel (14 forwarded ports)

## Author

**Tarig Elamin** — Data Platform Engineer, Riyadh, KSA

- AWS SAA-C03 (823) | CLF-C02 (734) | AIF-C01
- GitHub: [tarigelamin1997](https://github.com/tarigelamin1997)