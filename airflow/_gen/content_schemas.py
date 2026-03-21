"""Schema snapshot JSON content for Phase 6 drift detection.

These represent the expected silver.* column layout as of Phase 3 completion.
Stored under airflow/schema_snapshots/{entity}_schema.json.
"""
import json


def schema_orders() -> str:
    data = {
        "columns": [
            {"name": "id", "type": "Int32"},
            {"name": "user_id", "type": "Int32"},
            {"name": "restaurant_id", "type": "Int32"},
            {"name": "driver_id", "type": "Nullable(Int32)"},
            {"name": "status", "type": "LowCardinality(String)"},
            {"name": "total_amount", "type": "Float64"},
            {"name": "commission_earned", "type": "Float64"},
            {"name": "created_at_dt", "type": "DateTime"},
            {"name": "updated_at_dt", "type": "DateTime"},
            {"name": "ingested_at", "type": "DateTime"},
        ]
    }
    return json.dumps(data, indent=2)


def schema_users() -> str:
    data = {
        "columns": [
            {"name": "id", "type": "Int32"},
            {"name": "email_hash", "type": "String"},
            {"name": "name", "type": "String"},
            {"name": "city", "type": "String"},
            {"name": "created_at_dt", "type": "DateTime"},
            {"name": "updated_at_dt", "type": "DateTime"},
            {"name": "ingested_at", "type": "DateTime"},
        ]
    }
    return json.dumps(data, indent=2)


def schema_restaurants() -> str:
    data = {
        "columns": [
            {"name": "id", "type": "Int32"},
            {"name": "name", "type": "String"},
            {"name": "cuisine", "type": "LowCardinality(String)"},
            {"name": "city", "type": "String"},
            {"name": "rating", "type": "Float32"},
            {"name": "created_at_dt", "type": "DateTime"},
            {"name": "updated_at_dt", "type": "DateTime"},
            {"name": "ingested_at", "type": "DateTime"},
        ]
    }
    return json.dumps(data, indent=2)


def schema_drivers() -> str:
    data = {
        "columns": [
            {"name": "id", "type": "Int32"},
            {"name": "name", "type": "String"},
            {"name": "phone_hash", "type": "String"},
            {"name": "city", "type": "String"},
            {"name": "vehicle_type", "type": "LowCardinality(String)"},
            {"name": "created_at_dt", "type": "DateTime"},
            {"name": "updated_at_dt", "type": "DateTime"},
            {"name": "ingested_at", "type": "DateTime"},
        ]
    }
    return json.dumps(data, indent=2)


def schema_user_events() -> str:
    data = {
        "columns": [
            {"name": "id", "type": "Int32"},
            {"name": "user_id", "type": "Int32"},
            {"name": "event_type", "type": "LowCardinality(String)"},
            {"name": "event_payload", "type": "String"},
            {"name": "event_ts_dt", "type": "DateTime"},
            {"name": "ingested_at", "type": "DateTime"},
        ]
    }
    return json.dumps(data, indent=2)


def schema_delivery_updates() -> str:
    data = {
        "columns": [
            {"name": "id", "type": "Int32"},
            {"name": "order_id", "type": "Int32"},
            {"name": "driver_id", "type": "Int32"},
            {"name": "status", "type": "LowCardinality(String)"},
            {"name": "location_lat", "type": "Nullable(Float64)"},
            {"name": "location_lon", "type": "Nullable(Float64)"},
            {"name": "updated_at_dt", "type": "DateTime"},
            {"name": "ingested_at", "type": "DateTime"},
        ]
    }
    return json.dumps(data, indent=2)
