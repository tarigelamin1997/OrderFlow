"""Root config files for dbt/orderflow_clickhouse/ project."""


def dbt_project_yml() -> str:
    return """\
# dbt/orderflow_clickhouse/dbt_project.yml
# Phase 5 -- dbt project targeting ClickHouse gold layer (dbt_dev__gold database)
name: orderflow_clickhouse
version: "1.0.0"
config-version: 2

profile: orderflow_clickhouse

model-paths:   ["models"]
snapshot-paths: ["snapshots"]
macro-paths:   ["macros"]
target-path:   "target"
clean-targets: ["target", "dbt_packages"]

models:
  orderflow_clickhouse:
    staging:
      +materialized: view
      +schema: dbt_dev__gold
    intermediate:
      +materialized: ephemeral
    marts:
      +materialized: table
      +schema: dbt_dev__gold

snapshots:
  orderflow_clickhouse:
    +target_schema: dbt_dev__gold
    +strategy: timestamp
    +updated_at: updated_at_dt
"""


def packages_yml() -> str:
    return """\
# dbt/orderflow_clickhouse/packages.yml
packages:
  - package: calogica/dbt_expectations
    version: 0.10.4
"""


def profiles_yml() -> str:
    return """\
# dbt/orderflow_clickhouse/profiles.yml
# Credentials injected via environment variables -- never hard-code values here.
orderflow_clickhouse:
  target: dev
  outputs:
    dev:
      type: clickhouse
      driver: native
      host: "{{ env_var('CLICKHOUSE_HOST', 'clickhouse.clickhouse.svc.cluster.local') }}"
      port: 9000
      user: "{{ env_var('CLICKHOUSE_USER', 'default') }}"
      password: "{{ env_var('CLICKHOUSE_PASSWORD', '') }}"
      schema: dbt_dev__gold
      secure: false
      connect_timeout: 10
      send_receive_timeout: 300
      verify: false
      custom_settings:
        allow_experimental_object_type: 1
"""
