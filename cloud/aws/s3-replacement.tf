# =============================================================================
# OrderFlow — S3 Buckets Replacing MinIO (Reference Terraform)
# =============================================================================
# REFERENCE ONLY — not executable without AWS credentials.
#
# This file creates the three S3 buckets that replace the in-cluster MinIO
# deployment used in the Kind development environment. The key insight is that
# Spark, Debezium, and all other components already use the s3a:// protocol
# to talk to MinIO. Moving to real S3 requires only:
#
#   1. Remove the endpoint URL override (MinIO's http://minio.minio.svc:9000)
#   2. Remove static access/secret keys (IRSA handles authentication)
#   3. Set path_style_access = false (S3 uses virtual-hosted style)
#
# Bucket names, object key layouts, and file formats remain identical.
# =============================================================================

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------

variable "environment" {
  description = "Environment name (e.g., production, staging)"
  type        = string
  default     = "production"
}

variable "bucket_prefix" {
  description = "Prefix for S3 bucket names (must be globally unique)"
  type        = string
  default     = "orderflow"
}

# -----------------------------------------------------------------------------
# S3 Bucket: orderflow-raw (Bronze Layer)
# -----------------------------------------------------------------------------
# Stores raw CDC events from Debezium S3 sink connector and any raw file
# uploads. Data is written once and rarely re-read after the initial Spark
# ingestion into Delta Lake.

resource "aws_s3_bucket" "raw" {
  bucket = "${var.bucket_prefix}-raw"

  tags = {
    Project     = "OrderFlow"
    Layer       = "bronze"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "raw" {
  bucket = aws_s3_bucket.raw.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    # Raw data older than 30 days is rarely accessed — move to IA
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    # Archive after 90 days (optional, uncomment if needed)
    # transition {
    #   days          = 90
    #   storage_class = "GLACIER"
    # }

    # Delete raw data after 365 days (adjust based on retention policy)
    expiration {
      days = 365
    }
  }

  rule {
    id     = "cleanup-incomplete-uploads"
    status = "Enabled"

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# -----------------------------------------------------------------------------
# S3 Bucket: orderflow-silver (Silver Layer — Delta Lake)
# -----------------------------------------------------------------------------
# Stores Delta Lake tables written by Spark batch and streaming jobs.
# This is the primary analytical storage layer. Data is read frequently
# by downstream Spark jobs and dbt models.

resource "aws_s3_bucket" "silver" {
  bucket = "${var.bucket_prefix}-silver"

  tags = {
    Project     = "OrderFlow"
    Layer       = "silver"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_s3_bucket_versioning" "silver" {
  bucket = aws_s3_bucket.silver.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "silver" {
  bucket = aws_s3_bucket.silver.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "silver" {
  bucket = aws_s3_bucket.silver.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "silver" {
  bucket = aws_s3_bucket.silver.id

  # Silver data is actively queried — no transition to IA
  # Delta Lake handles its own vacuuming of old versions
  rule {
    id     = "cleanup-incomplete-uploads"
    status = "Enabled"

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# -----------------------------------------------------------------------------
# S3 Bucket: orderflow-checkpoints (Spark Streaming Checkpoints)
# -----------------------------------------------------------------------------
# Stores Spark Structured Streaming checkpoint data. These are small metadata
# files that track stream progress. They must be durable but are not large.

resource "aws_s3_bucket" "checkpoints" {
  bucket = "${var.bucket_prefix}-checkpoints"

  tags = {
    Project     = "OrderFlow"
    Layer       = "infrastructure"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_s3_bucket_versioning" "checkpoints" {
  bucket = aws_s3_bucket.checkpoints.id

  versioning_configuration {
    # Checkpoints are overwritten frequently; versioning adds cost for no benefit
    status = "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "checkpoints" {
  bucket = aws_s3_bucket.checkpoints.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "checkpoints" {
  bucket = aws_s3_bucket.checkpoints.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "checkpoints" {
  bucket = aws_s3_bucket.checkpoints.id

  rule {
    id     = "cleanup-incomplete-uploads"
    status = "Enabled"

    abort_incomplete_multipart_upload {
      days_after_initiation = 3
    }
  }

  # Checkpoint data older than 30 days is stale (streams would be restarted
  # from scratch anyway). Clean up automatically.
  rule {
    id     = "expire-stale-checkpoints"
    status = "Enabled"

    expiration {
      days = 30
    }
  }
}

# -----------------------------------------------------------------------------
# Bucket Policy: Restrict Access to IRSA Roles Only
# -----------------------------------------------------------------------------
# Each bucket is accessible only by the specific IAM roles defined in
# irsa-config.tf. This enforces least-privilege at the bucket level.

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket_policy" "raw" {
  bucket = aws_s3_bucket.raw.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSparkAndDebeziumOnly"
        Effect = "Allow"
        Principal = {
          AWS = [
            "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/orderflow-prod-spark",
            "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/orderflow-prod-debezium"
          ]
        }
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:DeleteObject"
        ]
        Resource = [
          aws_s3_bucket.raw.arn,
          "${aws_s3_bucket.raw.arn}/*"
        ]
      },
      {
        Sid       = "DenyPublicAccess"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.raw.arn,
          "${aws_s3_bucket.raw.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

resource "aws_s3_bucket_policy" "silver" {
  bucket = aws_s3_bucket.silver.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSparkOnly"
        Effect = "Allow"
        Principal = {
          AWS = [
            "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/orderflow-prod-spark"
          ]
        }
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:DeleteObject"
        ]
        Resource = [
          aws_s3_bucket.silver.arn,
          "${aws_s3_bucket.silver.arn}/*"
        ]
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.silver.arn,
          "${aws_s3_bucket.silver.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

resource "aws_s3_bucket_policy" "checkpoints" {
  bucket = aws_s3_bucket.checkpoints.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSparkOnly"
        Effect = "Allow"
        Principal = {
          AWS = [
            "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/orderflow-prod-spark"
          ]
        }
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:DeleteObject"
        ]
        Resource = [
          aws_s3_bucket.checkpoints.arn,
          "${aws_s3_bucket.checkpoints.arn}/*"
        ]
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.checkpoints.arn,
          "${aws_s3_bucket.checkpoints.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "raw_bucket_name" {
  description = "Name of the raw (bronze) S3 bucket"
  value       = aws_s3_bucket.raw.id
}

output "raw_bucket_arn" {
  description = "ARN of the raw (bronze) S3 bucket"
  value       = aws_s3_bucket.raw.arn
}

output "silver_bucket_name" {
  description = "Name of the silver S3 bucket"
  value       = aws_s3_bucket.silver.id
}

output "silver_bucket_arn" {
  description = "ARN of the silver S3 bucket"
  value       = aws_s3_bucket.silver.arn
}

output "checkpoints_bucket_name" {
  description = "Name of the checkpoints S3 bucket"
  value       = aws_s3_bucket.checkpoints.id
}

output "checkpoints_bucket_arn" {
  description = "ARN of the checkpoints S3 bucket"
  value       = aws_s3_bucket.checkpoints.arn
}
