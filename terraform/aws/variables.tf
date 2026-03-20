variable "aws_region" {
  description = "AWS region — eu-north-1 (Stockholm) is the account default"
  type        = string
  default     = "eu-north-1"
}

variable "aws_profile" {
  description = "AWS CLI profile name"
  type        = string
  default     = "orderflow"
}

variable "allowed_ssh_cidr" {
  description = "CIDR block allowed SSH access. Set to your IP: export TF_VAR_allowed_ssh_cidr=x.x.x.x/32"
  type        = string
  # No default — must be passed explicitly. Security group is closed by default.
}

