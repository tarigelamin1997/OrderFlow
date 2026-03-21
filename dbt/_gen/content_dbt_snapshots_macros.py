"""Snapshots and macros for dbt/orderflow_clickhouse/."""


def snap_restaurant_attrs_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/snapshots/snap_restaurant_attrs.sql
-- Phase 5 -- SCD Type 2 snapshot tracking restaurant attribute changes.
-- Captures changes to commission_rate, cuisine, city, name and rating over time.
-- strategy: timestamp uses updated_at_dt as the change indicator.
{% snapshot snap_restaurant_attrs %}

{{
  config(
    target_schema='dbt_dev__gold',
    unique_key='restaurant_id',
    strategy='timestamp',
    updated_at='updated_at_dt',
    check_cols=['name', 'cuisine', 'city', 'rating', 'commission_rate']
  )
}}

SELECT
    restaurant_id,
    name,
    cuisine,
    city,
    rating,
    commission_rate,
    updated_at_dt,
    _silver_at
FROM {{ ref('stg_restaurants') }}

{% endsnapshot %}
"""


def macro_generate_schema_name_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/macros/generate_schema_name.sql
-- Phase 5 -- Override dbt default schema name resolution.
-- When a model sets schema: dbt_dev__gold, this macro ensures that exact name
-- is used verbatim rather than being prefixed with the target schema.
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is not none -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ target.schema | trim }}
    {%- endif -%}
{%- endmacro %}
"""


def macro_cents_to_currency_sql() -> str:
    return """\
-- dbt/orderflow_clickhouse/macros/cents_to_currency.sql
-- Phase 5 -- Utility macro: format a decimal amount for display.
-- Usage: {{ cents_to_currency('total_amount') }}
{% macro cents_to_currency(column_name, decimals=2) %}
    round({{ column_name }}, {{ decimals }})
{% endmacro %}
"""
