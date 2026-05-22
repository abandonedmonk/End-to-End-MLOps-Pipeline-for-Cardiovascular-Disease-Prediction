# 01 — GitHub Actions & OIDC Authentication

## What is GitHub Actions?

GitHub Actions is a **CI/CD platform** built into GitHub. It automates software workflows — testing, building, and deploying — triggered by git events.

**Key Concepts:**

| Term | Meaning |
|------|---------|
| **Workflow** | YAML file defining automated tasks |
| **Job** | Set of steps that run on the same runner |
| **Step** | Individual command or action |
| **Runner** | Virtual machine (GitHub-hosted or self-hosted) |
| **Action** | Reusable unit (checkout, setup-python, etc.) |
| **Event** | Trigger (push, PR, schedule, webhook) |

---

## Example Workflow Structure

```yaml
# .github/workflows/example.yml
name: Example

on:                  # When to run
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:                # What to run
  build:
    runs-on: ubuntu-latest    # Runner type
    
    steps:           # Sequence of tasks
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run tests
        run: pytest
```

---

## The Problem: AWS Authentication

### Old Way (Bad)

Store long-lived AWS credentials in GitHub Secrets:

```yaml
- name: Configure AWS
  env:
    AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
    AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
  run: |
    aws configure set aws_access_key_id $AWS_ACCESS_KEY_ID
    aws configure set aws_secret_access_key $AWS_SECRET_ACCESS_KEY
```

**Problems:**
1. **Never expires** — If leaked, attacker has permanent access
2. **Hard to rotate** — Must update in GitHub manually
3. **Overly permissive** — Usually given broad permissions "just in case"
4. **Trust boundary** — GitHub stores your AWS keys

---

## The Solution: OIDC (OpenID Connect)

### What is OIDC?

**OIDC** allows GitHub Actions to authenticate to AWS **without stored credentials**.

Instead of:
- "Here are my AWS keys" (static)

We use:
- "AWS, trust GitHub's identity provider and verify my JWT token" (dynamic)

---

### How OIDC Works

```
┌──────────────────┐           ┌──────────────────┐
│  GitHub Actions  │           │       AWS        │
│                  │           │                  │
│  Workflow runs   │           │  OIDC Provider   │
│                  │           │  (trusted entity)│
└────────┬─────────┘           └────────┬─────────┘
         │                            │
         │  1. Request token          │
         │───────────────────────────>│
         │  "I'm GitHub Actions        │
         │   repo X, workflow Y"       │
         │                            │
         │  2. Return JWT             │
         │<───────────────────────────│
         │  (signed by GitHub)        │
         │                            │
         │  3. Exchange for AWS creds │
         │───────────────────────────>│
         │  to IAM Role via            │
         │  sts:AssumeRoleWithWebIdentity
         │                            │
         │  4. Return temp credentials│
         │<───────────────────────────│
         │  (valid 15 min)            │
         │                            │
         │  5. Use AWS services       │
         │  (ECR, EC2, etc.)         │
         └────────────────────────────┘
```

---

### AWS IAM Trust Policy

This tells AWS: "Trust GitHub's OIDC provider for this specific repo":

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:abandonedmonk/MLOps-Zoomcamp-Project:*"
        },
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        }
      }
    }
  ]
}
```

**Key Parts:**

| Element | Meaning |
|---------|---------|
| `Federated` | The OIDC provider (GitHub Actions) |
| `sub` | Subject claim — which repo/workflow (wildcard `*` for any branch) |
| `aud` | Audience — must match GitHub's audience (`sts.amazonaws.com`) |

---

### Terraform Implementation

In our infrastructure:

```hcl
# infra/modules/iam/main.tf

# 1. Create OIDC Provider
resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
  
  client_id_list = ["sts.amazonaws.com"]
  
  # GitHub's certificate thumbprint (verifies token authenticity)
  thumbprint_list = ["6938fd4e98bab03faadb97b34396831e3780aea1"]
}

# 2. Create IAM Role for GitHub Actions
resource "aws_iam_role" "github_actions" {
  name = "${var.project_name}-github-actions"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_org}/${var.github_repo}:*"
        }
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

# 3. Attach permissions policy
resource "aws_iam_role_policy" "github_actions" {
  name = "${var.project_name}-github-actions-policy"
  role = aws_iam_role.github_actions.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # ECR permissions
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload"
        ]
        Resource = var.ecr_repository_arn
      },
      {
        # ECR login needs * (no resource restriction)
        Effect = "Allow"
        Action = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        # SNS for notifications
        Effect = "Allow"
        Action = ["sns:Publish"]
        Resource = var.sns_topic_arn
      }
    ]
  })
}
```

---

### Using OIDC in Workflows

```yaml
# .github/workflows/cd.yml
name: CD

on:
  push:
    branches: [main, aws_migration]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    # REQUIRED: Allow job to request OIDC token
    permissions:
      id-token: write      # Required for OIDC
      contents: read       # Required for checkout
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      # Authenticate via OIDC
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1
      
      # Now you can use AWS CLI without explicit credentials
      - name: Login to ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2
      
      - name: Build and push
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
        run: |
          docker build -t $ECR_REGISTRY/my-app:latest .
          docker push $ECR_REGISTRY/my-app:latest
```

**Critical:** The `permissions: id-token: write` is required. Without it, OIDC won't work.

---

## Comparing Authentication Methods

| Method | Security | Complexity | Cost | Best For |
|--------|----------|------------|------|----------|
| **Stored Keys** | ❌ Poor (permanent if leaked) | ✅ Simple | Free | Quick prototypes only |
| **OIDC** | ✅ Excellent (15-min tokens) | ⚠️ Medium setup | Free | Production, multi-env |
| **IAM User** | ⚠️ Moderate (rotatable) | ⚠️ Manual rotation | Free | Legacy systems |
| **AWS Secrets Manager** | ✅ Good (auto-rotation) | ⚠️ More complex | ~$0.40/secret/month | High compliance needs |

**Recommendation:** Use OIDC for all GitHub Actions authentication. It's now the industry standard.

---

## Security Best Practices

### 1. Scope Trust Narrowly

```json
// ❌ Too broad — any repo in the org
"token.actions.githubusercontent.com:sub": "repo:my-org/*"

// ✅ Just right — specific repo only
"token.actions.githubusercontent.com:sub": "repo:my-org/my-repo:*"

// ✅ Even better — specific branches
"token.actions.githubusercontent.com:sub": [
  "repo:my-org/my-repo:ref:refs/heads/main",
  "repo:my-org/my-repo:ref:refs/heads/production"
]
```

### 2. Minimize Permissions

```json
// ❌ Too broad
"Action": "ecr:*"

// ✅ Specific actions needed
"Action": [
  "ecr:GetAuthorizationToken",
  "ecr:BatchCheckLayerAvailability",
  "ecr:PutImage"
]
```

### 3. Use Short Sessions

```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
    role-duration-seconds: 900  # 15 minutes (minimum)
```

Default is 1 hour. Use the minimum needed.

### 4. Audit Role Assumptions

```bash
# Check who assumed the role
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRoleWithWebIdentity
```

---

## Verification

### Check OIDC Provider Exists

```bash
aws iam list-open-id-connect-providers

# Response:
{
  "OpenIDConnectProviderList": [
    {
      "Arn": "arn:aws:iam::695074562426:oidc-provider/token.actions.githubusercontent.com"
    }
  ]
}
```

### Check Role Trust Policy

```bash
aws iam get-role --role-name heart-disease-mlops-github-actions

# Look for AssumeRolePolicyDocument with:
#   Principal.Federated = OIDC provider ARN
#   Condition.StringLike with your repo
```

### Test OIDC Locally

You can't fully test OIDC locally (requires GitHub token), but you can verify the role exists:

```bash
# Check role can be assumed (you need a valid token for this)
aws sts assume-role-with-web-identity \
  --role-arn arn:aws:iam::695074562426:role/heart-disease-mlops-github-actions \
  --role-session-name test \
  --web-identity-token <GITHUB_JWT_TOKEN>
```

---

## Common OIDC Errors

### Error: "Could not assume role"

**Cause:** Trust policy doesn't match the workflow's JWT claims.

**Fix:** Check `sub` claim in trust policy matches your repo exactly.

### Error: "Not authorized to perform sts:AssumeRoleWithWebIdentity"

**Cause:** Role doesn't have trust policy set up for OIDC.

**Fix:** Ensure `Federated` principal points to the OIDC provider ARN.

### Error: "Unable to request token"

**Cause:** Missing `permissions: id-token: write`.

**Fix:** Add the permission to the job.

---

## Key Takeaways

1. **OIDC eliminates stored credentials** — No AWS keys in GitHub
2. **Tokens expire automatically** — 15 minutes by default
3. **Trust policies control access** — Scope to specific repos/branches
4. **Minimal permissions** — Grant only what Actions needs
5. **Audit trail** — CloudTrail logs every assumption

---

## Further Reading

- [GitHub Docs: Using OIDC with AWS](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [AWS Docs: Creating OIDC identity providers](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)
- [Terraform AWS Provider: iam_openid_connect_provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_openid_connect_provider)
