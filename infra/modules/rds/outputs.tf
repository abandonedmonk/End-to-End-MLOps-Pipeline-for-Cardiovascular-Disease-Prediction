output "endpoint" {
  value = aws_db_instance.main.endpoint
}

output "security_group_id" {
  value = aws_security_group.rds.id
}

output "db_name" {
  value = var.db_name
}

output "username" {
  value = var.username
}
