# Phase 9 — Security Hardening

Comprehensive security hardening for the Heart Disease MLOps project on AWS.

---

## Quick Start

**What you need to do (30-60 minutes):**

```bash
# 1. Get your IP
curl https://checkip.amazonaws.com
# → Example: 203.0.113.50/32

# 2. Purge .env from git history
git filter-repo --path .env --invert-paths
git push origin --force --all

# 3. Rotate AWS keys (AWS Console → IAM → firstuser → Security credentials)
# Deactivate old key (AKIA2DVNMEF5JTWDIJM7)
# Create new key, update local .env

# 4. Set GitHub Secrets
gh secret set AWS_ROLE_ARN --body "arn:aws:iam::695074562426:role/heart-disease-mlops-github-actions"
cat ~/.ssh/id_ed25519 | gh secret set EC2_SSH_KEY
gh secret set SNS_TOPIC_ARN --body "arn:aws:sns:us-east-1:695074562426:heart-disease-mlops-alarms"

# 5. Apply IP restrictions
# Edit infra/terraform.tfvars → your_ip = "203.0.113.50/32"
cd infra && terraform apply -target=module.ec2

# 6. Install pre-commit hooks
pre-commit install
pre-commit run --all-files
```

---

## What's Already Done

✅ **Pre-commit hooks configured** — Security scanning on every commit  
✅ **Enhanced .gitignore** — Blocks credential files  
✅ **Terraform IP restrictions** — Security groups ready, just need your IP  
✅ **OIDC trust** — GitHub Actions uses short-lived tokens (no stored credentials)

---

## Documentation

| File | Topic |
|------|-------|
| [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) | Complete setup guide with all CLI commands |
| [phase9-overview.md](phase9-overview.md) | Architecture, decisions, verification |

---

## Security Checklist

- [ ] `.env` purged from git history (no AWS keys in git)
- [ ] AWS keys rotated, old key deactivated
- [ ] Pre-commit hooks installed locally
- [ ] GitHub Secrets configured (AWS_ROLE_ARN, EC2_SSH_KEY, SNS_TOPIC_ARN)
- [ ] Security groups restricted to your IP (not 0.0.0.0/0)
- [ ] MFA enabled on AWS account
- [ ] MFA enabled on GitHub account

---

## Verification

```bash
# Verify .env not in history
git log --all --full-history -- .env  # Should be empty

# Verify pre-commit works
pre-commit run detect-secrets --all-files  # Should pass

# Verify IP restrictions
aws ec2 describe-security-groups \
  --group-names heart-disease-mlops-ec2-sg \
  --query 'SecurityGroups[0].IpPermissions[0].IpRanges[0].CidrIp'

# Verify GitHub secrets
gh secret list
```

---

## Emergency Procedures

**If you accidentally commit secrets:**
1. Immediately rotate the exposed key (AWS Console)
2. Purge from history: `git filter-repo --path <file> --invert-paths`
3. Force push: `git push origin --force --all`
4. Notify team to re-clone repository

**If you lose SSH access after IP restriction:**
1. Get new IP: `curl https://checkip.amazonaws.com`
2. Update terraform.tfvars
3. Run: `terraform apply -target=module.ec2` from another machine with AWS access
4. Or use AWS Systems Manager Session Manager (if enabled)

---

## Cost Impact

**Zero additional cost.** Security hardening uses:
- Pre-commit hooks (local, free)
- GitHub Secrets (free for public repos)
- Security group rules (free)
- AWS IAM/OIDC (free)

---

## Next Steps After Phase 9

- ✅ Project is production-ready with security hardening
- Consider: VPC Flow Logs for network monitoring
- Consider: AWS CloudTrail for API audit logging
- Consider: Regular security audits (quarterly)
