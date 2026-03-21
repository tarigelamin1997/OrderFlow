"""Mart (materialized table) SQL models for dbt/orderflow_clickhouse/models/marts/."""


def mart_restaurant_revenue_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/models/marts/mart_restaurant_revenue.sql
-- Phase 5 -- restaurant-level revenue KPIs aggregated by day.
-- SummingMergeTree allows efficient incremental summation in ClickHouse.
{{
  config(
    materialized='table',
    engine='SummingMergeTree()',
    order_by='(restaurant_id, revenue_date)',
    schema='dbt_dev__gold'
  )
}}

SELECT
    restaurant_id,
    restaurant_name,
    cuisine,
    restaurant_city,
    toDate(created_at_dt)                   AS revenue_date,
    count()                                 AS order_count,
    countIf(status = 'delivered')           AS delivered_count,
    countIf(status = 'cancelled')           AS cancelled_count,
    sum(total_amount)                       AS gross_revenue,
    sum(commission_earned)                  AS platform_commission,
    avg(total_amount)                       AS avg_order_value
FROM {{ ref('int_orders_enriched') }}
GROUP BY
    restaurant_id,
    restaurant_name,
    cuisine,
    restaurant_city,
    toDate(created_at_dt)
"""


def mart_driver_kpis_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/models/marts/mart_driver_kpis.sql
-- Phase 5 -- per-driver delivery KPIs aggregated by day.
{{
  config(
    materialized='table',
    engine='SummingMergeTree()',
    order_by='(driver_id, delivery_date)',
    schema='dbt_dev__gold'
  )
}}

SELECT
    driver_id,
    driver_name,
    driver_city,
    vehicle_type,
    driver_rating,
    delivery_date,
    count()                 AS deliveries_completed,
    sum(total_amount)       AS total_delivery_value,
    avg(total_amount)       AS avg_delivery_value,
    count(DISTINCT restaurant_id) AS unique_restaurants
FROM {{ ref('int_driver_deliveries') }}
GROUP BY
    driver_id,
    driver_name,
    driver_city,
    vehicle_type,
    driver_rating,
    delivery_date
"""


def mart_order_funnel_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/models/marts/mart_order_funnel.sql
-- Phase 5 -- order status funnel counts by status and date.
-- Used for conversion funnel analysis and daily operations dashboards.
{{
  config(
    materialized='table',
    engine='SummingMergeTree()',
    order_by='(order_date, status)',
    schema='dbt_dev__gold'
  )
}}

SELECT
    toDate(created_at_dt)   AS order_date,
    status,
    count()                 AS order_count,
    sum(total_amount)       AS total_amount,
    avg(total_amount)       AS avg_amount
FROM {{ ref('stg_orders') }}
GROUP BY
    toDate(created_at_dt),
    status
"""


def mart_user_cohorts_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/models/marts/mart_user_cohorts.sql
-- Phase 5 -- user cohort behaviour summary (cohort = month of first order).
{{
  config(
    materialized='table',
    engine='SummingMergeTree()',
    order_by='(cohort_month)',
    schema='dbt_dev__gold'
  )
}}

SELECT
    cohort_month,
    count()                         AS cohort_size,
    sum(total_orders)               AS total_orders,
    sum(delivered_orders)           AS total_delivered,
    sum(cancelled_orders)           AS total_cancelled,
    sum(lifetime_value)             AS total_ltv,
    avg(lifetime_value)             AS avg_ltv,
    avg(total_orders)               AS avg_orders_per_user
FROM {{ ref('int_user_activity') }}
GROUP BY cohort_month
"""


def mart_demand_zone_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/models/marts/mart_demand_zone.sql
-- Phase 5 -- demand by city zone aggregated from delivery updates.
-- Combines order counts with delivery GPS coverage per city and date.
{{
  config(
    materialized='table',
    engine='SummingMergeTree()',
    order_by='(zone_city, demand_date)',
    schema='dbt_dev__gold'
  )
}}

WITH order_cities AS (
    SELECT
        restaurant_city                     AS zone_city,
        toDate(created_at_dt)               AS demand_date,
        count()                             AS order_count,
        sum(total_amount)                   AS total_revenue,
        countIf(status = 'delivered')       AS delivered_count
    FROM {{ ref('int_orders_enriched') }}
    GROUP BY restaurant_city, toDate(created_at_dt)
),
delivery_pings AS (
    SELECT
        toDate(update_timestamp)            AS demand_date,
        count()                             AS location_ping_count,
        count(DISTINCT driver_id)           AS active_drivers
    FROM {{ ref('stg_delivery_updates') }}
    GROUP BY toDate(update_timestamp)
)

SELECT
    oc.zone_city,
    oc.demand_date,
    oc.order_count,
    oc.total_revenue,
    oc.delivered_count,
    coalesce(dp.location_ping_count, 0)     AS location_ping_count,
    coalesce(dp.active_drivers, 0)          AS active_drivers
FROM order_cities oc
LEFT JOIN delivery_pings dp
    ON oc.demand_date = dp.demand_date
"""
