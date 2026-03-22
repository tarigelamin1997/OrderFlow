import pytest
import json
from pathlib import Path
from unittest.mock import patch
import sys
import os

# Add factory directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from factory.pipeline_factory import PipelineFactory


@pytest.fixture(autouse=True)
def mock_connector_validation():
    """Skip connector name validation in tests (no Kafka Connect available)."""
    with patch.object(PipelineFactory, '_validate_connector_name'):
        yield


def test_postgres_source_generates_all_artifacts():
    factory = PipelineFactory("factory/sources/payments.yaml")
    factory.generate_all()
    output = Path("factory/output/payments")
    assert (output / "debezium_connector.yaml").exists()
    assert (output / "clickhouse_bronze_kafka.sql").exists()
    assert (output / "clickhouse_bronze_raw.sql").exists()
    assert (output / "clickhouse_bronze_mv.sql").exists()
    assert (output / "clickhouse_silver.sql").exists()
    assert (output / "stg_payments.sql").exists()
    assert (output / "stg_payments_schema.yml").exists()
    assert (output / "orderflow_payments_ingestion.py").exists()
    assert (output / "payments_schema_snapshot.json").exists()
    assert (output / "apply.sh").exists()


def test_pii_columns_trigger_hashpii_transform():
    factory = PipelineFactory("factory/sources/payments.yaml")
    factory.generate_debezium_connector()
    content = (Path("factory/output/payments/debezium_connector.yaml")).read_text()
    assert "HashPII" in content
    assert "card_last_four" in content


def test_generated_silver_ddl_is_valid():
    factory = PipelineFactory("factory/sources/payments.yaml")
    factory.generate_clickhouse_silver()
    ddl = (Path("factory/output/payments/clickhouse_silver.sql")).read_text()
    assert "CREATE TABLE IF NOT EXISTS silver.payments" in ddl
    assert "ReplacingMergeTree" in ddl


def test_dbt_model_has_correct_materialization():
    factory = PipelineFactory("factory/sources/payments.yaml")
    factory.generate_dbt_staging()
    model = (Path("factory/output/payments/stg_payments.sql")).read_text()
    assert "materialized='view'" in model
    assert "source('silver', 'payments')" in model
