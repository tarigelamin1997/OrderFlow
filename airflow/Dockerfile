FROM apache/airflow:2.10.0

# Install system dependencies as root
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Switch back to airflow user for pip installs
USER airflow

# Install packages required by Phase 1-9 DAGs.
# Versions pinned to match versions.yaml — check_version_drift.py validates these.
# Exact pins avoid pip ResolutionTooDeep with wildcard dbt-spark/dbt-adapters chains.
RUN pip install --no-cache-dir \
    dbt-core==1.8.0 \
    dbt-clickhouse==1.8.4 \
    dbt-spark[PyHive]==1.8.0 \
    apache-airflow-providers-cncf-kubernetes \
    apache-airflow-providers-openlineage \
    great-expectations==0.18.21 \
    clickhouse-driver
