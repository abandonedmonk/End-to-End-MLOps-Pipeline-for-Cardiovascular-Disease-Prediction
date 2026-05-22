# Phase 9 Overview — Security Hardening

This phase removes all secrets from the repository and establishes secure development practices. Security is not a one-time task but an ongoing discipline.

---

## The Problem We Solved

### What Was Wrong
1. **AWS access key in `.env`** committed to git history (exposed)
2. **Security groups open to world** (`0.0.0.0/0`) — anyone could access MLflow, API
3. **No protection against future secret commits** — easy to make same mistake again
4. **Long-lived AWS credentials** — never rotated, no expiry

### Risk Assessment
| Risk | Before | After |
|------|--------|-------|
| Repository compromise | HIGH (keys in git) | LOW (keys purged, OIDC used) |
| Unauthorized EC2 access | HIGH (0.0.0.0/0) | LOW (your IP only) |
| Future secret leaks | HIGH (no prevention) | LOW (pre-commit blocks) |
| Credential rotation | NONE (never rotated) | REGULAR (90-day policy) |

---

## What We Built

### 1. Pre-commit Security Hooks

**Pattern:** Run security checks on every commit before it enters git history.

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```

**How it works:**
1. You stage files: `git add .`
2. You commit: `git commit -m "update"`
3. Pre-commit runs automatically, checks for secrets
4. If secrets found → commit BLOCKED, you must fix
5. If clean → commit proceeds

**Key insight:** It's much easier to prevent a commit than to purge history later.

### 2. Git History Purge

**Why not just `git rm`?**
- `git rm` removes from current commit, but history still contains the secret
- Anyone with clone access can see old commits → find the key

**Solution:** `git filter-repo` (or `git filter-branch`)
- Rewrites entire git history
- Completely removes file from all commits
- Requires force push to GitHub

**Trade-off:** Rewriting history breaks clones for collaborators. Coordinate before doing this.

### 3. AWS Key Rotation

**Best practice:** Rotate credentials regularly (90 days).

**Process we implemented:**
1. Deactivate old key (don't delete immediately — safety buffer)
2. Generate new key pair
3. Update local `.env` only (never commit)
4. Test new key works
5. After 24 hours, delete old key permanently

**Key insight:** Deactivating buys you time. If something breaks, you can reactivate. Deleting is permanent.

### 4. IP Restrictions

**Security groups before:**
```
SSH (22):       0.0.0.0/0  ← Anyone on internet
MLflow (5000):  0.0.0.0/0  ← Anyone on internet
API (8000):     0.0.0.0/0  ← Anyone on internet
```

**Security groups after:**
```
SSH (22):       YOUR_IP/32  ← Only you
MLflow (5000):  YOUR_IP/32  ← Only you
API (8000):     YOUR_IP/32  ← Only you
```

**Implementation:** Terraform variable `your_ip` passed to security group rules.

**Handling dynamic IPs:**
- Home WiFi: IP changes periodically (monthly/quarterly)
- Mobile hotspot: IP changes every connection
- Solution: Update `terraform.tfvars` → `terraform apply` (30 seconds)

### 5. GitHub Secrets vs. Repository Files

**Before:** CI/CD looked for AWS credentials in repository files or used hardcoded strings.

**After:** CI/CD receives credentials via GitHub Secrets, injected at runtime.

**Benefits:**
- Secrets encrypted at rest (GitHub's KMS)
- Secrets never in code, logs, or history
- Access controlled via GitHub permissions
- Audit log of who accessed/changed secrets

**Our secrets:**
- `AWS_ROLE_ARN` — For OIDC assume role
- `EC2_SSH_KEY` — For SSH deployment
- `SNS_TOPIC_ARN` — For deployment notifications

---

## Architecture Decisions

### Why Pre-commit Hooks vs. CI Scanning?

| Approach | Speed | Feedback | Effectiveness |
|----------|-------|----------|---------------|
| Pre-commit | Instant | Before commit | High (blocks commit) |
| CI scanning | 2-5 min | After push | Medium (alerts only) |
| Both | Mixed | Multiple points | Best |

**Decision:** Pre-commit for blocking, CI as secondary defense.

### Why git-filter-repo vs. BFG Repo-Cleaner?

- `git-filter-repo`: Modern, actively maintained, faster
- `BFG Repo-Cleaner`: Simpler for just removing files
- `filter-branch`: Built-in but deprecated, slower

**Decision:** `git-filter-repo` for comprehensive history rewriting.

### Why IP Restriction vs. VPN/Bastion?

| Approach | Cost | Complexity | Security |
|----------|------|------------|----------|
| IP restriction | Free | Low | Good for static IP |
| VPN (OpenVPN) | Free tier | Medium | Excellent |
| Bastion host | $3-5/month | Medium | Excellent |
| AWS Systems Manager | Free | Low | Good, session-based |

**Decision:** IP restriction for simplicity (Phase 9), consider bastion for production scale.

### Why OIDC vs. Stored AWS Keys?

| Approach | Token Lifetime | Rotation | Security |
|----------|----------------|----------|----------|
| Long-lived keys | Permanent | Manual | Low (stolen = permanent access) |
| OIDC tokens | 15 minutes | Automatic | High (short window, no stored creds) |

**Decision:** OIDC for CI/CD (Phase 7), local keys for development (Phase 9 rotation).

---

## Verification Strategy

### How We Know Security Works

1. **Automated verification:**
   ```bash
   pre-commit run --all-files  # Should pass
   ```

2. **History verification:**
   ```bash
   git log --all --full-history -- .env  # Should be empty
   ```

3. **AWS verification:**
   ```bash
   aws ec2 describe-security-groups --group-names heart-disease-mlops-ec2-sg
   # Check IpPermissions[].IpRanges[] = ["YOUR_IP/32"]
   ```

4. **Access verification:**
   ```bash
   ssh ubuntu@32.196.26.238  # Should work from your IP
   # From different IP: Connection timeout (good!)
   ```

---

## Ongoing Security Practices

### Monthly
- [ ] Review AWS IAM user activity (unused keys? unusual API calls?)
- [ ] Check CloudTrail for unauthorized access attempts
- [ ] Verify security group rules still point to your current IP

### Quarterly
- [ ] Rotate AWS access keys (90 days)
- [ ] Audit GitHub Secrets (still needed? rotated?)
- [ ] Review pre-commit baseline (false positives accumulating?)

### Annually
- [ ] Penetration test (AWS Inspector, manual testing)
- [ ] Security group audit (remove unused ports)
- [ ] Incident response drill (key compromised — what do you do?)

---

## What Wasn't Implemented (Out of Scope)

### VPN/Bastion Host
Too complex for single-developer free tier. IP restriction is sufficient.

### AWS Secrets Manager
Costs $0.40/month per secret. Environment variables in systemd service are sufficient for this scale.

### VPC Flow Logs
Good for audit but cost $0.25/GB ingested. Not worth it for low-traffic dev environment.

### AWS Shield/WAF
DDoS protection. Overkill for this scale.

---

## Files Added

```
.pre-commit-config.yaml       # Hook configuration
.secrets.baseline            # Known non-secrets (committed)
docs/learning/phase9/
├── README.md                # Quick start guide
├── IMPLEMENTATION_SUMMARY.md  # Complete CLI commands
└── phase9-overview.md       # This file
```

---

## Metrics

| Metric | Before | After |
|--------|--------|-------|
| Secrets in git | 1 (AWS key in .env) | 0 |
| Open security group rules | 3 (0.0.0.0/0) | 0 (all IP-restricted) |
| Pre-commit protection | None | detect-secrets + aws-creds |
| Key rotation policy | None | 90 days |
| CI/CD credential storage | None/OIDC | OIDC (no stored keys) |

---

## References

- [git-filter-repo](https://github.com/newren/git-filter-repo) — Modern git history rewriting
- [detect-secrets](https://github.com/Yelp/detect-secrets) — Secret scanning by Yelp
- [pre-commit](https://pre-commit.com/) — Git hook framework
- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [GitHub Security Best Practices](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)

---

## Key Takeaway

**Security is not a destination but a practice.**

Phase 9 gives you the tools and processes to maintain security over time:
- Pre-commit hooks prevent future mistakes
- Regular key rotation limits exposure window
- IP restrictions minimize attack surface
- Monitoring lets you detect issues early

The system is now as secure as your ongoing discipline.
