"""
OrderFlow Pipeline Factory — Phase 9
Generates all artifacts needed for a new CDC entity pipeline from a YAML source definition.

Artifacts generated:
  - Debezium KafkaConnector CRD (YAML)
  - ClickHouse Bronze (Kafka engine + raw table + MV)
  - ClickHouse Silver (ReplacingMergeTree or MergeTree)
  - dbt staging model + schema YAML
  - Airflow ingestion DAG
  - Schema snapshot JSON
  - apply.sh deployment script

Deviations from original plan:
  - Connectors are Strimzi KafkaConnector CRDs (kubectl apply), not REST API curl POST
  - DNS: postgres.databases.svc, schema-registry.kafka.svc, clickhouse.clickhouse.svc
  - PG password: debezium_pg_pass (Debezium), orderflow_pg_pass (direct PG access)
  - MongoDB: no auth, directConnection=true
  - Airflow is StatefulSet in airflow namespace; DAGs delivered via tar pipe copy
  - Template files are .json.j2 by name but produce YAML (Strimzi CRDs)
  - Bronze columns use flat naming: after_id, after_name, etc.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FACTORY_ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = FACTORY_ROOT / "templates"
OUTPUT_BASE = FACTORY_ROOT / "output"
REPO_ROOT = FACTORY_ROOT.parent

# ClickHouse connection (via SSH tunnel)
CH_HOST = "localhost"
CH_PORT = "30900"

# Kafka / Schema Registry DNS inside cluster
SCHEMA_REGISTRY_URL = "http://schema-registry.kafka.svc.cluster.local:8081"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flat_column_name(col_name: str) -> str:
    """Convert a source column name to flat bronze naming: after_{col}."""
    return f"after_{col_name}"


def _ch_type(source_type: str) -> str:
    """Map source (PG / Mongo) types to ClickHouse types."""
    mapping = {
        # PostgreSQL types
        "serial": "Int64",
        "integer": "Int32",
        "bigint": "Int64",
        "smallint": "Int16",
        "boolean": "UInt8",
        "text": "String",
        "varchar": "String",
        "char": "String",
        "numeric": "Float64",
        "decimal": "Float64",
        "real": "Float32",
        "double precision": "Float64",
        "timestamp": "String",
        "timestamptz": "String",
        "timestamp with time zone": "String",
        "timestamp without time zone": "String",
        "date": "String",
        "json": "String",
        "jsonb": "String",
        "uuid": "String",
        # MongoDB types
        "string": "String",
        "int": "Int32",
        "long": "Int64",
        "double": "Float64",
        "bool": "UInt8",
        "objectId": "String",
        "datetime": "String",
        "object": "String",
        "array": "String",
    }
    # Strip parenthetical precision (e.g., "numeric(10,2)" → "numeric")
    base_type = source_type.split("(")[0].strip().lower()
    return mapping.get(base_type, "String")


def _ch_type_nullable(source_type: str, nullable: bool) -> str:
    """Return ClickHouse type, wrapped in Nullable if needed."""
    base = _ch_type(source_type)
    if nullable:
        return f"Nullable({base})"
    return base


def _dbt_type(source_type: str) -> str:
    """Map source types to dbt test-friendly type names."""
    mapping = {
        "serial": "integer",
        "integer": "integer",
        "bigint": "integer",
        "smallint": "integer",
        "boolean": "boolean",
        "numeric": "number",
        "decimal": "number",
        "real": "number",
        "double precision": "number",
        "float64": "number",
        "int32": "integer",
        "int64": "integer",
    }
    return mapping.get(source_type.lower(), "string")


# ---------------------------------------------------------------------------
# PipelineFactory
# ---------------------------------------------------------------------------

class PipelineFactory:
    """Generates all pipeline artifacts from a YAML source definition."""

    def __init__(self, source_yaml_path: str):
        self.source_path = Path(source_yaml_path).resolve()
        if not self.source_path.exists():
            raise FileNotFoundError(f"Source YAML not found: {self.source_path}")

        with open(self.source_path, "r", encoding="utf-8") as f:
            self.config: Dict[str, Any] = yaml.safe_load(f)

        # Normalize: columns can be at top level (plan schema) or under source
        if "columns" in self.config and "columns" not in self.config.get("source", {}):
            self.config["source"]["columns"] = self.config["columns"]
        elif "columns" not in self.config and "columns" in self.config.get("source", {}):
            self.config["columns"] = self.config["source"]["columns"]

        self._validate_config()

        self.entity = self.config["source"]["name"]
        self.source_type = self.config["source"]["type"]
        self.output_dir = OUTPUT_BASE / self.entity
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Jinja2 environment — StrictUndefined so missing vars fail loudly
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )

    # ------------------------------------------------------------------
    # Config validation
    # ------------------------------------------------------------------

    def _validate_config(self) -> None:
        """Validate required keys in the YAML source definition."""
        required_top = ["source", "silver"]
        for key in required_top:
            if key not in self.config:
                raise ValueError(f"Missing required top-level key: '{key}'")

        src = self.config["source"]
        for key in ["name", "type", "connection", "columns"]:
            if key not in src:
                raise ValueError(f"Missing required source key: '{key}'")

        if src["type"] not in ("postgres", "mongodb"):
            raise ValueError(
                f"Unsupported source type: '{src['type']}'. "
                "Supported: postgres, mongodb"
            )

        if not src["columns"]:
            raise ValueError("source.columns must contain at least one column")

        # Validate column definitions
        for col in src["columns"]:
            if "name" not in col:
                raise ValueError(f"Column missing required field 'name': {col}")
            # Accept either 'type' or 'source_type' for compatibility
            if "type" not in col and "source_type" in col:
                col["type"] = col["source_type"]
            elif "type" not in col:
                raise ValueError(f"Column missing 'type' or 'source_type': {col}")

    # ------------------------------------------------------------------
    # Connector name validation
    # ------------------------------------------------------------------

    def _validate_connector_name(self) -> None:
        """Check that connector name does not already exist in the cluster."""
        if self.source_type == "postgres":
            connector_name = f"orderflow-postgres-source-{self.entity}"
        else:
            connector_name = f"orderflow-mongo-source-{self.entity}"

        try:
            result = subprocess.run(
                ["kubectl", "get", "kafkaconnector", "-n", "kafka",
                 "-o", "jsonpath={.items[*].metadata.name}"],
                capture_output=True, text=True, timeout=30,
            )
            existing = result.stdout.strip().split()
            if connector_name in existing:
                raise ValueError(
                    f"Connector '{connector_name}' already exists in namespace 'kafka'. "
                    "Delete it first or choose a different entity name."
                )
        except FileNotFoundError:
            print("WARNING: kubectl not found — skipping connector name validation")
        except subprocess.TimeoutExpired:
            print("WARNING: kubectl timed out — skipping connector name validation")

    # ------------------------------------------------------------------
    # Generate all artifacts
    # ------------------------------------------------------------------

    def generate_all(self) -> None:
        """Run the full generation pipeline."""
        print(f"Generating pipeline for entity: {self.entity}")
        print(f"Source type: {self.source_type}")
        print(f"Output directory: {self.output_dir}")
        print()

        self._validate_connector_name()
        self.generate_debezium_connector()
        self.generate_clickhouse_bronze()
        self.generate_clickhouse_silver()
        self.generate_dbt_staging()
        self.generate_airflow_dag()
        self.generate_schema_snapshot()
        self.generate_apply_script()

        print()
        print(f"All artifacts generated in: {self.output_dir}")

    # ------------------------------------------------------------------
    # Debezium connector (Strimzi KafkaConnector CRD — YAML)
    # ------------------------------------------------------------------

    def generate_debezium_connector(self) -> None:
        """Generate Debezium connector CRD from Jinja2 template."""
        if self.source_type == "postgres":
            template_name = "debezium_postgres.json.j2"
        else:
            template_name = "debezium_mongo.json.j2"

        # PII column names WITHOUT after_ prefix — HashPII runs BEFORE Flatten
        pii_columns = [
            col["name"]
            for col in self.config["source"]["columns"]
            if col.get("pii", False)
        ]

        template = self.jinja_env.get_template(template_name)
        rendered = template.render(
            config=self.config,
            pii_columns=pii_columns,
        )

        out_path = self.output_dir / "debezium_connector.yaml"
        out_path.write_text(rendered, encoding="utf-8")
        print(f"  [OK] {out_path.name}")

    # ------------------------------------------------------------------
    # ClickHouse Bronze
    # ------------------------------------------------------------------

    def generate_clickhouse_bronze(self) -> None:
        """Generate ClickHouse Bronze DDL: Kafka engine, raw table, MV."""
        src = self.config["source"]
        bronze_cfg = self.config.get("bronze", {})
        columns = src["columns"]
        entity = self.entity
        conn = src["connection"]

        topic = bronze_cfg.get("topic", f"{conn.get('server_name', entity)}.{conn.get('schema', 'public')}.{conn.get('table', entity)}")

        # -- Column definitions for bronze (flat naming) --
        kafka_cols = []
        raw_cols = []
        mv_select_cols = []
        for col in columns:
            flat_name = _flat_column_name(col["name"])
            nullable = col.get("nullable", True)
            ch_type = _ch_type_nullable(col["type"], nullable)
            kafka_cols.append(f"    {flat_name} {ch_type}")
            raw_cols.append(f"    {flat_name} {ch_type}")
            mv_select_cols.append(f"        {flat_name}")

        # CDC metadata columns
        cdc_meta_kafka = [
            "    op String",
            "    source_ts_ms Nullable(Int64)",
            "    source_lsn Nullable(Int64)",
        ]
        cdc_meta_raw = list(cdc_meta_kafka) + [
            "    _bronze_ts DateTime DEFAULT now()",
        ]
        cdc_meta_mv_select = [
            "        op",
            "        source_ts_ms",
            "        source_lsn",
            "        now() AS _bronze_ts",
        ]

        # -- 1. Kafka engine table --
        if self.source_type == "postgres":
            kafka_format = "AvroConfluent"
            kafka_settings = [
                f"    kafka_broker_list = 'orderflow-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092'",
                f"    kafka_topic_list = '{topic}'",
                f"    kafka_group_name = 'clickhouse_bronze_{entity}'",
                f"    kafka_format = '{kafka_format}'",
                f"    format_avro_schema_registry_url = '{SCHEMA_REGISTRY_URL}'",
            ]
        else:
            kafka_format = "JSONEachRow"
            kafka_settings = [
                f"    kafka_broker_list = 'orderflow-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092'",
                f"    kafka_topic_list = '{topic}'",
                f"    kafka_group_name = 'clickhouse_bronze_{entity}'",
                f"    kafka_format = '{kafka_format}'",
            ]

        kafka_ddl = (
            f"-- Auto-generated by OrderFlow Pipeline Factory\n"
            f"-- Entity: {entity} | Source: {self.source_type}\n"
            f"CREATE TABLE IF NOT EXISTS bronze.{entity}_kafka\n"
            f"(\n"
            + ",\n".join(kafka_cols + cdc_meta_kafka) + "\n"
            f")\n"
            f"ENGINE = Kafka\n"
            f"SETTINGS\n"
            + ",\n".join(kafka_settings) + ";\n"
        )

        kafka_path = self.output_dir / "clickhouse_bronze_kafka.sql"
        kafka_path.write_text(kafka_ddl, encoding="utf-8")
        print(f"  [OK] {kafka_path.name}")

        # -- 2. Raw (landing) table --
        order_by = bronze_cfg.get("order_by", _flat_column_name(columns[0]["name"]))
        raw_ddl = (
            f"-- Auto-generated by OrderFlow Pipeline Factory\n"
            f"-- Entity: {entity} | Bronze raw landing table\n"
            f"CREATE TABLE IF NOT EXISTS bronze.{entity}_raw\n"
            f"(\n"
            + ",\n".join(raw_cols + cdc_meta_raw) + "\n"
            f")\n"
            f"ENGINE = MergeTree()\n"
            f"ORDER BY ({order_by})\n"
            f"TTL _bronze_ts + INTERVAL {bronze_cfg.get('ttl_days', 30)} DAY\n"
            f"SETTINGS allow_nullable_key = 1;\n"
        )

        raw_path = self.output_dir / "clickhouse_bronze_raw.sql"
        raw_path.write_text(raw_ddl, encoding="utf-8")
        print(f"  [OK] {raw_path.name}")

        # -- 3. Materialized View --
        all_mv_cols = mv_select_cols + cdc_meta_mv_select
        mv_ddl = (
            f"-- Auto-generated by OrderFlow Pipeline Factory\n"
            f"-- Entity: {entity} | Bronze MV: Kafka -> Raw\n"
            f"CREATE MATERIALIZED VIEW IF NOT EXISTS bronze.{entity}_mv\n"
            f"TO bronze.{entity}_raw\n"
            f"AS SELECT\n"
            + ",\n".join(all_mv_cols) + "\n"
            f"FROM bronze.{entity}_kafka;\n"
        )

        mv_path = self.output_dir / "clickhouse_bronze_mv.sql"
        mv_path.write_text(mv_ddl, encoding="utf-8")
        print(f"  [OK] {mv_path.name}")

    # ------------------------------------------------------------------
    # ClickHouse Silver
    # ------------------------------------------------------------------

    def generate_clickhouse_silver(self) -> None:
        """Generate ClickHouse Silver table DDL with clean column names."""
        silver_cfg = self.config["silver"]
        columns = self.config["columns"]
        entity = self.entity

        engine = silver_cfg.get("engine", "ReplacingMergeTree")
        ver_col = silver_cfg.get("version_column", "updated_at_dt")
        order_by_cols = silver_cfg.get("order_by", [columns[0]["name"]])
        if isinstance(order_by_cols, str):
            order_by_cols = [order_by_cols]
        partition_by = silver_cfg.get("partition_by")

        # Silver uses clean column names (not after_* Bronze naming)
        silver_cols = []
        for col in columns:
            name = col["name"]
            ch_type = col.get("clickhouse_type", "String")
            if col.get("pii"):
                silver_cols.append(f"    {name}_hash {ch_type}")
            elif col.get("is_timestamp"):
                silver_cols.append(f"    {name}_dt DateTime")
            elif col.get("source_is_decimal"):
                silver_cols.append(f"    {name} {ch_type}")
            else:
                silver_cols.append(f"    {name} {ch_type}")

        silver_cols.append("    is_deleted UInt8 DEFAULT 0")
        # Only add default updated_at_dt if no timestamp column already creates it
        has_updated_at = any(
            c["name"] == "updated_at" and c.get("is_timestamp")
            for c in columns
        )
        if not has_updated_at:
            silver_cols.append("    updated_at_dt DateTime DEFAULT now()")

        # Build engine clause
        if engine == "ReplacingMergeTree":
            engine_clause = f"ENGINE = ReplacingMergeTree({ver_col})"
        else:
            engine_clause = f"ENGINE = {engine}()"

        partition_clause = ""
        if partition_by:
            partition_clause = f"\nPARTITION BY {partition_by}"

        order_by_str = ", ".join(order_by_cols)

        silver_ddl = (
            f"-- Auto-generated by OrderFlow Pipeline Factory\n"
            f"-- Entity: {entity} | Silver table\n"
            f"CREATE TABLE IF NOT EXISTS silver.{entity}\n"
            f"(\n"
            + ",\n".join(silver_cols) + "\n"
            f")\n"
            f"{engine_clause}\n"
            f"ORDER BY ({order_by_str})"
            f"{partition_clause}\n"
            f"SETTINGS allow_nullable_key = 1, index_granularity = 8192;\n"
        )

        # Build Bronze-to-Silver MV (transforms after_* flat columns to clean Silver)
        mv_select = []
        for col in columns:
            name = col["name"]
            if col.get("pii"):
                # PII already hashed by Debezium HashPII SMT
                mv_select.append(f"    after_{name} AS {name}_hash")
            elif col.get("is_timestamp"):
                # Convert ms epoch (Int64) or String to DateTime
                mv_select.append(
                    f"    toDateTime(toInt64OrZero(toString(after_{name})) / 1000) AS {name}_dt"
                )
            elif col.get("source_is_decimal"):
                mv_select.append(f"    toDecimal64(after_{name}, 2) AS {name}")
            else:
                mv_select.append(f"    after_{name} AS {name}")

        mv_select.append("    0 AS is_deleted")
        # Only add default updated_at_dt in MV if no timestamp column creates it
        has_updated_at = any(
            c["name"] == "updated_at" and c.get("is_timestamp")
            for c in columns
        )
        if not has_updated_at:
            mv_select.append("    now() AS updated_at_dt")

        mv_ddl = (
            f"\n-- Bronze-to-Silver MV\n"
            f"CREATE MATERIALIZED VIEW IF NOT EXISTS bronze.{entity}_to_silver_mv\n"
            f"TO silver.{entity}\n"
            f"AS SELECT\n"
            + ",\n".join(mv_select) + "\n"
            f"FROM bronze.{entity}_kafka;\n"
        )

        silver_ddl += mv_ddl

        silver_path = self.output_dir / "clickhouse_silver.sql"
        silver_path.write_text(silver_ddl, encoding="utf-8")
        print(f"  [OK] {silver_path.name}")

    # ------------------------------------------------------------------
    # dbt staging model
    # ------------------------------------------------------------------

    def generate_dbt_staging(self) -> None:
        """Generate dbt staging SQL model and schema YAML."""
        src = self.config["source"]
        silver_cfg = self.config["silver"]
        columns = src["columns"]
        entity = self.entity

        engine = silver_cfg.get("engine", "ReplacingMergeTree")
        is_append_only = engine == "MergeTree"

        # Build SELECT columns
        select_lines = []
        for col in columns:
            flat_name = _flat_column_name(col["name"])
            alias = col.get("alias", col["name"])
            if flat_name != alias:
                select_lines.append(f"    {flat_name} AS {alias}")
            else:
                select_lines.append(f"    {flat_name}")

        # Always include metadata
        select_lines.extend([
            "    op",
            "    source_lsn",
            "    _bronze_ts",
            "    _silver_at",
        ])

        final_kw = "" if is_append_only else " FINAL"
        where_clause = "" if is_append_only else "\nWHERE is_deleted = 0"

        model_sql = (
            f"-- Auto-generated by OrderFlow Pipeline Factory\n"
            f"-- dbt staging model for silver.{entity}\n"
            f"{{{{ config(materialized='view') }}}}\n"
            f"\n"
            f"SELECT\n"
            + ",\n".join(select_lines) + "\n"
            f"FROM {{{{ source('silver', '{entity}') }}}}{final_kw}"
            f"{where_clause}\n"
        )

        sql_path = self.output_dir / f"stg_{entity}.sql"
        sql_path.write_text(model_sql, encoding="utf-8")
        print(f"  [OK] {sql_path.name}")

        # -- Schema YAML --
        pk_col = columns[0].get("alias", columns[0]["name"])
        schema_yml = (
            f"# Auto-generated by OrderFlow Pipeline Factory\n"
            f"version: 2\n"
            f"\n"
            f"models:\n"
            f"  - name: stg_{entity}\n"
            f"    description: \"Staging view over silver.{entity}\"\n"
            f"    columns:\n"
            f"      - name: {pk_col}\n"
            f"        tests:\n"
            f"          - not_null\n"
        )

        if not is_append_only:
            schema_yml += f"          - unique\n"

        yml_path = self.output_dir / f"stg_{entity}_schema.yml"
        yml_path.write_text(schema_yml, encoding="utf-8")
        print(f"  [OK] {yml_path.name}")

    # ------------------------------------------------------------------
    # Airflow DAG
    # ------------------------------------------------------------------

    def generate_airflow_dag(self) -> None:
        """Generate an Airflow ingestion DAG for the entity."""
        entity = self.entity
        src = self.config["source"]
        dag_cfg = self.config.get("dag", {})

        schedule = dag_cfg.get("schedule", "@hourly")
        owner = dag_cfg.get("owner", "orderflow")
        retries = dag_cfg.get("retries", 2)
        retry_delay_min = dag_cfg.get("retry_delay_minutes", 5)

        # Build connectivity check based on source type
        if self.source_type == "postgres":
            conn_check = (
                f"    check = BashOperator(\n"
                f"        task_id='check_{entity}_connector',\n"
                f"        bash_command=(\n"
                f"            'kubectl get kafkaconnector '\n"
                f"            'orderflow-postgres-source-{entity} '\n"
                f"            '-n kafka -o jsonpath=\"{{.status.connectorStatus.connector.state}}\" '\n"
                f"            '| grep -q RUNNING'\n"
                f"        ),\n"
                f"    )\n"
            )
        else:
            conn_check = (
                f"    check = BashOperator(\n"
                f"        task_id='check_{entity}_connector',\n"
                f"        bash_command=(\n"
                f"            'kubectl get kafkaconnector '\n"
                f"            'orderflow-mongo-source-{entity} '\n"
                f"            '-n kafka -o jsonpath=\"{{.status.connectorStatus.connector.state}}\" '\n"
                f"            '| grep -q RUNNING'\n"
                f"        ),\n"
                f"    )\n"
            )

        dag_content = (
            f'"""\n'
            f"Auto-generated by OrderFlow Pipeline Factory\n"
            f"Airflow DAG: {entity} ingestion monitoring\n"
            f'"""\n'
            f"from datetime import datetime, timedelta\n"
            f"\n"
            f"from airflow import DAG\n"
            f"from airflow.operators.bash import BashOperator\n"
            f"from airflow.operators.python import PythonOperator\n"
            f"\n"
            f"default_args = {{\n"
            f"    'owner': '{owner}',\n"
            f"    'depends_on_past': False,\n"
            f"    'retries': {retries},\n"
            f"    'retry_delay': timedelta(minutes={retry_delay_min}),\n"
            f"}}\n"
            f"\n"
            f"with DAG(\n"
            f"    dag_id='orderflow_{entity}_ingestion',\n"
            f"    default_args=default_args,\n"
            f"    description='Ingestion monitoring for {entity} pipeline',\n"
            f"    schedule_interval='{schedule}',\n"
            f"    start_date=datetime(2024, 1, 1),\n"
            f"    catchup=False,\n"
            f"    tags=['orderflow', 'ingestion', '{entity}', 'factory-generated'],\n"
            f") as dag:\n"
            f"\n"
            f"{conn_check}\n"
            f"    freshness = BashOperator(\n"
            f"        task_id='check_{entity}_freshness',\n"
            f"        bash_command=(\n"
            f"            \"clickhouse-client --host localhost --port 30900 \"\n"
            f"            \"--query \\\"SELECT countIf(_bronze_ts > now() - INTERVAL 1 HOUR) \"\n"
            f"            \"FROM bronze.{entity}_raw\\\" \"\n"
            f"            \"| awk '{{if ($1 < 1) exit 1}}'\"\n"
            f"        ),\n"
            f"    )\n"
            f"\n"
            f"    row_count = BashOperator(\n"
            f"        task_id='check_{entity}_silver_count',\n"
            f"        bash_command=(\n"
            f"            \"clickhouse-client --host localhost --port 30900 \"\n"
            f"            \"--query \\\"SELECT count() FROM silver.{entity}\\\" \"\n"
            f"            \"| awk '{{if ($1 < 1) exit 1}}'\"\n"
            f"        ),\n"
            f"    )\n"
            f"\n"
            f"    check >> freshness >> row_count\n"
        )

        dag_path = self.output_dir / f"orderflow_{entity}_ingestion.py"
        dag_path.write_text(dag_content, encoding="utf-8")
        print(f"  [OK] {dag_path.name}")

    # ------------------------------------------------------------------
    # Schema snapshot
    # ------------------------------------------------------------------

    def generate_schema_snapshot(self) -> None:
        """Generate a JSON schema snapshot for drift detection."""
        src = self.config["source"]
        columns = src["columns"]
        entity = self.entity

        snapshot = {
            "entity": entity,
            "source_type": self.source_type,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "OrderFlow Pipeline Factory v1.0",
            "columns": [
                {
                    "name": col["name"],
                    "flat_name": _flat_column_name(col["name"]),
                    "source_type": col["type"],
                    "clickhouse_type": _ch_type(col["type"]),
                    "nullable": col.get("nullable", True),
                    "pii": col.get("pii", False),
                }
                for col in columns
            ],
        }

        snap_path = self.output_dir / f"{entity}_schema_snapshot.json"
        snap_path.write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"  [OK] {snap_path.name}")

    # ------------------------------------------------------------------
    # Apply script
    # ------------------------------------------------------------------

    def generate_apply_script(self) -> None:
        """Generate the deployment script (apply.sh)."""
        entity = self.entity

        script = (
            f"#!/bin/bash\n"
            f"set -euo pipefail\n"
            f'ENTITY="{entity}"\n'
            f'OUTPUT_DIR="factory/output/$ENTITY"\n'
            f"\n"
            f'echo "=== Deploying pipeline for: $ENTITY ==="\n'
            f"\n"
            f"# 1. Apply ClickHouse DDL\n"
            f'echo "Step 1: ClickHouse Bronze + Silver tables..."\n'
            f'clickhouse-client --host localhost --port 30900 --multiquery < "$OUTPUT_DIR/clickhouse_bronze_kafka.sql"\n'
            f'clickhouse-client --host localhost --port 30900 --multiquery < "$OUTPUT_DIR/clickhouse_bronze_raw.sql"\n'
            f'clickhouse-client --host localhost --port 30900 --multiquery < "$OUTPUT_DIR/clickhouse_silver.sql"\n'
            f'clickhouse-client --host localhost --port 30900 --multiquery < "$OUTPUT_DIR/clickhouse_bronze_mv.sql"\n'
            f'echo "  Done"\n'
            f"\n"
            f"# 2. Register Debezium connector (KafkaConnector CRD)\n"
            f'echo "Step 2: Debezium connector..."\n'
            f'kubectl apply -f "$OUTPUT_DIR/debezium_connector.yaml"\n'
            f'echo "  Done"\n'
            f"\n"
            f"# 3. Copy dbt staging model\n"
            f'echo "Step 3: dbt staging model..."\n'
            f'cp "$OUTPUT_DIR/stg_$ENTITY.sql" dbt/orderflow_clickhouse/models/staging/\n'
            f'cp "$OUTPUT_DIR/stg_${{ENTITY}}_schema.yml" dbt/orderflow_clickhouse/models/staging/\n'
            f'echo "  Done"\n'
            f"\n"
            f"# 4. Copy schema snapshot\n"
            f'echo "Step 4: Schema snapshot..."\n'
            f"mkdir -p airflow/schema_snapshots\n"
            f'cp "$OUTPUT_DIR/${{ENTITY}}_schema_snapshot.json" airflow/schema_snapshots/\n'
            f'echo "  Done"\n'
            f"\n"
            f"# 5. Deploy DAG to Airflow pod\n"
            f'echo "Step 5: Airflow DAG..."\n'
            f'cp "$OUTPUT_DIR/orderflow_${{ENTITY}}_ingestion.py" airflow/dags/\n'
            f"cd airflow/dags && tar cf - *.py | kubectl exec -n airflow airflow-0 -c airflow-webserver -i -- tar xf - -C /opt/airflow/dags/ && cd ../..\n"
            f'echo "  Done"\n'
            f"\n"
            f"# 6. Restart Airflow to pick up new DAG\n"
            f"kubectl rollout restart statefulset/airflow -n airflow\n"
            f"\n"
            f'echo "=== Pipeline for $ENTITY deployed ==="\n'
        )

        script_path = self.output_dir / "apply.sh"
        script_path.write_text(script, encoding="utf-8")
        # Make executable
        os.chmod(script_path, 0o755)
        print(f"  [OK] {script_path.name}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI: python pipeline_factory.py <source.yaml>"""
    if len(sys.argv) < 2:
        print("Usage: python pipeline_factory.py <source.yaml>")
        print("       python pipeline_factory.py factory/sources/payments.yaml")
        sys.exit(1)

    source_yaml = sys.argv[1]
    factory = PipelineFactory(source_yaml)
    factory.generate_all()


if __name__ == "__main__":
    main()
