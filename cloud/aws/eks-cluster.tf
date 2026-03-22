# =============================================================================
# OrderFlow — EKS Cluster (Reference Terraform)
# =============================================================================
# REFERENCE ONLY — not executable without AWS credentials and a configured
# Terraform backend. This file documents the target EKS architecture for
# migrating OrderFlow from Kind to production.
#
# Prerequisites:
#   - AWS account with appropriate permissions
#   - VPC and private subnets already provisioned
#   - Terraform >= 1.7.5
#   - AWS provider configured with valid credentials
# =============================================================================

terraform {
  required_version = ">= 1.7.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }

  # Uncomment and configure for real deployment:
  # backend "s3" {
  #   bucket         = "orderflow-terraform-state"
  #   key            = "eks/terraform.tfstate"
  #   region         = "eu-north-1"
  #   dynamodb_table = "orderflow-terraform-lock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = "eu-north-1"
}

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------

variable "vpc_id" {
  description = "ID of the VPC where the EKS cluster will be deployed"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for EKS worker nodes (at least 2 AZs)"
  type        = list(string)
}

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "orderflow-prod"
}

variable "cluster_version" {
  description = "Kubernetes version for the EKS cluster"
  type        = string
  default     = "1.29"
}

# -----------------------------------------------------------------------------
# EKS Cluster
# -----------------------------------------------------------------------------

# Reference only — not executable without AWS credentials
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = var.cluster_version
  vpc_id          = var.vpc_id
  subnet_ids      = var.private_subnet_ids

  # Enable IRSA for pod-level IAM (used by Spark, Airflow, Debezium)
  enable_irsa = true

  # Cluster endpoint access
  cluster_endpoint_public_access  = false
  cluster_endpoint_private_access = true

  # Cluster addons
  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
    aws-ebs-csi-driver = {
      most_recent              = true
      service_account_role_arn = module.ebs_csi_irsa.iam_role_arn
    }
  }

  # --- Managed Node Groups ---------------------------------------------------

  eks_managed_node_groups = {
    # General-purpose node group for most workloads:
    # Kafka (Strimzi), ClickHouse, Airflow, Grafana, Marquez, Schema Registry,
    # Kafka Connect, Debezium
    general = {
      instance_types = ["m5.2xlarge"]
      min_size       = 2
      max_size       = 4
      desired_size   = 3

      labels = {
        "workload" = "general"
      }

      # Use gp3 for better price/performance
      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size = 100
            volume_type = "gp3"
            iops        = 3000
            throughput   = 125
            encrypted   = true
          }
        }
      }
    }

    # Optional: Dedicated Spark node group (scale-from-zero)
    # Uncomment when Spark workloads need dedicated resources.
    # spark = {
    #   instance_types = ["r5.2xlarge"]
    #   min_size       = 0
    #   max_size       = 6
    #   desired_size   = 0
    #
    #   labels = {
    #     "workload" = "spark"
    #   }
    #
    #   taints = [{
    #     key    = "spark"
    #     value  = "true"
    #     effect = "NO_SCHEDULE"
    #   }]
    # }
  }

  tags = {
    Project     = "OrderFlow"
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

# -----------------------------------------------------------------------------
# EBS CSI Driver IRSA
# -----------------------------------------------------------------------------

module "ebs_csi_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name             = "${var.cluster_name}-ebs-csi"
  attach_ebs_csi_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
  }

  tags = {
    Project = "OrderFlow"
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "cluster_endpoint" {
  description = "Endpoint URL for the EKS cluster API server"
  value       = module.eks.cluster_endpoint
}

output "cluster_name" {
  description = "Name of the EKS cluster"
  value       = module.eks.cluster_name
}

output "cluster_certificate_authority_data" {
  description = "Base64-encoded certificate authority data for the cluster"
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "oidc_provider_arn" {
  description = "ARN of the OIDC provider (used for IRSA configuration)"
  value       = module.eks.oidc_provider_arn
}

output "node_security_group_id" {
  description = "Security group ID attached to the EKS worker nodes"
  value       = module.eks.node_security_group_id
}
