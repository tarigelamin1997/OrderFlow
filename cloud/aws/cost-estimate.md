# OrderFlow AWS Production Cost Estimate

This document provides a monthly cost projection for running the OrderFlow
data pipeline on AWS EKS, replacing the current single-EC2 Kind cluster
development environment.

All prices are for the **eu-north-1 (Stockholm)** region as of 2025 pricing.
Actual costs may vary. Consult the [AWS Pricing Calculator](https://calculator.aws/)
for up-to-date figures.

---

## Monthly Cost Breakdown

| Component | AWS Service | Spec / Config | Monthly Estimate |
|-----------|-------------|---------------|-----------------|
| EKS cluster | EKS | Control plane (1 cluster) | $73 |
| Worker nodes (3x m5.2xlarge) | EC2 | 8 vCPU, 32 GB RAM each, on-demand | ~$830 |
| S3 (replacing MinIO) | S3 | ~100 GB storage, moderate requests | ~$5 |
| Managed Kafka (optional) | MSK | 3x kafka.m5.large brokers | ~$350 |
| Secrets Manager | Secrets Manager | 4 secrets, ~1000 API calls/month | ~$2 |
| EBS volumes | EBS (gp3) | 3x 100 GB (one per node) | ~$25 |
| ALB (Ingress) | ALB | 1 ALB, moderate traffic | ~$20 |
| Data transfer | VPC / Internet | Internal mostly, minimal egress | ~$5 |
| **Total (on-demand)** | | | **~$1,310/mo** |

### Simplified View

| Component | AWS Service | Monthly Estimate |
|-----------|-------------|-----------------|
| EKS cluster | EKS | $73 |
| Worker nodes (3x m5.2xlarge) | EC2 | ~$830 |
| S3 (replacing MinIO) | S3 | ~$5 |
| Managed Kafka (MSK) | MSK | ~$350 |
| Secrets Manager | Secrets Manager | ~$2 |
| **Total** | | **~$1,260/mo** |

---

## Cost Reduction Strategies

### 1. Reserved Instances / Savings Plans (~40% EC2 reduction)

EC2 is the largest cost component. Reserved Instances (1-year, no upfront)
or Compute Savings Plans reduce the effective hourly rate significantly:

| Commitment | EC2 Monthly Cost | Savings |
|------------|-----------------|---------|
| On-demand | ~$830 | baseline |
| 1-year RI, no upfront | ~$530 | ~36% |
| 1-year RI, all upfront | ~$500 | ~40% |
| 3-year RI, all upfront | ~$330 | ~60% |

**With 1-year Reserved Instances, the total drops to approximately $900/month.**

### 2. Self-Managed Kafka Instead of MSK

If operational overhead is acceptable, running Strimzi Kafka on the existing
EKS worker nodes (as OrderFlow already does in Kind) eliminates the MSK cost
entirely:

| Option | Monthly Cost |
|--------|-------------|
| MSK (3 brokers) | ~$350 |
| Self-managed Strimzi on EKS | $0 (uses existing nodes) |

This saves $350/month but shifts Kafka operational burden to the team.
Recommended for teams already comfortable with Strimzi.

### 3. Spot Instances for Spark Node Group

If a dedicated Spark node group is used (see `eks-cluster.tf`), Spark
executor pods tolerate interruption well. Using Spot Instances for the
Spark node group can reduce Spark compute costs by 60-70%:

| Instance | On-demand/hr | Spot/hr (typical) | Savings |
|----------|-------------|-------------------|---------|
| r5.2xlarge | $0.576 | ~$0.17 | ~70% |

### 4. Scale-from-Zero for Spark

Spark batch jobs run on a schedule (e.g., every 4 hours). A dedicated Spark
node group with `min_size = 0` and Cluster Autoscaler or Karpenter scales
nodes up only when SparkApplications are submitted, and scales back to zero
when idle. This can reduce Spark compute costs by 60-80% depending on job
frequency and duration.

---

## Comparison: Current vs. Production

| | Current (Kind on EC2) | Production (EKS) |
|---|---|---|
| EC2 | 1x t3.2xlarge (~$270/mo) | 3x m5.2xlarge (~$830/mo) |
| Kafka | Strimzi in Kind | MSK or Strimzi on EKS |
| Storage | MinIO (on EC2 disk) | S3 (~$5/mo) |
| HA | None (single node) | Multi-AZ, auto-scaling |
| Total | ~$270/mo | ~$1,260/mo (on-demand) |

The production setup costs approximately 4.7x more but provides:
- High availability across multiple Availability Zones
- Auto-scaling for traffic spikes
- Managed Kubernetes control plane (no Kind maintenance)
- Durable, replicated object storage (S3 vs. single-disk MinIO)
- IAM-based security (IRSA) instead of static credentials

---

## Optional Managed Services (Not Included Above)

These services can replace self-hosted components for reduced operational
burden at additional cost:

| Self-Hosted Component | Managed Alternative | Additional Monthly Cost |
|---|---|---|
| ClickHouse (on EKS) | ClickHouse Cloud | ~$200-500 (depends on usage) |
| PostgreSQL (on EKS) | Amazon RDS PostgreSQL | ~$30 (db.t3.medium) |
| MongoDB (on EKS) | Amazon DocumentDB | ~$200 (db.r5.large) |
| Grafana (on EKS) | Amazon Managed Grafana | ~$9/editor |
| Airflow (on EKS) | Amazon MWAA | ~$350 (small environment) |

Using all managed services would increase the total to approximately
$2,000-2,500/month but significantly reduce operational complexity.

---

## Notes

- All estimates assume the **eu-north-1 (Stockholm)** region.
- Data transfer costs are minimal because most traffic is internal (within
  VPC). Significant egress to the internet would increase costs.
- S3 costs assume ~100 GB of storage with moderate request volume. At
  petabyte scale, S3 costs grow linearly but remain cost-effective.
- MSK pricing is for `kafka.m5.large` brokers. Smaller instances
  (`kafka.t3.small`) are available for dev/staging at ~$100/month total.
- EKS control plane cost ($73/month) is fixed regardless of the number of
  worker nodes.
- Prices do not include AWS support plans. Business support adds 10% of
  monthly spend (minimum $100/month).
