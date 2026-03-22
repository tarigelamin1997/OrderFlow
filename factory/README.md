# OrderFlow Pipeline Factory

Phase 9 automation tool that generates a complete CDC ingestion pipeline
from a single YAML source definition.

## What It Does

The Pipeline Factory takes a declarative YAML file describing a source entity
(PostgreSQL table or MongoDB collection) and generates every artifact needed
to ingest that entity through the full OrderFlow pipeline:

```
YAML source definition
        |
        v
  pipeline_factory.py
        |
        +---> Debezium KafkaConnector CRD (YAML)
        +---> ClickHouse Bronze DDL (Kafka engine + raw + MV)
        +---> ClickHouse Silver DDL (ReplacingMergeTree / MergeTree)
        +---> dbt staging model + schema YAML
        +---> Airflow ingestion monitoring DAG
        +---> Schema snapshot JSON (drift detection)
        +---> apply.sh deployment script
```

## Architecture

```
+-------------------+     +-------------------+     +------------------+
|   YAML Source     |---->| Pipeline Factory  |---->| output/<entity>/ |
|   Definition      |     | (Jinja2 + Python) |     | (all artifacts)  |
+-------------------+     +-------------------+     +------------------+
                                  |
                                  v
                          +----------------+
                          |   Templates    |
                          | (*.json.j2)    |
                          | (produce YAML) |
                          +----------------+

apply.sh deploys artifacts to the cluster:

  +-----------+     +-------------+     +-------------+
  | ClickHouse|<----|  apply.sh   |---->|   Kafka     |
  | DDL       |     | (generated) |     | Connector   |
  +-----------+     +------+------+     +-------------+
                           |
              +------------+------------+
              |                         |
       +------v------+          +------v------+
       | dbt staging |          | Airflow DAG |
       | model copy  |          | tar pipe    |
       +-------------+          +-------------+
```

## Supported Source Types

| Source     | Connector           | Format        | Silver Engine         |
|------------|--------------------|--------------|-----------------------|
| PostgreSQL | Debezium PG        | AvroConfluent | ReplacingMergeTree    |
| MongoDB    | Debezium MongoDB   | JSONEachRow   | MergeTree (append)    |

## YAML Schema Reference

```yaml
source:
  name: <entity_name>          # Must match filename (without .yaml)
  type: postgres | mongodb     # Source database type
  connection:
    # PostgreSQL:
    database: orderflow        # PG database name
    schema: public             # PG schema
    table: <table_name>        # PG table
    server_name: orderflow     # Debezium server.name / topic prefix
    # MongoDB:
    database: orderflow        # Mongo database
    collection: <collection>   # Mongo collection
    server_name: orderflow-mongo

  columns:
    - name: id                 # Source column name
      type: serial             # Source type (PG or Mongo type)
      nullable: false          # Whether column can be NULL
      alias: payment_id        # Optional: rename in dbt staging
      pii: true                # Optional: mark for PII hashing

bronze:
  topic: <kafka_topic>         # Full Kafka topic name
  order_by: after_<pk>         # Bronze ORDER BY (flat naming)
  ttl_days: 30                 # Bronze retention in days

silver:
  engine: ReplacingMergeTree   # or MergeTree for append-only
  version_column: source_ts_ms # Version column for ReplacingMergeTree
  order_by: after_<pk>         # Silver ORDER BY
  partition_by: null           # Optional: PARTITION BY expression

dag:
  schedule: "@hourly"          # Airflow schedule interval
  owner: orderflow             # DAG owner
  retries: 2                   # Task retry count
  retry_delay_minutes: 5       # Minutes between retries
```

## Column Naming Convention

All source columns arrive in ClickHouse Bronze with the `after_` prefix due to
the Debezium Flatten SMT. The factory handles this mapping automatically:

- Source column `id` becomes `after_id` in Bronze and Silver
- Source column `order_id` becomes `after_order_id`
- The `alias` field in the YAML is used only in the dbt staging SELECT

## How to Use

### 1. Write the YAML source definition

Copy an example and customize:

```bash
cp factory/sources/_example_postgres.yaml factory/sources/my_entity.yaml
# Edit my_entity.yaml with your table details
```

### 2. Seed the source table (if new)

For new tables, create a seed SQL file and run it against PostgreSQL:

```bash
kubectl exec -n databases postgres-0 -- \
  psql -U orderflow -d orderflow -f - < factory/sources/my_entity_seed.sql
```

### 3. Generate the pipeline

```bash
make generate-pipeline ENTITY=my_entity
# Or directly:
python factory/pipeline_factory.py factory/sources/my_entity.yaml
```

### 4. Review generated artifacts

```bash
ls factory/output/my_entity/
```

### 5. Deploy

```bash
bash factory/output/my_entity/apply.sh
```

## Demo: Payments Pipeline

The `payments` entity is the Phase 9 demo. To run end-to-end:

```bash
# 1. Seed PostgreSQL with payments data
kubectl exec -n databases postgres-0 -- \
  psql -U orderflow -d orderflow -f - < factory/sources/payments_seed.sql

# 2. Generate all pipeline artifacts
python factory/pipeline_factory.py factory/sources/payments.yaml

# 3. Review output
ls factory/output/payments/

# 4. Deploy to cluster
bash factory/output/payments/apply.sh

# 5. Verify data is flowing
clickhouse-client --host localhost --port 30900 \
  --query "SELECT count() FROM bronze.payments_raw"
clickhouse-client --host localhost --port 30900 \
  --query "SELECT count() FROM silver.payments"
```

## Generated Artifacts

For each entity, the factory produces these files in `factory/output/<entity>/`:

| File                              | Purpose                                    |
|-----------------------------------|--------------------------------------------|
| `debezium_connector.yaml`         | Strimzi KafkaConnector CRD                 |
| `clickhouse_bronze_kafka.sql`     | Bronze Kafka engine table                  |
| `clickhouse_bronze_raw.sql`       | Bronze raw landing table (MergeTree)       |
| `clickhouse_bronze_mv.sql`        | Bronze MV: Kafka -> Raw                    |
| `clickhouse_silver.sql`           | Silver table (Replacing/MergeTree)         |
| `stg_<entity>.sql`                | dbt staging model (view)                   |
| `stg_<entity>_schema.yml`         | dbt schema tests                           |
| `orderflow_<entity>_ingestion.py` | Airflow monitoring DAG                     |
| `<entity>_schema_snapshot.json`   | Schema snapshot for drift detection        |
| `apply.sh`                        | One-command deployment script               |

## What Is NOT Generated

The factory handles Bronze-through-Staging only. The following require
manual creation (typically in later project phases):

- **Gold / mart tables** -- business logic varies per entity
- **Spark feature engineering** -- depends on analytical requirements
- **Grafana dashboards** -- monitoring panels are entity-specific
- **dbt intermediate / mart models** -- join logic is cross-entity
- **Great Expectations suites** -- data quality rules vary

## Key Deviations from Original Plan

These deviations are documented in the Phase 9 execution log:

1. **Connectors are Strimzi CRDs**, not REST API curl POST.
   `kubectl apply -f` is used instead of `curl -X POST`.

2. **DNS follows cluster conventions**:
   `postgres.databases.svc`, `schema-registry.kafka.svc`,
   `clickhouse.clickhouse.svc`, `minio.spark.svc`.

3. **PG passwords**: `debezium_pg_pass` for Debezium connectors,
   `orderflow_pg_pass` for direct PostgreSQL access.

4. **MongoDB**: no authentication, `directConnection=true`.

5. **Airflow is a StatefulSet** in the `airflow` namespace.
   DAGs are deployed by tar-piping files to the pod, not via ConfigMap.

6. **Template files** are named `.json.j2` but produce YAML output
   (Strimzi KafkaConnector CRDs).

## File Structure

```
factory/
  pipeline_factory.py           # Main generator class
  README.md                     # This file
  templates/
    debezium_postgres.json.j2   # PG connector CRD template
    debezium_mongo.json.j2      # Mongo connector CRD template
  sources/
    _example_postgres.yaml      # PG source example (copy to start)
    _example_mongo.yaml         # Mongo source example (copy to start)
    payments.yaml               # Demo: payments entity definition
    payments_seed.sql           # Demo: payments PG seed data
  output/
    <entity>/                   # Generated artifacts per entity
```
