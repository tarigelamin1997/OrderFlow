"""Source and staging schema YAML files for dbt/orderflow_clickhouse/models/staging/."""


def sources_yml() -> str:
    return """\
# dbt/orderflow_clickhouse/models/staging/_sources.yml
# Phase 5 -- source declarations for silver and gold_batch layers
version: 2

sources:
  - name: silver
    database: silver
    schema: silver
    description: "Silver layer -- cleaned and deduplicated CDC data"
    tables:
      - name: orders
        description: "Order records from PostgreSQL via Debezium CDC"
      - name: users
        description: "User records from PostgreSQL via Debezium CDC"
      - name: restaurants
        description: "Restaurant records from PostgreSQL via Debezium CDC"
      - name: drivers
        description: "Driver records from PostgreSQL via Debezium CDC"
      - name: user_events
        description: "User behavioural events from MongoDB via Debezium CDC"
      - name: delivery_updates
        description: "Driver location updates from MongoDB via Debezium CDC"

  - name: gold_batch
    database: gold
    schema: gold
    description: "Gold batch aggregation tables written by Phase 4 Spark jobs"
    tables:
      - name: restaurant_revenue_batch
      - name: driver_features_batch
      - name: demand_zone_batch
"""


def stg_schema_yml() -> str:
    return """\
# dbt/orderflow_clickhouse/models/staging/_stg_schema.yml
# Phase 5 -- schema tests for all staging views
version: 2

models:
  - name: stg_orders
    description: "Staging view over silver.orders (active records only)"
    columns:
      - name: order_id
        tests:
          - not_null
          - unique
      - name: user_id
        tests:
          - not_null
      - name: restaurant_id
        tests:
          - not_null
      - name: status
        tests:
          - not_null
          - accepted_values:
              values: ["pending", "confirmed", "preparing", "out_for_delivery",
                       "delivered", "cancelled"]

  - name: stg_users
    description: "Staging view over silver.users (active records only)"
    columns:
      - name: user_id
        tests:
          - not_null
          - unique

  - name: stg_restaurants
    description: "Staging view over silver.restaurants (active records only)"
    columns:
      - name: restaurant_id
        tests:
          - not_null
          - unique

  - name: stg_drivers
    description: "Staging view over silver.drivers (active records only)"
    columns:
      - name: driver_id
        tests:
          - not_null
          - unique

  - name: stg_user_events
    description: "Staging view over silver.user_events (append-only)"
    columns:
      - name: event_id
        tests:
          - not_null

  - name: stg_delivery_updates
    description: "Staging view over silver.delivery_updates (append-only)"
    columns:
      - name: update_id
        tests:
          - not_null
"""
