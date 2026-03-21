"""SparkApplication manifest contents for Phase 4."""

_ENV_MINIO = """\
      - name: MINIO_ACCESS_KEY
        valueFrom:
          secretKeyRef:
            name: orderflow-minio-secret
            key: access-key
      - name: MINIO_SECRET_KEY
        valueFrom:
          secretKeyRef:
            name: orderflow-minio-secret
            key: secret-key"""

_ENV_MINIO_CH = _ENV_MINIO + """
      - name: CLICKHOUSE_PASSWORD
        value: \"\""""


def _manifest(name, main_file, args_block, extra_driver_env="", extra_exec_env=""):
    driver_env = _ENV_MINIO + extra_driver_env
    exec_env   = _ENV_MINIO + extra_exec_env
    args_section = f"  arguments:\n{args_block}\n" if args_block else ""
    return f"""\
# spark/manifests/{name}.yaml
# Phase 4 -- SparkApplication: {name}
apiVersion: sparkoperator.k8s.io/v1beta2
kind: SparkApplication
metadata:
  name: {name}
  namespace: spark
spec:
  type: Python
  pythonVersion: "3"
  mode: cluster
  image: "orderflow/spark-orderflow:3.5.1-delta3"
  imagePullPolicy: Never
  mainApplicationFile: "local:///opt/spark/jobs/{main_file}"
{args_section}  sparkVersion: "3.5.1"
  restartPolicy:
    type: Never
  driver:
    cores: 1
    memory: "1Gi"
    labels:
      version: "3.5.1"
      phase: "4"
      job: "{name}"
    serviceAccount: spark
    env:
{driver_env}
  executor:
    cores: 1
    instances: 2
    memory: "2Gi"
    labels:
      version: "3.5.1"
      phase: "4"
      job: "{name}"
    env:
{exec_env}
"""


def silver_ingestion_yaml():
    args = '    - "--entity"\n    - "all"'
    return _manifest("silver-ingestion", "silver_ingestion.py", args)


def feature_engineering_yaml():
    args = '    - "--feature"\n    - "all"'
    return _manifest("feature-engineering", "feature_engineering.py", args)


def gold_writer_yaml():
    ch_env = "\n      - name: CLICKHOUSE_PASSWORD\n        value: \"\""
    args = ""
    return _manifest("gold-writer", "gold_writer.py", args,
                     extra_driver_env=ch_env, extra_exec_env=ch_env)
