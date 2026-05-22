output "dashboard_name" {
  description = "CloudWatch dashboard name"
  value       = aws_cloudwatch_dashboard.monitoring.dashboard_name
}

output "alerts_topic_arn" {
  description = "SNS topic ARN for monitoring alarms"
  value       = aws_sns_topic.monitoring_alerts.arn
}
