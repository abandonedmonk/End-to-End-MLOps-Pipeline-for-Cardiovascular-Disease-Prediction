resource "aws_sns_topic" "monitoring_alerts" {
  name = "${var.project_name}-monitoring-alerts"
}

resource "aws_cloudwatch_dashboard" "monitoring" {
  dashboard_name = "${var.project_name}-monitoring"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "EC2 CPU Utilization"
          region  = var.aws_region
          stat    = "Average"
          period  = 300
          view    = "timeSeries"
          metrics = [["AWS/EC2", "CPUUtilization", "InstanceId", var.ec2_instance_id]]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "EC2 Memory Utilization"
          region  = var.aws_region
          stat    = "Average"
          period  = 300
          view    = "timeSeries"
          metrics = [["CWAgent", "mem_used_percent", "InstanceId", var.ec2_instance_id]]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Data Drift Score"
          region = var.aws_region
          stat   = "Maximum"
          period = 300
          view   = "timeSeries"
          yAxis = {
            left = {
              min = 0
              max = 1
            }
          }
          annotations = {
            horizontal = [
              {
                label = "Drift threshold"
                value = var.drift_threshold
              }
            ]
          }
          metrics = [[var.metric_namespace, "DataDriftScore"]]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "FastAPI Requests and 5xx Errors"
          region = var.aws_region
          stat   = "Sum"
          period = 300
          view   = "timeSeries"
          metrics = [
            [var.metric_namespace, "FastAPIRequestCount"],
            [var.metric_namespace, "FastAPI5xxErrorCount"]
          ]
        }
      }
    ]
  })
}

resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "high-cpu"
  alarm_description   = "EC2 CPU utilization is greater than 80% for 5 minutes."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.monitoring_alerts.arn]

  dimensions = {
    InstanceId = var.ec2_instance_id
  }
}

resource "aws_cloudwatch_metric_alarm" "high_drift" {
  alarm_name          = "high-drift"
  alarm_description   = "Evidently data drift score exceeded the configured threshold."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "DataDriftScore"
  namespace           = var.metric_namespace
  period              = 300
  statistic           = "Maximum"
  threshold           = var.drift_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.monitoring_alerts.arn]
}
