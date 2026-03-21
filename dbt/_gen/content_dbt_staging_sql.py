"""Staging SQL models for dbt/orderflow_clickhouse/models/staging/."""


def stg_orders_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/models/staging/stg_orders.sql
-- Phase 5 -- active order records from silver layer.
-- FINAL ensures latest version per order_id for ReplacingMergeTree.
-- is_deleted = 0 excludes soft-deleted rows propagated from CDC DELETEs.
{{ config(materialized='view') }}

SELECT
    id                              AS order_id,
    user_id,
    restaurant_id,
    driver_id,
    status,
    total_amount,
    created_at_dt,
    updated_at_dt,
    op,
    source_lsn,
    _bronze_ts,
    _silver_at
FROM {{ source('silver', 'orders') }} FINAL
WHERE is_deleted = 0
"""


def stg_users_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/models/staging/stg_users.sql
-- Phase 5 -- active user records from silver layer.
{{ config(materialized='view') }}

SELECT
    id              AS user_id,
    name,
    email_hash,
    phone_hash,
    city,
    created_at_dt,
    updated_at_dt,
    op,
    _bronze_ts,
    _silver_at
FROM {{ source('silver', 'users') }} FINAL
WHERE is_deleted = 0
"""


def stg_restaurants_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/models/staging/stg_restaurants.sql
-- Phase 5 -- active restaurant records from silver layer.
-- No active column in source; is_deleted=0 is the only exclusion filter.
{{ config(materialized='view') }}

SELECT
    id              AS restaurant_id,
    name,
    cuisine,
    city,
    rating,
    commission_rate,
    created_at_dt,
    updated_at_dt,
    op,
    _bronze_ts,
    _silver_at
FROM {{ source('silver', 'restaurants') }} FINAL
WHERE is_deleted = 0
"""


def stg_drivers_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/models/staging/stg_drivers.sql
-- Phase 5 -- active driver records from silver layer.
-- vehicle_type is the correct column (not license).
{{ config(materialized='view') }}

SELECT
    id              AS driver_id,
    name,
    phone_hash,
    city,
    rating,
    vehicle_type,
    created_at_dt,
    updated_at_dt,
    op,
    _bronze_ts,
    _silver_at
FROM {{ source('silver', 'drivers') }} FINAL
WHERE is_deleted = 0
"""


def stg_user_events_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/models/staging/stg_user_events.sql
-- Phase 5 -- user behavioural events from silver layer.
-- MergeTree (append-only): no FINAL, no is_deleted filter.
{{ config(materialized='view') }}

SELECT
    event_id,
    user_id,
    event_type,
    page,
    session_id,
    device,
    os,
    event_timestamp,
    schema_version,
    op,
    _bronze_ts,
    _silver_at
FROM {{ source('silver', 'user_events') }}
"""


def stg_delivery_updates_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/models/staging/stg_delivery_updates.sql
-- Phase 5 -- driver location update events from silver layer.
-- MergeTree (append-only): no FINAL, no is_deleted filter.
{{ config(materialized='view') }}

SELECT
    update_id,
    order_id,
    driver_id,
    delivery_status,
    lat,
    lng,
    accuracy,
    update_timestamp,
    op,
    _bronze_ts,
    _silver_at
FROM {{ source('silver', 'delivery_updates') }}
"""
