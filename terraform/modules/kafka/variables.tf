variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}

variable "kafka_retention_ms" {
  description = "Default Kafka topic retention in milliseconds (86400000 = 24h)"
  type        = number
  default     = 86400000
}
