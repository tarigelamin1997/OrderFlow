#!/usr/bin/env python3
"""
check_versions.py — compatibility matrix validator.

Reads versions.yaml and validates every inter-service pair against a
hardcoded compatibility matrix sourced from official documentation.
Fails with a clear error identifying the exact incompatible pair.
"""

import sys
import yaml
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
VERSIONS_FILE = REPO_ROOT / "versions.yaml"


def load_versions() -> dict:
    with open(VERSIONS_FILE) as f:
        data = yaml.safe_load(f)
    return data["components"]


def parse_minor(version_str: str) -> tuple[int, int]:
    """Return (major, minor) from a version string like '3.7.0' or '1.8'."""
    parts = str(version_str).split(".")
    major = int(parts[0])
    minor = int(parts[1]) if len(parts) > 1 else 0
    return major, minor


def check_compatibility(versions: dict) -> list[str]:
    """
    Validate all inter-service compatibility pairs.
    Returns list of failure messages; empty list = all pass.
    """
    failures = []

    kafka_major, kafka_minor = parse_minor(versions["kafka"])
    debezium_major, _ = parse_minor(versions["debezium"])
    sr_major, sr_minor = parse_minor(versions["schema_registry"])
    spark_major, spark_minor = parse_minor(versions["spark"])
    delta_major, _ = parse_minor(versions["delta_lake"])
    dbt_core_major, dbt_core_minor = parse_minor(versions["dbt_core"])
    dbt_ch_major, dbt_ch_minor = parse_minor(versions["dbt_clickhouse"])
    dbt_spark_major, dbt_spark_minor = parse_minor(versions["dbt_spark"])
    ch_major, ch_minor = parse_minor(versions["clickhouse"])
    airflow_major, _ = parse_minor(versions["airflow"])
    ge_major, ge_minor = parse_minor(versions["great_expectations"])

    # Debezium 2.x supports Kafka 3.x
    # Source: https://debezium.io/releases/
    if not (debezium_major == 2 and kafka_major == 3):
        failures.append(
            f"FAIL [Debezium↔Kafka]: Debezium {versions['debezium']} requires "
            f"Kafka 3.x, got {versions['kafka']}. "
            f"Source: debezium.io/releases"
        )
    else:
        print(f"PASS [Debezium↔Kafka]: Debezium {versions['debezium']} supports Kafka {versions['kafka']}")

    # Confluent Platform 7.6 supports Kafka 3.6/3.7
    # Source: https://docs.confluent.io/platform/current/installation/versions-interoperability.html
    if not (sr_major == 7 and sr_minor == 6 and kafka_major == 3 and kafka_minor in (6, 7)):
        failures.append(
            f"FAIL [SchemaRegistry↔Kafka]: Schema Registry {versions['schema_registry']} "
            f"(CP 7.6) supports Kafka 3.6/3.7, got {versions['kafka']}. "
            f"Source: docs.confluent.io"
        )
    else:
        print(f"PASS [SchemaRegistry↔Kafka]: Schema Registry {versions['schema_registry']} supports Kafka {versions['kafka']}")

    # Delta Lake 3.x requires Spark 3.5
    # Source: https://delta.io/blog/delta-lake-3-0-released/
    if not (delta_major == 3 and spark_major == 3 and spark_minor == 5):
        failures.append(
            f"FAIL [Spark↔DeltaLake]: Delta Lake {versions['delta_lake']} requires "
            f"Spark 3.5.x, got {versions['spark']}. "
            f"Source: delta.io/compatibility"
        )
    else:
        print(f"PASS [Spark↔DeltaLake]: Delta Lake {versions['delta_lake']} works with Spark {versions['spark']}")

    # dbt-core and dbt-clickhouse must match minor version
    # Source: https://docs.getdbt.com/docs/core-versions
    if not (dbt_core_major == dbt_ch_major and dbt_core_minor == dbt_ch_minor):
        failures.append(
            f"FAIL [dbt-core↔dbt-clickhouse]: Minor versions must match. "
            f"dbt-core={versions['dbt_core']}, dbt-clickhouse={versions['dbt_clickhouse']}. "
            f"Source: docs.getdbt.com"
        )
    else:
        print(f"PASS [dbt-core↔dbt-clickhouse]: Versions match ({versions['dbt_core']})")

    # dbt-core and dbt-spark must match minor version
    # Source: https://docs.getdbt.com/docs/core-versions
    if not (dbt_core_major == dbt_spark_major and dbt_core_minor == dbt_spark_minor):
        failures.append(
            f"FAIL [dbt-core↔dbt-spark]: Minor versions must match. "
            f"dbt-core={versions['dbt_core']}, dbt-spark={versions['dbt_spark']}. "
            f"Source: docs.getdbt.com"
        )
    else:
        print(f"PASS [dbt-core↔dbt-spark]: Versions match ({versions['dbt_core']})")

    # dbt-clickhouse requires ClickHouse >= 22.x
    # Source: https://hub.getdbt.com/ClickHouse/dbt-clickhouse/latest/
    if not (ch_major >= 22):
        failures.append(
            f"FAIL [ClickHouse↔dbt-clickhouse]: dbt-clickhouse {versions['dbt_clickhouse']} "
            f"requires ClickHouse >= 22.x, got {versions['clickhouse']}. "
            f"Source: hub.getdbt.com"
        )
    else:
        print(f"PASS [ClickHouse↔dbt-clickhouse]: ClickHouse {versions['clickhouse']} >= 22.x")

    # Great Expectations 0.18 supports Airflow 2.x
    # Source: https://greatexpectations.io/blog/
    if not (ge_major == 0 and ge_minor == 18 and airflow_major == 2):
        failures.append(
            f"FAIL [Airflow↔GreatExpectations]: GE {versions['great_expectations']} "
            f"requires Airflow 2.x, got {versions['airflow']}. "
            f"Source: greatexpectations.io"
        )
    else:
        print(f"PASS [Airflow↔GreatExpectations]: GE {versions['great_expectations']} supports Airflow {versions['airflow']}")

    # Great Expectations 0.18 supports Spark 3.x
    # Source: https://greatexpectations.io/
    if not (ge_major == 0 and ge_minor == 18 and spark_major == 3):
        failures.append(
            f"FAIL [Spark↔GreatExpectations]: GE {versions['great_expectations']} "
            f"requires Spark 3.x, got {versions['spark']}. "
            f"Source: greatexpectations.io"
        )
    else:
        print(f"PASS [Spark↔GreatExpectations]: GE {versions['great_expectations']} supports Spark {versions['spark']}")

    return failures


def main():
    print(f"Loading versions from {VERSIONS_FILE}")
    versions = load_versions()
    print(f"Loaded {len(versions)} components\n")

    failures = check_compatibility(versions)

    print(f"\n{'='*60}")
    if failures:
        print(f"COMPATIBILITY CHECK FAILED — {len(failures)} incompatible pair(s):\n")
        for msg in failures:
            print(f"  {msg}")
        sys.exit(1)
    else:
        print(f"All compatibility checks passed ({len(versions)} components validated)")
        sys.exit(0)


if __name__ == "__main__":
    main()
