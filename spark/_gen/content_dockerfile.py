"""Dockerfile content for Phase 4 Spark image."""


def get() -> str:
    return """\
# spark/Dockerfile
# Base: official Apache Spark 3.5.1 with Python 3
# Adds Delta Lake 3.1.0 JARs + AWS/ClickHouse connectors for MinIO & ClickHouse writes.
FROM apache/spark:3.5.1-python3

USER root

# ── JAR versions (from versions.yaml) ────────────────────────────────────────
ENV DELTA_VERSION=3.1.0
ENV HADOOP_AWS_VERSION=3.3.4
ENV AWS_SDK_VERSION=1.12.367
ENV CLICKHOUSE_JDBC_VERSION=0.6.3

# ── Download all JARs to Spark jars dir ──────────────────────────────────────
RUN set -euo pipefail && \\
    JAR_DIR=/opt/spark/jars && \\
    BASE_MVN=https://repo1.maven.org/maven2 && \\
    \\
    # Delta Lake core + Spark
    wget -q -P "$JAR_DIR" \\
      "${BASE_MVN}/io/delta/delta-spark_2.12/${DELTA_VERSION}/delta-spark_2.12-${DELTA_VERSION}.jar" && \\
    wget -q -P "$JAR_DIR" \\
      "${BASE_MVN}/io/delta/delta-storage/${DELTA_VERSION}/delta-storage-${DELTA_VERSION}.jar" && \\
    \\
    # Hadoop AWS + AWS SDK bundle (for S3A / MinIO)
    wget -q -P "$JAR_DIR" \\
      "${BASE_MVN}/org/apache/hadoop/hadoop-aws/${HADOOP_AWS_VERSION}/hadoop-aws-${HADOOP_AWS_VERSION}.jar" && \\
    wget -q -P "$JAR_DIR" \\
      "${BASE_MVN}/com/amazonaws/aws-java-sdk-bundle/${AWS_SDK_VERSION}/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar" && \\
    \\
    # ClickHouse JDBC (all-in-one / shaded)
    wget -q -P "$JAR_DIR" \\
      "${BASE_MVN}/com/clickhouse/clickhouse-jdbc/${CLICKHOUSE_JDBC_VERSION}/clickhouse-jdbc-${CLICKHOUSE_JDBC_VERSION}-all.jar" && \\
    \\
    echo "JAR download complete."

# ── Python dependencies ───────────────────────────────────────────────────────
RUN pip3 install --no-cache-dir delta-spark==3.1.0

USER spark
"""
