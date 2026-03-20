output "instance_id" {
  description = "EC2 instance ID — used by Makefile pause/resume targets"
  value       = aws_instance.orderflow.id
}

output "public_ip" {
  description = "EC2 public IP — set in ~/.ssh/config HostName for SSH tunnel"
  value       = aws_eip.orderflow.public_ip
}

output "instance_dns" {
  description = "EC2 public DNS hostname"
  value       = aws_instance.orderflow.public_dns
}
