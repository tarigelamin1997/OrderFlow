"""Intermediate (ephemeral) SQL models for dbt/orderflow_clickhouse/models/intermediate/."""


def int_orders_enriched_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/models/intermediate/int_orders_enriched.sql
-- Phase 5 -- ephemeral CTE joining orders with restaurant and user dimensions.
-- Ephemeral: inlined by dbt at compile time; no table is created in ClickHouse.
{{ config(materialized='ephemeral') }}

WITH orders AS (
    SELECT * FROM {{ ref('stg_orders') }}
),
restaurants AS (
    SELECT
        restaurant_id,
        name            AS restaurant_name,
        cuisine,
        city            AS restaurant_city,
        commission_rate
    FROM {{ ref('stg_restaurants') }}
),
users AS (
    SELECT
        user_id,
        city            AS user_city
    FROM {{ ref('stg_users') }}
)

SELECT
    o.order_id,
    o.user_id,
    o.restaurant_id,
    o.driver_id,
    o.status,
    o.total_amount,
    o.created_at_dt,
    o.updated_at_dt,
    r.restaurant_name,
    r.cuisine,
    r.restaurant_city,
    r.commission_rate,
    u.user_city,
    -- Commission earned by platform on this order
    round(o.total_amount * coalesce(r.commission_rate, 0), 2) AS commission_earned
FROM orders o
LEFT JOIN restaurants r USING (restaurant_id)
LEFT JOIN users u USING (user_id)
"""


def int_driver_deliveries_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/models/intermediate/int_driver_deliveries.sql
-- Phase 5 -- ephemeral CTE: completed deliveries with driver context.
{{ config(materialized='ephemeral') }}

WITH delivered_orders AS (
    SELECT
        order_id,
        driver_id,
        restaurant_id,
        total_amount,
        created_at_dt,
        toDate(created_at_dt) AS delivery_date
    FROM {{ ref('stg_orders') }}
    WHERE status = 'delivered'
      AND driver_id IS NOT NULL
),
drivers AS (
    SELECT
        driver_id,
        name            AS driver_name,
        city            AS driver_city,
        vehicle_type,
        rating          AS driver_rating
    FROM {{ ref('stg_drivers') }}
)

SELECT
    d.order_id,
    d.driver_id,
    dr.driver_name,
    dr.driver_city,
    dr.vehicle_type,
    dr.driver_rating,
    d.restaurant_id,
    d.total_amount,
    d.delivery_date
FROM delivered_orders d
LEFT JOIN drivers dr USING (driver_id)
"""


def int_user_activity_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/models/intermediate/int_user_activity.sql
-- Phase 5 -- ephemeral CTE: per-user order aggregates used by cohort mart.
{{ config(materialized='ephemeral') }}

SELECT
    user_id,
    count()                                 AS total_orders,
    countIf(status = 'delivered')           AS delivered_orders,
    countIf(status = 'cancelled')           AS cancelled_orders,
    sum(total_amount)                       AS lifetime_value,
    min(created_at_dt)                      AS first_order_at,
    max(created_at_dt)                      AS last_order_at,
    -- Cohort month based on first order
    toStartOfMonth(min(created_at_dt))      AS cohort_month
FROM {{ ref('stg_orders') }}
GROUP BY user_id
"""
