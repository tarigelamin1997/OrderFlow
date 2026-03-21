"""ClickHouse Gold DDL and apply script content for Phase 4."""


def restaurant_revenue_batch_sql() -> str:
    return """\
-- clickhouse/gold/09_restaurant_revenue_batch.sql
-- Phase 4 -- Gold batch table: restaurant revenue aggregates
-- SummingMergeTree sums order_count and total_revenue on merge
-- when (restaurant_id, order_date) duplicates appear across batch runs.

CREATE TABLE IF NOT EXISTS gold.restaurant_revenue_batch
(
    restaurant_id    Int32,
    order_date       Date,
    order_count      Int64,
    total_revenue    Decimal(14, 2),
    avg_order_value  Decimal(10, 2),
    _batch_run_at    DateTime DEFAULT now()
)
ENGINE = SummingMergeTree(order_count, total_revenue)
PARTITION BY toYYYYMM(order_date)
ORDER BY (restaurant_id, order_date)
SETTINGS index_granularity = 8192;
"""


def driver_features_batch_sql() -> str:
    return """\
-- clickhouse/gold/10_driver_features_batch.sql
-- Phase 4 -- Gold batch table: driver efficiency features
-- ReplacingMergeTree(_batch_run_at) replaces older rows for the same
-- (driver_id, order_date) key when a newer batch run arrives.

CREATE TABLE IF NOT EXISTS gold.driver_features_batch
(
    driver_id              Int32,
    order_date             Date,
    deliveries_completed   Int64,
    avg_order_value        Decimal(10, 2),
    total_revenue          Decimal(14, 2),
    _batch_run_at          DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(_batch_run_at)
PARTITION BY toYYYYMM(order_date)
ORDER BY (driver_id, order_date)
SETTINGS index_granularity = 8192;
"""


def demand_zone_batch_sql() -> str:
    return """\
-- clickhouse/gold/11_demand_zone_batch.sql
-- Phase 4 -- Gold batch table: demand by geographic zone
-- SummingMergeTree sums order_count and total_gmv on merge when
-- (city, order_date) duplicates appear across batch runs.

CREATE TABLE IF NOT EXISTS gold.demand_zone_batch
(
    city          String,
    order_date    Date,
    order_count   Int64,
    total_gmv     Decimal(14, 2),
    _batch_run_at DateTime DEFAULT now()
)
ENGINE = SummingMergeTree(order_count, total_gmv)
PARTITION BY toYYYYMM(order_date)
ORDER BY (city, order_date)
SETTINGS index_granularity = 8192;
"""


def apply_gold_batch_sh() -> str:
    return """\
#!/usr/bin/env bash
# clickhouse/gold/apply_gold_batch.sh
# Phase 4 -- Apply all Gold batch DDL files to ClickHouse.
# Idempotent: CREATE TABLE IF NOT EXISTS throughout.
# Run from EC2 host; requires clickhouse-client and NodePort 30900 reachable.
set -euo pipefail

CH_HOST="localhost"
CH_PORT="30900"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Applying Phase 4 Gold batch DDL to ClickHouse (${CH_HOST}:${CH_PORT})"

for sql_file in \\
    "${SCRIPT_DIR}/09_restaurant_revenue_batch.sql" \\
    "${SCRIPT_DIR}/10_driver_features_batch.sql" \\
    "${SCRIPT_DIR}/11_demand_zone_batch.sql"
do
    echo "  Applying: $(basename "${sql_file}")"
    clickhouse-client \\
        --host "${CH_HOST}" \\
        --port "${CH_PORT}" \\
        --multiquery \\
        --queries-file "${sql_file}"
    echo "  Done: $(basename "${sql_file}")"
done

echo ""
echo "All Phase 4 Gold batch tables created (or already exist)."
echo "Verify with:"
echo "  clickhouse-client --host localhost --port 30900 \\\\"
echo "    --query \\"SHOW TABLES FROM gold LIKE '%_batch'\""
"""
