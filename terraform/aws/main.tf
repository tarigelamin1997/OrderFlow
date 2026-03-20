terraform {
  required_version = ">= 1.7.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}

# ── AMI: Ubuntu 22.04 LTS (latest in region) ─────────────────────────────────
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ── Security group: SSH only from allowed IP ──────────────────────────────────
# AWS description field only allows: a-z A-Z 0-9 spaces and . _ - : / ( ) # , @ [ ] + = & ; { } ! $
# No em dashes, no apostrophes.
resource "aws_security_group" "orderflow_sg" {
  name        = "orderflow-sg"
  description = "OrderFlow - SSH inbound from allowed IP only, all outbound"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
    description = "SSH from Tarig IP only"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound traffic allowed"
  }

  tags = {
    Name    = "orderflow-sg"
    Project = "orderflow"
  }
}

# ── Key pair: Terraform-generated RSA key ─────────────────────────────────────
# Generates the key pair in Terraform state. Private key written to
# ~/.ssh/orderflow.pem (0400) so SSH and VS Code Remote-SSH can use it.
# The .pem file is covered by .gitignore (*.pem) — never committed.
resource "tls_private_key" "orderflow" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "orderflow_key" {
  key_name   = "orderflow-key"
  public_key = tls_private_key.orderflow.public_key_openssh

  tags = {
    Name    = "orderflow-key"
    Project = "orderflow"
  }
}

# Write private key locally so SSH works after apply.
resource "local_sensitive_file" "orderflow_private_key" {
  content         = tls_private_key.orderflow.private_key_pem
  filename        = pathexpand("~/.ssh/orderflow.pem")
  file_permission = "0400"
}

# ── IAM: minimal EC2 describe-only policy ─────────────────────────────────────
resource "aws_iam_role" "orderflow_ec2_role" {
  name = "orderflow-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })

  tags = {
    Name    = "orderflow-ec2-role"
    Project = "orderflow"
  }
}

resource "aws_iam_role_policy" "orderflow_ec2_policy" {
  name = "orderflow-ec2-describe-policy"
  role = aws_iam_role.orderflow_ec2_role.id

  # Minimal: EC2 describe only. No S3, no RDS, nothing unnecessary.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ec2:DescribeInstances", "ec2:DescribeVolumes"]
      Resource = "*"
    }]
  })
}

resource "aws_iam_instance_profile" "orderflow_profile" {
  name = "orderflow-instance-profile"
  role = aws_iam_role.orderflow_ec2_role.name
}

# ── EC2 instance ──────────────────────────────────────────────────────────────
resource "aws_instance" "orderflow" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.2xlarge"
  key_name               = aws_key_pair.orderflow_key.key_name
  vpc_security_group_ids = [aws_security_group.orderflow_sg.id]
  iam_instance_profile   = aws_iam_instance_profile.orderflow_profile.name

  user_data = file("${path.module}/user_data.sh")

  # 100GB gp3 root volume.
  # delete_on_termination = false: EBS survives accidental terraform destroy.
  # Kind cluster data on EBS persists independently of instance lifecycle.
  root_block_device {
    volume_type           = "gp3"
    volume_size           = 100
    delete_on_termination = false
  }

  tags = {
    Name    = "orderflow-ec2"
    Project = "orderflow"
  }
}
