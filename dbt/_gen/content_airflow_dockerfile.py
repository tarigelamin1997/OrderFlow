"""Updated Airflow Dockerfile content for Phase 5 (adds S3A + Delta JARs for dbt-spark)."""


def get() -> str:
    return """\
FROM apache/airflow:2.10.0

# Install system dependencies as root
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    && rm -rf /var/lib/apt/lists/*

# Download Hadoop S3A and Delta Lake JARs needed by dbt-spark session method.
# Versions must match versions.yaml: hadoop_aws=3.3.4, aws_java_sdk_bundle=1.12.367,
# delta_lake=3.1.0, spark=3.5.1
ARG HADOOP_AWS_VERSION=3.3.4
ARG AWS_SDK_VERSION=1.12.367
ARG DELTA_VERSION=3.1.0
ARG SCALA_VERSION=2.12

RUN mkdir -p /opt/airflow/jars && \\
    curl -fSL \\
      "https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/${HADOOP_AWS_VERSION}/hadoop-aws-${HADOOP_AWS_VERSION}.jar" \\
      -o /opt/airflow/jars/hadoop-aws.jar && \\
    curl -fSL \\
      "https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/${AWS_SDK_VERSION}/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar" \\
      -o /opt/airflow/jars/aws-java-sdk-bundle.jar && \\
    curl -fSL \\
      "https://repo1.maven.org/maven2/io/delta/delta-spark_${SCALA_VERSION}/${DELTA_VERSION}/delta-spark_${SCALA_VERSION}-${DELTA_VERSION}.jar" \\
      -o /opt/airflow/jars/delta-spark.jar && \\
    curl -fSL \\
      "https://repo1.maven.org/maven2/io/delta/delta-storage/${DELTA_VERSION}/delta-storage-${DELTA_VERSION}.jar" \\
      -o /opt/airflow/jars/delta-storage.jar

# Switch back to airflow user for pip installs
USER airflow

# Install packages required by Phase 1-9 DAGs.
# Versions pinned to match versions.yaml -- check_version_drift.py validates these.
# Exact pins avoid pip ResolutionTooDeep with wildcard dbt-spark/dbt-adapters chains.
RUN pip install --no-cache-dir \\
    dbt-core==1.8.0 \\
    dbt-clickhouse==1.8.4 \\
    dbt-spark[PyHive]==1.8.0 \\
    apache-airflow-providers-cncf-kubernetes \\
    apache-airflow-providers-openlineage \\
    great-expectations==0.18.21 \\
    clickhouse-driver \\
    pyspark==3.5.1
"""
