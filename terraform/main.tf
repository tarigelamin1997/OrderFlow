terraform {
  required_version = ">= 1.7.5"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }
}

# ── Providers point at the Kind cluster kubeconfig ────────────────────────────
# Kind writes kubeconfig to ~/.kube/config on cluster creation.
# On first apply, run: terraform apply -target=module.kind_cluster first,
# then: terraform apply (to deploy workloads into the live cluster).
provider "kubernetes" {
  config_path    = "~/.kube/config"
  config_context = "kind-${var.cluster_name}"
}

provider "helm" {
  kubernetes {
    config_path    = "~/.kube/config"
    config_context = "kind-${var.cluster_name}"
  }
}

# ── Layer 2 modules ───────────────────────────────────────────────────────────

module "kind_cluster" {
  source       = "./modules/kind-cluster"
  cluster_name = var.cluster_name
}

module "databases" {
  source      = "./modules/databases"
  depends_on  = [module.kind_cluster]
  environment = var.environment
}

module "kafka" {
  source      = "./modules/kafka"
  depends_on  = [module.kind_cluster]
  environment = var.environment
}

module "clickhouse" {
  source      = "./modules/clickhouse"
  depends_on  = [module.kind_cluster]
  environment = var.environment
}

module "spark" {
  source             = "./modules/spark"
  depends_on         = [module.kind_cluster]
  environment        = var.environment
  minio_storage_size = var.minio_storage_size
}

# Airflow needs databases and clickhouse running before it initialises
module "airflow" {
  source      = "./modules/airflow"
  depends_on  = [module.databases, module.clickhouse]
  environment = var.environment
}

module "grafana" {
  source      = "./modules/grafana"
  depends_on  = [module.clickhouse]
  environment = var.environment
}

module "marquez" {
  source      = "./modules/marquez"
  depends_on  = [module.kind_cluster]
  environment = var.environment
}
