output "ec2_instance_profile_name" {
  value = aws_iam_instance_profile.ec2.name
}

output "ec2_role_arn" {
  value = aws_iam_role.ec2_instance.arn
}

output "github_actions_role_arn" {
  value = var.github_actions_enabled && var.github_repo != "" ? aws_iam_role.github_actions[0].arn : ""
}
