#!/usr/bin/env python3
"""
gen_phase5.py -- Phase 5 file generator for OrderFlow.

Copy this file (and the whole dbt/_gen/ directory) to the EC2 instance
inside ~/OrderFlow, then run:

    python3 ~/OrderFlow/gen_phase5.py

All Phase 5 files will be created under ~/OrderFlow/.
Content modules live in dbt/_gen/ alongside the generator.
"""

import os
import stat
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "dbt", "_gen"))

from content_dbt_clickhouse_root import (
    dbt_project_yml        as ch_dbt_project,
    packages_yml           as ch_packages,
    profiles_yml           as ch_profiles,
)
from content_dbt_sources import (
    sources_yml            as ch_sources,
    stg_schema_yml         as ch_stg_schema,
)
from content_dbt_staging_sql import (
    stg_orders_sql, stg_users_sql, stg_restaurants_sql,
    stg_drivers_sql, stg_user_events_sql, stg_delivery_updates_sql,
)
from content_dbt_intermediate import (
    int_orders_enriched_sql, int_driver_deliveries_sql, int_user_activity_sql,
)
from content_dbt_marts import (
    mart_restaurant_revenue_sql, mart_driver_kpis_sql, mart_order_funnel_sql,
    mart_user_cohorts_sql, mart_demand_zone_sql,
)
from content_dbt_snapshots_macros import (
    snap_restaurant_attrs_sql,
    macro_generate_schema_name_sql  as ch_macro_schema,
    macro_cents_to_currency_sql,
)
from content_dbt_spark_root import (
    dbt_project_yml        as sp_dbt_project,
    packages_yml           as sp_packages,
    profiles_yml           as sp_profiles,
    stg_delta_orders_sql, stg_delta_user_events_sql,
    macro_generate_schema_name_sql  as sp_macro_schema,
)
from content_dbt_spark_models import (
    py_feature_validation, py_driver_score, py_demand_features,
)
from content_airflow_dockerfile import get as airflow_dockerfile
from content_verify_phase5      import get as verify_phase5

BASE = os.path.expanduser("~/OrderFlow")

# (relative_path, content_callable, executable_flag)
FILES = [
    # dbt/orderflow_clickhouse root
    ("dbt/orderflow_clickhouse/dbt_project.yml",          ch_dbt_project,              False),
    ("dbt/orderflow_clickhouse/packages.yml",             ch_packages,                 False),
    ("dbt/orderflow_clickhouse/profiles.yml",             ch_profiles,                 False),
    # staging YAML
    ("dbt/orderflow_clickhouse/models/staging/_sources.yml",   ch_sources,             False),
    ("dbt/orderflow_clickhouse/models/staging/_stg_schema.yml", ch_stg_schema,         False),
    # staging SQL
    ("dbt/orderflow_clickhouse/models/staging/stg_orders.sql",          stg_orders_sql,          False),
    ("dbt/orderflow_clickhouse/models/staging/stg_users.sql",           stg_users_sql,           False),
    ("dbt/orderflow_clickhouse/models/staging/stg_restaurants.sql",     stg_restaurants_sql,     False),
    ("dbt/orderflow_clickhouse/models/staging/stg_drivers.sql",         stg_drivers_sql,         False),
    ("dbt/orderflow_clickhouse/models/staging/stg_user_events.sql",     stg_user_events_sql,     False),
    ("dbt/orderflow_clickhouse/models/staging/stg_delivery_updates.sql", stg_delivery_updates_sql, False),
    # intermediate (ephemeral)
    ("dbt/orderflow_clickhouse/models/intermediate/int_orders_enriched.sql",   int_orders_enriched_sql,   False),
    ("dbt/orderflow_clickhouse/models/intermediate/int_driver_deliveries.sql", int_driver_deliveries_sql, False),
    ("dbt/orderflow_clickhouse/models/intermediate/int_user_activity.sql",     int_user_activity_sql,     False),
    # marts
    ("dbt/orderflow_clickhouse/models/marts/mart_restaurant_revenue.sql", mart_restaurant_revenue_sql, False),
    ("dbt/orderflow_clickhouse/models/marts/mart_driver_kpis.sql",        mart_driver_kpis_sql,        False),
    ("dbt/orderflow_clickhouse/models/marts/mart_order_funnel.sql",       mart_order_funnel_sql,       False),
    ("dbt/orderflow_clickhouse/models/marts/mart_user_cohorts.sql",       mart_user_cohorts_sql,       False),
    ("dbt/orderflow_clickhouse/models/marts/mart_demand_zone.sql",        mart_demand_zone_sql,        False),
    # snapshots
    ("dbt/orderflow_clickhouse/snapshots/snap_restaurant_attrs.sql", snap_restaurant_attrs_sql, False),
    # macros
    ("dbt/orderflow_clickhouse/macros/generate_schema_name.sql", ch_macro_schema,          False),
    ("dbt/orderflow_clickhouse/macros/cents_to_currency.sql",    macro_cents_to_currency_sql, False),
    # dbt/orderflow_spark root
    ("dbt/orderflow_spark/dbt_project.yml",  sp_dbt_project, False),
    ("dbt/orderflow_spark/packages.yml",     sp_packages,    False),
    ("dbt/orderflow_spark/profiles.yml",     sp_profiles,    False),
    # spark staging SQL
    ("dbt/orderflow_spark/models/staging/stg_delta_orders.sql",      stg_delta_orders_sql,     False),
    ("dbt/orderflow_spark/models/staging/stg_delta_user_events.sql", stg_delta_user_events_sql, False),
    # spark Python models
    ("dbt/orderflow_spark/models/py_feature_validation.py", py_feature_validation, False),
    ("dbt/orderflow_spark/models/py_driver_score.py",       py_driver_score,       False),
    ("dbt/orderflow_spark/models/py_demand_features.py",    py_demand_features,    False),
    # spark macros
    ("dbt/orderflow_spark/macros/generate_schema_name.sql", sp_macro_schema, False),
    # Airflow Dockerfile (updated with S3A + Delta JARs for dbt-spark session)
    ("airflow/Dockerfile",           airflow_dockerfile, False),
    # Verify script
    ("scripts/verify_phase5.sh",     verify_phase5,      True),
]


def main() -> None:
    print(f"Writing {len(FILES)} Phase 5 files under {BASE}/")
    print()
    for rel_path, content_fn, executable in FILES:
        abs_path = os.path.join(BASE, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as fh:
            fh.write(content_fn())
        if executable:
            mode = os.stat(abs_path).st_mode
            os.chmod(abs_path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            print(f"  created (chmod +x): {rel_path}")
        else:
            print(f"  created:            {rel_path}")

    print()
    print(f"Done. {len(FILES)} files written.")
    print()
    print("Next steps (from ~/OrderFlow):")
    print("  1. docker build -t orderflow/airflow:2.10.0 airflow/")
    print("  2. kind load docker-image orderflow/airflow:2.10.0 --name orderflow")
    print("  3. cd dbt/orderflow_clickhouse")
    print("     dbt deps --profiles-dir . && dbt run --profiles-dir .")
    print("     dbt snapshot --profiles-dir . && dbt test --profiles-dir .")
    print("  4. cd ../orderflow_spark  # (requires active SparkSession via Airflow DAG)")
    print("     dbt deps --profiles-dir . && dbt run --profiles-dir .")
    print("  5. bash ~/OrderFlow/scripts/verify_phase5.sh")


if __name__ == "__main__":
    main()
