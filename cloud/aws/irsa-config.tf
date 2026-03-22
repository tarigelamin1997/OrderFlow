# =============================================================================
# OrderFlow — IRSA + Secrets Manager Configuration (Reference Terraform)
# =============================================================================
# REFERENCE ONLY — not executable without AWS credentials.
#
# This file defines:
#   1. IAM roles for Kubernetes ServiceAccounts (IRSA) so pods authenticate
#      to AWS services without static credentials.
#   2. AWS Secrets Manager secrets for database credentials, replacing the
#      K8s Secrets with placeholder values used in the Kind cluster.
#
# Each workload gets the minimum IAM permissions it needs:
#   - Spark: S3 read/write for Delta Lake tables and checkpoints
#   - Airflow: Secrets Manager read for connection strings, S3 for logs
#   - Debezium: S3 write for the raw-event sink connector
# =============================================================================

# -----------------------------------------------------------------------------
# Data Sources — imported from eks-cluster.tf outputs
# -----------------------------------------------------------------------------

data "aws_eks_cluster" "this" {
  name = var.cluster_name
}

data "aws_caller_identity" "current" {}

# The OIDC provider is created by the EKS module when enable_irsa = true.
# We reference its ARN to build trust policies for each IAM role.
data "aws_iam_openid_connect_provider" "eks" {
  url = data.aws_eks_cluster.this.identity[0].oidc[0].issuer
}

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------

variable "cluster_name" {
  description = "Name of the EKS cluster (must match eks-cluster.tf)"
  type        = string
  default     = "orderflow-prod"
}

variable "spark_namespace" {
  description = "Kubernetes namespace where Spark jobs run"
  type        = string
  default     = "spark"
}

variable "airflow_namespace" {
  description = "Kubernetes namespace where Airflow runs"
  type        = string
  default     = "airflow"
}

variable "kafka_namespace" {
  description = "Kubernetes namespace where Kafka Connect / Debezium runs"
  type        = string
  default     = "kafka"
}

# =============================================================================
# 1. IRSA — Spark ServiceAccount (S3 Access)
# =============================================================================

# IAM policy: Spark needs read/write to the three OrderFlow S3 buckets.
resource "aws_iam_policy" "spark_s3" {
  name        = "${var.cluster_name}-spark-s3"
  description = "Allow Spark pods to read/write OrderFlow S3 buckets"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3BucketAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          "arn:aws:s3:::orderflow-raw",
          "arn:aws:s3:::orderflow-raw/*",
          "arn:aws:s3:::orderflow-silver",
          "arn:aws:s3:::orderflow-silver/*",
          "arn:aws:s3:::orderflow-checkpoints",
          "arn:aws:s3:::orderflow-checkpoints/*"
        ]
      }
    ]
  })

  tags = {
    Project = "OrderFlow"
  }
}

# IAM role: Trusted by the Spark ServiceAccount in the spark namespace.
module "spark_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name = "${var.cluster_name}-spark"

  role_policy_arns = {
    spark_s3 = aws_iam_policy.spark_s3.arn
  }

  oidc_providers = {
    main = {
      provider_arn               = data.aws_iam_openid_connect_provider.eks.arn
      namespace_service_accounts = ["${var.spark_namespace}:spark"]
    }
  }

  tags = {
    Project = "OrderFlow"
  }
}

# After applying, annotate the existing Spark ServiceAccount:
#   kubectl -n spark annotate serviceaccount spark \
#     eks.amazonaws.com/role-arn=<spark_irsa_role_arn> --overwrite

# =============================================================================
# 2. IRSA — Airflow ServiceAccount (Secrets Manager + S3 Logs)
# =============================================================================

# IAM policy: Airflow needs to read secrets and optionally write logs to S3.
resource "aws_iam_policy" "airflow_secrets" {
  name        = "${var.cluster_name}-airflow-secrets"
  description = "Allow Airflow to read OrderFlow secrets from Secrets Manager"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SecretsManagerRead"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          "arn:aws:secretsmanager:eu-north-1:${data.aws_caller_identity.current.account_id}:secret:orderflow/*"
        ]
      },
      {
        Sid    = "S3LogAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::orderflow-airflow-logs",
          "arn:aws:s3:::orderflow-airflow-logs/*"
        ]
      }
    ]
  })

  tags = {
    Project = "OrderFlow"
  }
}

module "airflow_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name = "${var.cluster_name}-airflow"

  role_policy_arns = {
    airflow_secrets = aws_iam_policy.airflow_secrets.arn
  }

  oidc_providers = {
    main = {
      provider_arn               = data.aws_iam_openid_connect_provider.eks.arn
      namespace_service_accounts = ["${var.airflow_namespace}:airflow"]
    }
  }

  tags = {
    Project = "OrderFlow"
  }
}

# After applying, annotate the existing Airflow ServiceAccount:
#   kubectl -n airflow annotate serviceaccount airflow \
#     eks.amazonaws.com/role-arn=<airflow_irsa_role_arn> --overwrite

# =============================================================================
# 3. IRSA — Debezium / Kafka Connect ServiceAccount (S3 Write)
# =============================================================================

resource "aws_iam_policy" "debezium_s3" {
  name        = "${var.cluster_name}-debezium-s3"
  description = "Allow Debezium S3 sink connector to write raw events"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3SinkWrite"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          "arn:aws:s3:::orderflow-raw",
          "arn:aws:s3:::orderflow-raw/*"
        ]
      }
    ]
  })

  tags = {
    Project = "OrderFlow"
  }
}

module "debezium_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name = "${var.cluster_name}-debezium"

  role_policy_arns = {
    debezium_s3 = aws_iam_policy.debezium_s3.arn
  }

  oidc_providers = {
    main = {
      provider_arn               = data.aws_iam_openid_connect_provider.eks.arn
      namespace_service_accounts = ["${var.kafka_namespace}:kafka-connect"]
    }
  }

  tags = {
    Project = "OrderFlow"
  }
}

# =============================================================================
# 4. AWS Secrets Manager — Database Credentials
# =============================================================================
# These secrets replace the K8s Secret manifests that currently hold placeholder
# values. In production, actual credentials are set via the AWS Console or CLI:
#
#   aws secretsmanager put-secret-value \
#     --secret-id orderflow/clickhouse \
#     --secret-string '{"username":"default","password":"<real-password>"}'
#
# Workloads consume these secrets via:
#   - Secrets Store CSI Driver (mounts as files/env vars in pods), OR
#   - External Secrets Operator (syncs to K8s Secrets automatically)
# =============================================================================

resource "aws_secretsmanager_secret" "clickhouse" {
  name        = "orderflow/clickhouse"
  description = "ClickHouse database credentials for OrderFlow"

  tags = {
    Project   = "OrderFlow"
    Component = "clickhouse"
  }
}

resource "aws_secretsmanager_secret_version" "clickhouse" {
  secret_id = aws_secretsmanager_secret.clickhouse.id
  # Placeholder — real values set via CLI, never committed to code
  secret_string = jsonencode({
    username = "PLACEHOLDER"
    password = "PLACEHOLDER"
    host     = "clickhouse.clickhouse.svc"
    port     = "8123"
  })
}

resource "aws_secretsmanager_secret" "postgres" {
  name        = "orderflow/postgres"
  description = "PostgreSQL (Airflow metadata + source DB) credentials"

  tags = {
    Project   = "OrderFlow"
    Component = "postgres"
  }
}

resource "aws_secretsmanager_secret_version" "postgres" {
  secret_id = aws_secretsmanager_secret.postgres.id
  secret_string = jsonencode({
    username = "PLACEHOLDER"
    password = "PLACEHOLDER"
    host     = "postgres.postgres.svc"
    port     = "5432"
  })
}

resource "aws_secretsmanager_secret" "mongodb" {
  name        = "orderflow/mongodb"
  description = "MongoDB (source DB) credentials"

  tags = {
    Project   = "OrderFlow"
    Component = "mongodb"
  }
}

resource "aws_secretsmanager_secret_version" "mongodb" {
  secret_id = aws_secretsmanager_secret.mongodb.id
  secret_string = jsonencode({
    username = "PLACEHOLDER"
    password = "PLACEHOLDER"
    host     = "mongodb.mongodb.svc"
    port     = "27017"
  })
}

resource "aws_secretsmanager_secret" "kafka" {
  name        = "orderflow/kafka"
  description = "Kafka broker connection details"

  tags = {
    Project   = "OrderFlow"
    Component = "kafka"
  }
}

resource "aws_secretsmanager_secret_version" "kafka" {
  secret_id = aws_secretsmanager_secret.kafka.id
  secret_string = jsonencode({
    bootstrap_servers = "PLACEHOLDER"
    security_protocol = "PLAINTEXT"
  })
}

# =============================================================================
# Outputs
# =============================================================================

output "spark_irsa_role_arn" {
  description = "IAM role ARN for the Spark ServiceAccount"
  value       = module.spark_irsa.iam_role_arn
}

output "airflow_irsa_role_arn" {
  description = "IAM role ARN for the Airflow ServiceAccount"
  value       = module.airflow_irsa.iam_role_arn
}

output "debezium_irsa_role_arn" {
  description = "IAM role ARN for the Debezium / Kafka Connect ServiceAccount"
  value       = module.debezium_irsa.iam_role_arn
}
