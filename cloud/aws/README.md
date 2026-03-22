# OrderFlow EKS Migration Guide

This document describes what changes when migrating OrderFlow from the local
Kind cluster (development / single-EC2) to a production Amazon EKS deployment.
The application layer (Kafka topics, ClickHouse schemas, Spark jobs, Airflow
DAGs, dbt models) is intentionally unchanged. Only infrastructure wiring moves.

---

## What Changes from Kind to EKS

| Layer | Kind (current) | EKS (production) |
|-------|----------------|-------------------|
| Cluster provisioning | `kind create cluster` | Terraform `eks-cluster.tf` |
| Node pool | 1 control-plane + 2 workers (Docker containers) | EKS managed node group (EC2 instances) |
| Container runtime | containerd inside Kind nodes | containerd on EKS AMI |
| Networking | NodePort on localhost, SSH tunnel | AWS ALB / NLB via Ingress controller |
| Persistent storage | hostPath / local-path-provisioner | EBS CSI driver (gp3) |
| Object storage | MinIO (in-cluster) | Amazon S3 |
| Secrets | K8s Secrets with placeholder values | IRSA + AWS Secrets Manager |
| DNS | none (port numbers only) | Route 53 or internal ALB DNS |
| TLS | none | ACM certificates on ALB |
| Monitoring | Self-hosted Grafana (in-cluster) | Self-hosted on EKS or Amazon Managed Grafana |

### What Does NOT Change

- Strimzi Kafka operator CRDs and topic definitions
- ClickHouse schemas (bronze, silver, gold databases)
- Spark job JARs and SparkApplication CRDs
- Airflow DAG Python files
- dbt project, models, and tests
- Debezium connector configurations (except endpoint URLs)
- Marquez / OpenLineage integration
- Grafana dashboard JSON (provisioned via ConfigMaps)

---

## Networking: NodePort to LoadBalancer / Ingress

### Current State (Kind)

All services are exposed via NodePort on the Kind control-plane container.
Access from the developer laptop is through an SSH tunnel to the EC2 host.

```
laptop  -->  SSH tunnel  -->  EC2:30080  -->  Kind NodePort  -->  Airflow Pod
```

### EKS Target State

Replace NodePort services with:

1. **Internal ALB Ingress** for HTTP services (Airflow UI, Grafana, Marquez UI,
   MinIO Console replacement if needed).
2. **NLB** for TCP services (Kafka brokers, ClickHouse native protocol).
3. **ClusterIP** for all inter-service communication (Kafka Connect, Schema
   Registry, Spark driver-executor).

Install the AWS Load Balancer Controller:

```bash
helm install aws-load-balancer-controller \
  eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=orderflow-prod
```

Then annotate Ingress resources:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: orderflow-ingress
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internal
    alb.ingress.kubernetes.io/target-type: ip
spec:
  rules:
    - host: airflow.orderflow.internal
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: airflow-webserver
                port:
                  number: 8080
    - host: grafana.orderflow.internal
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: grafana
                port:
                  number: 3000
```

### Port Mapping Reference

| Service | Kind NodePort | EKS Exposure |
|---------|--------------|--------------|
| Airflow UI | 30080 | ALB Ingress (HTTPS 443) |
| Grafana | 30300 | ALB Ingress (HTTPS 443) |
| Marquez UI | 30301 | ALB Ingress (HTTPS 443) |
| Marquez API | 30500 | ALB Ingress (HTTPS 443) |
| Kafka brokers | 30092 | NLB (TCP 9092) |
| ClickHouse HTTP | 30123 | NLB (TCP 8123) |
| ClickHouse Native | 30900 | NLB (TCP 9000) |
| Schema Registry | 30081 | ClusterIP only |
| Kafka Connect | 30083 | ClusterIP only |
| PostgreSQL | 30432 | ClusterIP only (or RDS) |
| MongoDB | 30017 | ClusterIP only (or DocumentDB) |

---

## Storage: MinIO to S3

### What Changes

The only configuration change is the **endpoint URL**. All Spark jobs and
Debezium connectors already use the `s3a://` protocol. MinIO is S3-compatible,
so the bucket paths remain identical.

| Setting | Kind (MinIO) | EKS (S3) |
|---------|-------------|----------|
| Endpoint | `http://minio.minio.svc:9000` | *remove* (default AWS endpoint) |
| Access key | MinIO root user | IRSA (no static keys) |
| Secret key | MinIO root password | IRSA (no static keys) |
| Path style | `true` | `false` (virtual-hosted style) |
| Bucket names | Same | Same |

### Spark Configuration Diff

```python
# Kind (MinIO)
.set("spark.hadoop.fs.s3a.endpoint", "http://minio.minio.svc:9000")
.set("spark.hadoop.fs.s3a.access.key", "minioadmin")
.set("spark.hadoop.fs.s3a.secret.key", "minioadmin")
.set("spark.hadoop.fs.s3a.path.style.access", "true")

# EKS (S3 with IRSA) — remove endpoint, keys handled by IAM role
.set("spark.hadoop.fs.s3a.aws.credentials.provider",
     "com.amazonaws.auth.WebIdentityTokenCredentialsProvider")
# No endpoint, access.key, or secret.key needed
```

### Debezium S3 Sink Diff

The Debezium S3 sink connector config changes only the endpoint and
authentication fields. The `s3.bucket.name`, `topics.dir`, and format settings
remain identical.

### Buckets

| Bucket | Purpose |
|--------|---------|
| `orderflow-raw` | Bronze-layer raw event storage |
| `orderflow-silver` | Silver-layer cleaned/enriched data |
| `orderflow-checkpoints` | Spark Structured Streaming checkpoints |

See `s3-replacement.tf` for the Terraform resource definitions.

---

## Secrets: K8s Secrets to IRSA + AWS Secrets Manager

### Current State (Kind)

Secrets are stored as Kubernetes Secret manifests with placeholder values.
Actual values are injected via `kubectl create secret` commands at deploy time.
dbt uses `env_var()` in `profiles.yml`.

### EKS Target State

1. **IRSA (IAM Roles for Service Accounts):** Each workload (Spark, Airflow,
   Debezium) gets a Kubernetes ServiceAccount annotated with an IAM role ARN.
   The IAM role grants least-privilege access to the specific AWS resources
   that workload needs (S3 buckets, Secrets Manager secrets).

2. **AWS Secrets Manager:** Database credentials (ClickHouse, PostgreSQL,
   MongoDB) are stored in Secrets Manager. Workloads retrieve them at runtime
   via the Secrets Manager CSI driver or SDK calls.

3. **External Secrets Operator (optional):** Syncs AWS Secrets Manager values
   into K8s Secrets automatically, so existing `env_var()` references in dbt
   and environment variable mounts in Airflow continue to work without code
   changes.

### Migration Steps

1. Create IAM roles and policies (`irsa-config.tf`).
2. Install the Secrets Store CSI Driver and AWS provider.
3. Create SecretProviderClass resources that map Secrets Manager paths to
   volume mounts.
4. Annotate existing ServiceAccounts with the IAM role ARN.
5. Remove static credential environment variables from pod specs.
6. Verify all workloads authenticate successfully.

See `irsa-config.tf` for the reference Terraform definitions.

---

## Spark: spark-operator on EKS

### What Stays the Same

- The `spark-operator` Helm chart is deployed identically on EKS.
- `SparkApplication` CRDs (`spark/*.yaml`) are unchanged.
- Spark job JARs and Python scripts are identical.

### What Changes

| Aspect | Kind | EKS |
|--------|------|-----|
| RBAC | ClusterRole bound to `spark` namespace SA | Same CRDs, but SA annotated with IAM role for S3 |
| Storage access | MinIO via static keys | S3 via IRSA (WebIdentityTokenCredentialsProvider) |
| Resource limits | Constrained to Kind node memory | Full EC2 instance resources available |
| Dynamic allocation | Disabled (not enough resources) | Can be enabled for cost efficiency |
| Node affinity | None | Optional: schedule Spark on dedicated node group |

### Recommended EKS Spark Node Group

For production workloads with larger data volumes, consider a dedicated
node group with instance types optimized for Spark:

```hcl
spark = {
  instance_types = ["r5.2xlarge"]  # Memory-optimized
  min_size       = 0
  max_size       = 6
  desired_size   = 0  # Scale from zero, Karpenter or CA scales up on demand
  labels = {
    "workload" = "spark"
  }
  taints = [{
    key    = "spark"
    value  = "true"
    effect = "NO_SCHEDULE"
  }]
}
```

---

## Monitoring: Grafana on EKS

### Option A: Self-Hosted Grafana on EKS (Recommended for Cost)

Deploy the same Grafana Helm chart currently used in Kind. Dashboard JSON
files are provisioned via ConfigMaps and remain unchanged. The only
differences:

- Grafana is exposed via ALB Ingress instead of NodePort.
- ClickHouse datasource URL changes from NodePort to ClusterIP
  (`clickhouse.clickhouse.svc:8123`).
- Authentication can be integrated with AWS Cognito or an OIDC provider.

### Option B: Amazon Managed Grafana

- AWS manages the Grafana instance, patching, and availability.
- Dashboard JSON can be imported but provisioning-as-code requires the
  Grafana Terraform provider or API calls.
- ClickHouse datasource must use a private VPC endpoint or the NLB.
- Additional cost: ~$9/editor/month.

### Recommendation

Start with Option A (self-hosted) since it reuses all existing ConfigMap-based
provisioning. Migrate to Managed Grafana only if operational overhead of
self-hosting becomes a concern.

### Alert Routing

Current Grafana alerts route to a webhook. On EKS, options include:

- Amazon SNS for email/SMS notifications
- PagerDuty or Opsgenie integration via Grafana alerting contact points
- Slack webhook (unchanged from current setup if already configured)

---

## Cost Estimate Reference

See [cost-estimate.md](cost-estimate.md) for a detailed monthly cost
projection for running OrderFlow on AWS EKS.

**Summary:** ~$1,260/month at on-demand pricing, reducible to ~$900/month
with Reserved Instances or Savings Plans for EC2.

---

## Migration Checklist

Use this checklist when performing the actual migration:

- [ ] Provision VPC, subnets, and EKS cluster (`eks-cluster.tf`)
- [ ] Install EBS CSI driver for persistent volumes
- [ ] Install AWS Load Balancer Controller
- [ ] Create S3 buckets (`s3-replacement.tf`)
- [ ] Create Secrets Manager secrets and IAM roles (`irsa-config.tf`)
- [ ] Install Secrets Store CSI Driver
- [ ] Deploy Strimzi operator and Kafka cluster
- [ ] Deploy ClickHouse with EBS-backed PVCs
- [ ] Deploy Spark operator with IRSA-annotated ServiceAccount
- [ ] Deploy Airflow with IRSA-annotated ServiceAccount
- [ ] Deploy Debezium connectors (remove MinIO endpoint, use S3 default)
- [ ] Deploy Grafana with ALB Ingress
- [ ] Deploy Marquez with ALB Ingress
- [ ] Run `make verify-phase8` equivalent on EKS
- [ ] Validate end-to-end data pipeline (insert source row, verify gold table)
