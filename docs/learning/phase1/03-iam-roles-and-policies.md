# 03 — IAM Roles and Policies

## What We Did

Created two IAM roles:

1. **EC2 Instance Role** — attached to the EC2 instance via an instance profile, allowing it to access S3, ECR, CloudWatch, and SSM without stored credentials
2. **GitHub Actions OIDC Role** — (conditional) allows GitHub Actions to assume an AWS role without long-lived access keys

Resources created:
- 1 IAM Role (`heart-disease-mlops-ec2-role`)
- 1 IAM Policy (custom S3 read/write)
- 4 Policy Attachments (S3, ECR ReadOnly, CloudWatch Agent, SSM Managed)
- 1 Instance Profile (binds role to EC2)
- 1 OIDC Provider for GitHub (optional)
- 1 GitHub Actions Role + Policy (optional)

## Theory: IAM Concepts

### The Problem IAM Solves

Without IAM roles, you'd need to:
1. Create an AWS access key
2. Store it on the EC2 instance (in a file or environment variable)
3. Rotate it when it expires
4. Hope nobody finds it

With IAM roles + instance profiles:
1. EC2 automatically gets temporary credentials
2. Credentials rotate automatically (every few hours)
3. No secrets stored on the instance
4. Fine-grained permissions via policies

### IAM Role vs IAM User

| | IAM User | IAM Role |
|---|---------|----------|
| Has long-lived credentials? | Yes (access key) | No |
| Who assumes it? | People, scripts | Services (EC2, Lambda), federated users |
| Credential rotation | Manual | Automatic |
| Use case | CLI access, CI/CD | EC2 instances, Lambda, cross-account |

### Instance Profile

An instance profile is a **container for an IAM role** that EC2 can assume. You attach the instance profile to EC2, and the EC2 instance gets the role's permissions.

```
IAM Role → Instance Profile → EC2 Instance
                ↑
        This is what Terraform attaches
```

You can't attach a role directly to EC2 — you must use an instance profile. Terraform handles this:

```hcl
resource "aws_iam_instance_profile" "ec2" {
  name = "heart-disease-mlops-ec2-profile"
  role = aws_iam_role.ec2_instance.name  # Reference the role
}
```

### Trust Policy (Assume Role)

A role is useless without a trust policy — it defines **who can assume the role**:

```json
{
  "Effect": "Allow",
  "Principal": { "Service": "ec2.amazonaws.com" },
  "Action": "sts:AssumeRole"
}
```

This says: "The EC2 service can assume this role." Without this, nothing happens.

### Permission Policies

We attach both AWS-managed and custom policies:

| Policy | Type | What It Allows |
|--------|------|---------------|
| `AmazonEC2ContainerRegistryReadOnly` | AWS-managed | Pull Docker images from ECR |
| `CloudWatchAgentServerPolicy` | AWS-managed | Send logs and metrics to CloudWatch |
| `AmazonSSMManagedInstanceCore` | AWS-managed | SSM Session Manager (SSH without port 22) |
| `heart-disease-mlops-ec2-s3-policy` | Custom | Read/write to our S3 bucket only |

### Custom Policy (Least Privilege)

Our custom S3 policy is scoped to **one bucket**:

```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
  "Resource": [
    "arn:aws:s3:::heart-disease-mlops-695074562426",
    "arn:aws:s3:::heart-disease-mlops-695074562426/*"
  ]
}
```

Compare with `AmazonS3FullAccess` — that would allow access to **every S3 bucket in the account**. Least privilege means granting only the permissions needed for the task.

### OIDC (OpenID Connect) for GitHub Actions

Without OIDC, CI/CD typically works like this:
1. Create an AWS access key
2. Store it as a GitHub Secret
3. GitHub Actions uses the key to authenticate
4. The key never expires — if leaked, it's compromised forever

With OIDC:
1. AWS trusts GitHub's identity provider
2. GitHub Actions requests temporary credentials using a JWT token
3. The token is scoped to a specific repo + branch
4. Credentials expire after 1 hour
5. No long-lived keys stored anywhere

```hcl
# Trust policy for GitHub OIDC
condition {
  test     = "StringLike"
  variable = "token.actions.githubusercontent.com:sub"
  values   = ["repo:your-org/your-repo:*"]
}
```

This means: "Only allow this role to be assumed from workflows in `your-org/your-repo`."

## How to Debug

### EC2 Can't Access S3

```bash
# SSH into EC2
ssh -i ~/.ssh/id_ed25519 ubuntu@32.196.26.238

# Check if instance profile is attached
aws sts get-caller-identity
# Should show: "arn:aws:sts::695074562426:assumed-role/heart-disease-mlops-ec2-role/..."

# If it shows "arn:aws:iam::695074562426:user/firstuser" instead,
# that means it's using your CLI credentials, not the instance profile

# Test S3 access
aws s3 ls s3://heart-disease-mlops-695074562426/
# If "Access Denied" → check the policy ARN and resource scope
```

### Checking Effective Permissions

```bash
# From your local machine — simulate what EC2 can do
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::695074562426:role/heart-disease-mlops-ec2-role \
  --action-names s3:GetObject s3:PutObject s3:DeleteObject \
  --resource-arns arn:aws:s3:::heart-disease-mlops-695074562426/data/raw/test.csv
```

### Instance Profile Not Found on Launch

This is a race condition — IAM propagation takes 5-15 seconds. Terraform's `depends_on` fixes this:

```hcl
module "ec2" {
  source     = "./modules/ec2"
  depends_on = [module.iam]  # Wait for IAM before launching EC2
}
```

Without it, you get:
```
Error: IAM instance profile "heart-disease-mlops-ec2-profile" not found
```

### OIDC Trust Policy Not Working

GitHub Actions fails with `Not authorized to perform sts:AssumeRoleWithWebIdentity`:

1. Check the repo name matches exactly: `repo:org/repo:*` (case-sensitive)
2. Check the OIDC provider thumbprint hasn't changed (GitHub rotates keys)
3. Check the `aud` claim matches: `sts.amazonaws.com`

## Practical Tips

### Always Use Instance Profiles for EC2

Never put AWS credentials in user_data or environment files on EC2. The instance profile handles authentication automatically:

```bash
# On EC2 — no credentials needed, instance profile provides them
aws s3 cp data.csv s3://heart-disease-mlops-695074562426/data/raw/
```

### Use AWS-Managed Policies When Possible

AWS-managed policies (like `CloudWatchAgentServerPolicy`) are maintained by AWS. They're broader than custom policies but save you from writing and updating policy documents for standard use cases.

### Scope Custom Policies to Specific Resources

```json
// Bad — access to ALL buckets
"Resource": "*"

// Good — access to only our bucket
"Resource": [
  "arn:aws:s3:::heart-disease-mlops-695074562426",
  "arn:aws:s3:::heart-disease-mlops-695074562426/*"
]
```

The first resource ARN (without `/*`) covers `s3:ListBucket`. The second (with `/*`) covers `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`. Both are needed — ListBucket operates on the bucket, the others operate on objects.
