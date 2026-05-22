# Phase 7 Implementation Summary

## What Was Built

- `.github/workflows/ci.yml`: pull request CI for `main` and `aws_migration` with flake8, black check, isort check, and a passing placeholder test step.
- `.github/workflows/cd.yml`: push-based Docker deployment to EC2 using GitHub OIDC, ECR commit-SHA image tags, health checks, rollback, and SNS notifications.
- `.github/workflows/infra.yml`: Terraform workflow for `infra/**` changes. Pull requests get `terraform plan` comments, and pushes to `main` run `terraform apply`.
- `infra/modules/iam/`: GitHub Actions OIDC provider and IAM role with ECR, SNS, Terraform backend, and infrastructure-management permissions.
- `infra/main.tf`: enables GitHub Actions OIDC for `abandonedmonk/MLOps-Zoomcamp-Project` and wires the SNS topic ARN into IAM.
- `tests/test_placeholder.py`: placeholder tests until Phase 8 adds real test coverage.
- `pyproject.toml`: adds a `dev` optional dependency group for `flake8`, `black`, `isort`, and `pytest`.

## How It Works

A pull request into `main` or `aws_migration` runs CI linting. If the PR changes Terraform under `infra/`, the infrastructure workflow authenticates to AWS through OIDC, runs `terraform plan`, and posts the plan result as a PR comment.

On push to `main` or `aws_migration`, CD builds the FastAPI Docker image, tags it as `sha-<commit>` and `latest`, and pushes both tags to ECR. The workflow then connects to EC2 over SSH, records the currently running `fastapi` container image, pulls the new image, replaces the container, and checks `http://32.196.26.238:8000/health`.

If the health check reports `"model_loaded": true`, deployment is successful and SNS sends a success notification. If health checks fail, the workflow stops the failed container and starts the previously recorded image. SNS then sends a failure/rollback notification.

## Key Design Decisions

- GitHub Actions uses AWS OIDC instead of stored AWS access keys, so there are no long-lived AWS credentials in GitHub Secrets.
- Docker images are tagged by commit SHA for deterministic rollback and by `latest` for operational convenience.
- Rollback uses the exact previous container image from `docker inspect fastapi`, not an inferred tag.
- Terraform apply only runs on pushes to `main`; `aws_migration` push runs CD but not infrastructure apply.
- The SNS topic ARN defaults to `arn:aws:sns:<region>:<account>:heart-disease-mlops-alarms`, matching the Phase 7 notification target.

## Bugs Encountered & Fixes

- Passing the monitoring module topic output directly into the IAM module would create a Terraform dependency cycle: IAM -> EC2 -> monitoring -> IAM. This was fixed by computing the known SNS topic ARN in root Terraform locals and passing that into IAM.
- The rollback step must run after a failed health check. The workflow uses `if: failure() && steps.healthcheck.outputs.status == 'failed'` so GitHub Actions does not skip rollback after the health-check step exits non-zero.
- The Terraform PR comment example needed plan output to be captured explicitly. The workflow writes the plan text to `GITHUB_ENV` before commenting.

## Configuration Required

Set these GitHub Actions secrets in `abandonedmonk/MLOps-Zoomcamp-Project`:

- `AWS_ROLE_ARN`: from `terraform output github_actions_role_arn`
- `EC2_SSH_KEY`: the private SSH key that can connect to `ubuntu@32.196.26.238`
- `SNS_TOPIC_ARN`: from `terraform output sns_topic_arn`

Recommended setup:

```bash
terraform -chdir=infra plan
terraform -chdir=infra apply

terraform -chdir=infra output github_actions_role_arn
terraform -chdir=infra output sns_topic_arn

gh secret set AWS_ROLE_ARN --body "$(terraform -chdir=infra output -raw github_actions_role_arn)"
gh secret set EC2_SSH_KEY < ~/.ssh/id_ed25519
gh secret set SNS_TOPIC_ARN --body "$(terraform -chdir=infra output -raw sns_topic_arn)"
```

## Verification Commands

```bash
# Check workflow runs
gh run list --workflow=CI
gh run list --workflow=CD
gh run list --workflow=Infrastructure

# Check OIDC provider
aws iam list-open-id-connect-providers

# Confirm role output
terraform -chdir=infra output github_actions_role_arn

# Confirm SNS output
terraform -chdir=infra output sns_topic_arn

# Test deployment on aws_migration
git commit --allow-empty -m "Test deploy"
git push origin aws_migration

# Check API health after deploy
curl http://32.196.26.238:8000/health
```
