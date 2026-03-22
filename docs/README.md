# OrderFlow

OrderFlow is not a pipeline project — it is a data platform that happens to contain pipelines.

## What OrderFlow Is

OrderFlow is a production-grade food-tech data platform that demonstrates senior-level, end-to-end data engineering across the full modern data stack. It simulates a food delivery marketplace (orders, restaurants, drivers, users) with a hybrid real-time and batch architecture, deployed entirely on Kubernetes via Infrastructure as Code. The platform is designed for interview-readiness in the KSA Data Platform Engineer / Data Architect market and serves as a portfolio-grade reference implementation.

## Architecture Overview

For the full architecture specification, data flow diagrams, and component interaction details, see [ARCHITECTURE.md](architecture/ARCHITECTURE.md).

```
Source Databases
  PostgreSQL 15 (orders, users, restaurants, drivers)
  MongoDB 6.0 (user_events, delivery_updates)
       |                          |
       | WAL (CDC)                | Change Streams
       v                          v
  Debezium 2.7 (Custom SMT: PII SHA-256 hashing + schema flattening)
                    |
                    v
  Kafka KRaft 3.7 (Strimzi 0.40.0) + Schema Registry 7.6.1 (Avro)
       |                                    |
       | Real-time path                     | Batch path
       v                                    v
  ClickHouse 24.8 LTS               S3 Sink -> MinIO -> Spark 3.5.1
    Bronze (Kafka Engine)              -> Delta Lake 3.1 Silver
    Silver (ReplacingMergeTree)        -> Feature Engineering
    Gold (AggregatingMergeTree)        -> ClickHouse Gold (_batch)
       |                                    |
       v                                    v
  dbt-clickhouse 1.8.4 (staging -> intermediate -> marts, SCD Type 2)
  dbt-spark 1.8.0 (SKIPPED -- see note below)
                    |
                    v
  Airflow 2.10.0 -- 8 DAGs (6 operational, 2 no-op placeholders)
  Grafana -- 5 dashboards + 5 alert rules
  OpenLineage -> Marquez 0.48.0 -- full pipeline lineage
```

> **Note on dbt-spark:** The dbt-spark project (PySpark Python models for driver scoring and demand forecasting) was **skipped** due to an architectural limitation on the Kind/MinIO runtime environment. The S3A authentication layer requires Hadoop credentials that are not compatible with MinIO's local endpoint in a non-cloud context, and dbt-spark's `submission_method: cluster` requires a Databricks-compatible endpoint. The dbt-spark models, project configuration, and profiles exist in the repository as reference artifacts, but they are not executed in any DAG or verification step.

> **Note on DAGs 3 and 4:** `dag_dbt_spark_models` (DAG 3) and `dag_delta_optimize` (DAG 4) are **no-op placeholders**. DAG 3 is blocked by the dbt-spark limitation above. DAG 4 (Delta Lake OPTIMIZE/VACUUM) requires a running Spark cluster with Delta Lake write access; it is wired but executes a pass-through task. Both DAGs are registered in Airflow and will activate when the runtime constraints are resolved.

## Stack (Exact Versions)

All versions are pinned in [`versions.yaml`](../versions.yaml) at the repository root. No version is hard-coded in any Dockerfile, Helm chart, Terraform module, or requirements file.

| Component | Version | Role |
|---|---|---|
| Kafka | 3.7.0 (Strimzi 0.40.0, KRaft mode) | Event streaming, no ZooKeeper |
| Schema Registry | 7.6.1 | Avro schema management and compatibility enforcement |
| Debezium | 2.7.0 | Change Data Capture from PostgreSQL WAL and MongoDB Change Streams |
| ClickHouse | 24.8 LTS | Analytical database (Bronze/Silver/Gold layers) |
| Spark | 3.5.1 | Batch processing engine (SparkApplication CRDs on K8s) |
| Delta Lake | 3.1.0 | ACID lakehouse storage on MinIO |
| Airflow | 2.10.0 (LocalExecutor) | Workflow orchestration (8 DAGs) |
| dbt-core | 1.8.0 | SQL transformation framework |
| dbt-clickhouse | 1.8.4 | dbt adapter for ClickHouse |
| dbt-spark | 1.8.0 | dbt adapter for Spark (skipped -- Kind/MinIO limitation) |
| Great Expectations | 0.18.21 | Data quality validation |
| Terraform | 1.7.5 | Infrastructure as Code (7 modules, 3 environments) |
| Marquez | 0.48.0 | Data lineage via OpenLineage |
| PostgreSQL | 15 | Source database (relational: orders, users, restaurants, drivers) |
| MongoDB | 6.0 | Source database (document: user_events, delivery_updates) |

## Quick Start

**Prerequisites:** AWS account with t3.2xlarge access, Terraform >= 1.7.5, SSH client.

```bash
# 1. Clone the repository
git clone https://github.com/tarigelamin1997/OrderFlow.git
cd OrderFlow

# 2. Provision EC2 instance
export TF_VAR_allowed_ssh_cidr="YOUR_IP/32"
make ec2-apply

# 3. SSH into EC2
ssh orderflow

# 4. Deploy the platform (Terraform -> Kind -> all services)
make apply

# 5. Seed source databases with synthetic data
make seed

# 6. Verify each phase in order
make verify-phase1    # Infrastructure: Kind cluster, namespaces, all pods Running
make verify-phase2    # CDC: Debezium connectors, Kafka topics, Schema Registry subjects
make verify-phase3    # ClickHouse: Bronze/Silver/Gold tables, materialized views, row counts
make verify-phase4    # Spark: Delta Lake Silver tables, feature engineering, Gold batch tables
make verify-phase5    # dbt: staging/intermediate/marts models, SCD snapshots, 14 tests passing
make verify-phase6    # Airflow: 8 DAGs registered, 6 operational, PII audit, schema drift DDL
make verify-phase7    # Observability: 5 dashboards, 5 alerts, OpenLineage events in Marquez
```

## SLO Summary

These are the platform-level service level objectives. Each is verified during the relevant phase.

| SLO | Target | Measurement Point |
|---|---|---|
| CDC end-to-end latency | < 30 seconds | Source commit to ClickHouse Bronze row visible |
| Batch ingestion wall time | < 15 minutes | Spark submit to ClickHouse Gold `_batch` table populated |
| dbt run duration | < 5 minutes | `dbt run` start to finish (all models, ClickHouse target) |
| Query response p95 | < 2 seconds | ClickHouse Gold table queries via HTTP interface |
| Data quality pass rate | 100% | Great Expectations checkpoint: all expectations pass |
| Zero data loss | 0 records lost | Source row count matches Silver row count after full sync |

## Repository Structure

```
OrderFlow/
|-- versions.yaml                  # Single source of truth for all component versions
|-- Makefile                       # Top-level make targets (apply, seed, verify-phaseN)
|-- CLAUDE.md                      # Agent execution rules
|-- LICENSE
|
|-- terraform/                     # Phase 1: Infrastructure as Code
|   |-- modules/
|   |   |-- kind-cluster/          # Kind cluster (1 control-plane + 2 workers)
|   |   |-- databases/             # PostgreSQL 15, MongoDB 6.0
|   |   |-- kafka/                 # Strimzi operator, Kafka KRaft, Schema Registry
|   |   |-- clickhouse/            # ClickHouse 24.8 LTS (StatefulSet)
|   |   |-- spark/                 # Spark operator, MinIO, ServiceAccount
|   |   |-- airflow/               # Airflow 2.10 (webserver + scheduler)
|   |   |-- grafana/               # Grafana + provisioned datasources
|   |   |-- marquez/               # Marquez API + UI + backing Postgres
|   |-- environments/
|   |   |-- dev.tfvars
|   |   |-- staging.tfvars
|   |   |-- prod.tfvars
|   |-- aws/                       # EC2 t3.2xlarge provisioning
|
|-- seed/                          # Phase 1: Synthetic data generation
|   |-- postgres/                  # users, restaurants, drivers, orders
|   |-- mongo/                     # user_events, delivery_updates
|
|-- scripts/                       # Verification and utilities
|   |-- verify_phase1.sh
|   |-- verify_phase3.sh
|   |-- check_versions.py          # Drift detection: versions.yaml vs actual
|   |-- check_version_drift.py
|   |-- generate_diagram.py
|
|-- airflow/                       # Phase 6: Orchestration
|   |-- Dockerfile                 # Custom Airflow image with dbt + providers
|   |-- _gen/                      # Generated DAG and DDL content
|       |-- content_dag_batch_ingestion.py
|       |-- content_dag_quality_gate.py
|       |-- content_dag_pii_audit.py
|       |-- content_dag_schema_drift.py
|       |-- content_dags_dbt_placeholders.py
|       |-- content_pii_audit_ddl.py
|       |-- content_schemas.py
|       |-- content_verify_phase6.py
|
|-- dbt/                           # Phase 5: Transformation layer
|   |-- _gen/                      # Generated dbt project content
|       |-- content_dbt_clickhouse_root.py
|       |-- content_dbt_staging_sql.py
|       |-- content_dbt_intermediate.py
|       |-- content_dbt_marts.py
|       |-- content_dbt_snapshots_macros.py
|       |-- content_dbt_sources.py
|       |-- content_dbt_spark_root.py
|       |-- content_dbt_spark_models.py
|       |-- content_airflow_dockerfile.py
|       |-- content_verify_phase5.py
|
|-- spark/                         # Phase 4: Batch processing
|   |-- _gen/                      # Generated Spark job content
|       |-- content_dockerfile.py
|       |-- content_silver_ingestion.py
|       |-- content_feature_engineering.py
|       |-- content_gold_writer.py
|       |-- content_clickhouse.py
|       |-- content_manifests.py
|       |-- content_verify.py
|       |-- gen_phase4.py
|
|-- observability/                 # Phase 7: Monitoring and lineage
|   |-- _gen/                      # Generated observability content
|       |-- content_dashboards.py
|       |-- content_grafana_provisioning.py
|       |-- content_ch_ddl.py
|       |-- content_k8s_patches.py
|       |-- content_telemetry_plugin.py
|       |-- content_verify_phase7.py
|
|-- docs/                          # Phase 8: Documentation
|   |-- architecture/
|       |-- architecture_spec.yaml
|
|-- .github/
|   |-- workflows/                 # CI/CD
```

## Phase Summary

| Phase | Title | Delivers | Status |
|---|---|---|---|
| 1 | Infrastructure Foundation | Terraform IaC, Kind cluster, all services deployed, seed data | Built, Verified |
| 2 | CDC Pipeline | Debezium connectors (PG + Mongo), Kafka topics, Schema Registry (Avro), S3 Sink to MinIO | Built, Verified |
| 3 | ClickHouse Deep Schema | Bronze (Kafka Engine), Silver (ReplacingMergeTree), Gold (AggregatingMergeTree), projections | Built, Verified |
| 4 | Spark Batch + Delta Lake | Delta Silver tables (6 entities), feature engineering (5 features), Gold batch tables (3) | Built, Verified |
| 5 | Advanced dbt Layer | dbt-clickhouse project (staging, intermediate, marts), SCD Type 2 snapshots, 14 tests. dbt-spark skipped (Kind limitation) | Built, Verified |
| 6 | Airflow Orchestration | 8 DAGs registered (6 operational, 2 no-op placeholders for DAGs 3/4), PII audit, schema drift detection | Built, Verified |
| 7 | Observability | 5 Grafana dashboards, 5 alert rules, OpenLineage integration, Marquez lineage, telemetry listener | Built, Verified |
| 8 | Documentation + Stress Test | This README, ARCHITECTURE.md, runbooks, SLO documentation | In Progress |
| 9 | Self-Service Pipeline Factory | Config-driven pipeline generation: YAML definition -> auto-generated DAG + dbt staging model + Debezium connector | Planned |

## Runtime Environment

| Resource | Specification |
|---|---|
| EC2 instance | t3.2xlarge (8 vCPU, 32GB RAM) |
| Region | eu-north-1 (Stockholm) |
| Storage | 100GB EBS gp3 |
| Kubernetes | Kind 1 control-plane + 2 workers (K8s 1.31) |
| Access | All services via SSH tunnel (no public NodePorts) |

### Port Allocation

All ports are accessed through SSH tunnel. No services are exposed publicly.

| Service | NodePort |
|---|---|
| PostgreSQL | 30432 |
| MongoDB | 30017 |
| Kafka | 30092 |
| Schema Registry | 30081 |
| Kafka Connect | 30083 |
| ClickHouse HTTP | 30123 |
| ClickHouse Native | 30900 |
| MinIO S3 API | 30910 |
| MinIO Console | 30901 |
| Airflow UI | 30080 |
| Grafana | 30300 |
| Marquez API | 30500 |
| Marquez UI | 30301 |
| Spark UI | 30404 |

## Portfolio Context

This project targets **Data Engineer / Analytics Engineer / Data Platform Engineer** roles. It demonstrates end-to-end platform engineering: infrastructure provisioning, real-time and batch data ingestion, transformation, orchestration, data quality, observability, and lineage -- all deployed on Kubernetes with Infrastructure as Code.

**Certifications context:**
- AWS Solutions Architect Associate (SAA-C03)
- AWS Cloud Practitioner (CLF-C02)
- AWS AI Practitioner (AIF-C01)
- Terraform Associate (planned)
- dbt Analytics Engineering Certification (planned)

**Key engineering decisions demonstrated:**
- KRaft-mode Kafka (no ZooKeeper dependency) via Strimzi operator
- Custom Debezium SMT for PII hashing at the CDC layer (shift-left privacy)
- ClickHouse MergeTree family selection per layer (Kafka Engine, ReplacingMergeTree, AggregatingMergeTree)
- Delta Lake on MinIO for ACID batch storage with OPTIMIZE and VACUUM
- dbt project separation (clickhouse vs. spark) with shared source definitions
- Idempotent DAGs with quality gates (Great Expectations checkpoints block downstream)
- OpenLineage emission from Airflow and dbt into Marquez for cross-pipeline lineage
- Grafana dashboards and alerts provisioned as code (no manual UI configuration)
- Three Terraform environments (dev/staging/prod) with variable-driven resource sizing

## Author

**Tarig Elamin** -- Data Platform Engineer, Riyadh, KSA

- GitHub: [tarigelamin1997](https://github.com/tarigelamin1997)
- AWS SAA-C03 (823) | CLF-C02 (734) | AIF-C01
