# 03 — Infrastructure Monitoring

Creating CloudWatch dashboards and alarms with Terraform for infrastructure visibility.

---

## What to Monitor

### EC2 Infrastructure
- **CPU Utilization** — Is the instance overloaded?
- **Memory Usage** — Is swap being used? (requires CloudWatch agent)
- **Disk Usage** — Is the root volume full?
- **Network Traffic** — Unexpected spikes?

### Application Health
- **FastAPI Requests** — Traffic patterns
- **5xx Errors** — Server failures
- **Latency (p99)** — User experience

### ML System Health
- **Drift Score** — Model degradation
- **Prediction Volume** — Business impact

---

## Terraform Module Structure

```
infra/modules/monitoring/
├── main.tf      # Dashboard, alarms, SNS
├── variables.tf # Inputs
└── outputs.tf   # ARN outputs
```

### Variables (`variables.tf`)

```hcl
variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "heart-disease-mlops"
}

variable "environment" {
  description = "Environment tag"
  type        = string
  default     = "production"
}

variable "alarm_email" {
  description = "Email for alarm notifications (optional)"
  type        = string
  default     = ""  # Empty = no email, just SNS topic
}

variable "ec2_instance_id" {
  description = "EC2 instance ID to monitor"
  type        = string
}

variable "drift_threshold" {
  description = "Drift score threshold for alarm (0-1)"
  type        = number
  default     = 0.3
}

variable "cpu_threshold" {
  description = "CPU percentage threshold for alarm"
  type        = number
  default     = 80
}

variable "fastapi_log_group" {
  description = "CloudWatch log group for FastAPI"
  type        = string
  default     = "/ec2/heart-disease-mlops/fastapi"
}
```

### Main Resources (`main.tf`)

```hcl
# SNS Topic for alarm notifications
resource "aws_sns_topic" "alarms" {
  name = "${var.project_name}-alarms"
  
  tags = {
    Name        = "${var.project_name}-alarms"
    Environment = var.environment
  }
}

# Email subscription (optional)
resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# CloudWatch Dashboard
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = var.project_name
  
  dashboard_body = jsonencode({
    widgets = [
      # EC2 CPU Utilization
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "EC2 CPU Utilization"
          region = "us-east-1"
          metrics = [
            ["AWS/EC2", "CPUUtilization", "InstanceId", var.ec2_instance_id]
          ]
          period = 300
          yAxis = {
            left = {
              min = 0
              max = 100
            }
          }
        }
      },
      
      # EC2 Memory (requires CloudWatch agent)
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "EC2 Memory Utilization"
          region = "us-east-1"
          metrics = [
            ["CWAgent", "mem_used_percent", "InstanceId", var.ec2_instance_id]
          ]
          period = 300
          yAxis = {
            left = {
              min = 0
              max = 100
            }
          }
        }
      },
      
      # Data Drift Score (custom metric)
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Data Drift Score"
          region = "us-east-1"
          metrics = [
            ["HeartDisease/Monitoring", "DataDriftScore"]
          ]
          period = 86400  # Daily
          annotations = {
            horizontal = [
              {
                value = var.drift_threshold
                label = "Drift Threshold"
                color = "#ff0000"
              }
            ]
          }
        }
      },
      
      # FastAPI Request Count
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "FastAPI Requests"
          region = "us-east-1"
          metrics = [
            ["HeartDisease/Monitoring", "FastAPIRequestCount"]
          ]
          period = 3600  # Hourly
        }
      },
      
      # FastAPI Error Rate
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "FastAPI 5xx Errors"
          region = "us-east-1"
          metrics = [
            ["HeartDisease/Monitoring", "FastAPI5xxErrorCount"]
          ]
          period = 3600
        }
      },
      
      # Text widget with links
      {
        type   = "text"
        x      = 12
        y      = 12
        width  = 12
        height = 6
        properties = {
          markdown = <<-EOT
            # Heart Disease MLOps Dashboard
            
            **Quick Links:**
            - [MLflow UI](http://32.196.26.238:5000)
            - [FastAPI Health](http://32.196.26.238:8000/health)
            - [AWS Console](https://console.aws.amazon.com/cloudwatch)
            
            **Documentation:**
            - [Drift Reports](s3://heart-disease-mlops-695074562426/monitoring/reports/)
          EOT
        }
      }
    ]
  })
}

# CPU Alarm
resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "${var.project_name}-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = "300"
  statistic           = "Average"
  threshold           = var.cpu_threshold
  alarm_description   = "CPU utilization exceeds ${var.cpu_threshold}%"
  
  dimensions = {
    InstanceId = var.ec2_instance_id
  }
  
  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
  
  tags = {
    Name        = "${var.project_name}-high-cpu"
    Environment = var.environment
  }
}

# High Drift Alarm
resource "aws_cloudwatch_metric_alarm" "high_drift" {
  alarm_name          = "${var.project_name}-high-drift"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "DataDriftScore"
  namespace           = "HeartDisease/Monitoring"
  period              = "86400"  # Daily
  statistic           = "Maximum"
  threshold           = var.drift_threshold
  alarm_description   = "Data drift score exceeds ${var.drift_threshold}"
  
  alarm_actions = [aws_sns_topic.alarms.arn]
  
  tags = {
    Name        = "${var.project_name}-high-drift"
    Environment = var.environment
  }
}

# Metric Filter for FastAPI 5xx errors (from logs)
resource "aws_cloudwatch_log_metric_filter" "fastapi_5xx" {
  name           = "${var.project_name}-fastapi-5xx"
  pattern        = '"status_code": 5*'  # Match 5xx status codes
  log_group_name = var.fastapi_log_group
  
  metric_transformation {
    name      = "FastAPI5xxErrorCount"
    namespace = "HeartDisease/Monitoring"
    value     = "1"
    default_value = "0"
  }
}

# Metric Filter for FastAPI requests
resource "aws_cloudwatch_log_metric_filter" "fastapi_requests" {
  name           = "${var.project_name}-fastapi-requests"
  pattern        = '"method": "POST"'  # Count POST requests
  log_group_name = var.fastapi_log_group
  
  metric_transformation {
    name      = "FastAPIRequestCount"
    namespace = "HeartDisease/Monitoring"
    value     = "1"
    default_value = "0"
  }
}
```

### Outputs (`outputs.tf`)

```hcl
output "sns_topic_arn" {
  description = "SNS topic ARN for alarm notifications"
  value       = aws_sns_topic.alarms.arn
}

output "dashboard_name" {
  description = "CloudWatch dashboard name"
  value       = aws_cloudwatch_dashboard.main.dashboard_name
}

output "cpu_alarm_name" {
  description = "High CPU alarm name"
  value       = aws_cloudwatch_metric_alarm.high_cpu.alarm_name
}

output "drift_alarm_name" {
  description = "High drift alarm name"
  value       = aws_cloudwatch_metric_alarm.high_drift.alarm_name
}

output "manual_subscription_command" {
  description = "AWS CLI command to subscribe email to SNS"
  value       = "aws sns subscribe --topic-arn ${aws_sns_topic.alarms.arn} --protocol email --notification-endpoint your-email@example.com"
}
```

---

## Integration with Main Terraform

Update `infra/main.tf`:

```hcl
module "monitoring" {
  source = "./modules/monitoring"
  
  project_name      = var.project_name
  environment       = "production"
  ec2_instance_id   = module.ec2.instance_id
  drift_threshold   = 0.3
  cpu_threshold     = 80
  alarm_email       = var.alarm_email  # Optional, can be empty
  fastapi_log_group = "/ec2/${var.project_name}/fastapi"
}
```

Add to `infra/variables.tf`:

```hcl
variable "alarm_email" {
  description = "Email for CloudWatch alarm notifications (optional)"
  type        = string
  default     = ""
}
```

Add to `infra/outputs.tf`:

```hcl
output "monitoring_dashboard_url" {
  description = "CloudWatch Dashboard URL"
  value       = "https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=${module.monitoring.dashboard_name}"
}

output "sns_topic_arn" {
  description = "SNS topic for alarms"
  value       = module.monitoring.sns_topic_arn
}
```

---

## CloudWatch Agent Setup

For memory metrics, install CloudWatch agent on EC2:

```bash
# In your user_data.sh or manually on EC2

# Download and install agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb

# Create config file
sudo tee /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<'EOF'
{
  "metrics": {
    "namespace": "CWAgent",
    "metrics_collected": {
      "mem": {
        "measurement": ["mem_used_percent"],
        "metrics_collection_interval": 60
      },
      "disk": {
        "measurement": ["disk_used_percent"],
        "resources": ["/"],
        "metrics_collection_interval": 60
      }
    }
  }
}
EOF

# Start agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json

# Enable auto-start
sudo systemctl enable amazon-cloudwatch-agent
```

---

## Viewing the Dashboard

### AWS Console

1. Navigate to **CloudWatch → Dashboards**
2. Click **heart-disease-mlops**
3. View real-time metrics

### AWS CLI

```bash
# Get dashboard definition
aws cloudwatch get-dashboard --dashboard-name heart-disease-mlops

# List all dashboards
aws cloudwatch list-dashboards
```

### Presigned URL (for sharing)

```bash
# Generate temporary URL (good for 1 hour)
aws cloudwatch get-dashboard --dashboard-name heart-disease-mlops \
  --query 'DashboardArn' --output text

# Or create in console and share
```

---

## Alarm States

| State | Meaning | Action |
|-------|---------|--------|
| **OK** | Metric within threshold | None |
| **ALARM** | Metric exceeded threshold | SNS notification sent |
| **INSUFFICIENT_DATA** | Not enough data yet | Wait for more metrics |

**Note:** New alarms start in `INSUFFICIENT_DATA` — this is normal, wait 1-2 evaluation periods.

---

## SNS Email Subscription

If you didn't set `alarm_email` in Terraform, subscribe manually:

```bash
# Subscribe your email
aws sns subscribe \
    --topic-arn $(terraform output -raw sns_topic_arn) \
    --protocol email \
    --notification-endpoint your-email@example.com

# List subscriptions
aws sns list-subscriptions-by-topic \
    --topic-arn $(terraform output -raw sns_topic_arn)
```

**You must confirm the subscription** by clicking the link in the email AWS sends you.

---

## Testing Alarms

### CPU Alarm Test

```bash
# SSH to EC2 and stress CPU
ssh -i ~/.ssh/id_ed25519 -T ubuntu@32.196.26.238
sudo apt-get install -y stress
stress --cpu 4 --timeout 300  # 5 minutes of 100% CPU
```

Watch CloudWatch — alarm should trigger within 10 minutes.

### Drift Alarm Test

```python
# Manually push a high drift score
from monitoring.cloudwatch_metrics import push_drift_metrics
push_drift_metrics(drift_score=0.5, drift_detected=True)
```

Alarm should trigger on next evaluation period.

---

## Troubleshooting

### Dashboard Not Showing Custom Metrics

Custom metrics take a few minutes to appear. Wait 5 minutes, refresh.

### Memory Metrics Missing

CloudWatch agent not installed or configured:

```bash
# Check agent status
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -m ec2 -a status

# Check logs
sudo tail -f /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log
```

### Alarm Not Triggering

```bash
# Check alarm state
aws cloudwatch describe-alarms --alarm-names heart-disease-mlops-high-cpu

# Check SNS topic
aws sns get-topic-attributes --topic-arn $(terraform output -raw sns_topic_arn)

# Check if email is confirmed
aws sns list-subscriptions-by-topic --topic-arn $(terraform output -raw sns_topic_arn)
```

### SNS Email Not Received

- Check spam folder
- Verify email is confirmed: look for "Confirmed" in subscription list
- Check AWS region matches your deployment
