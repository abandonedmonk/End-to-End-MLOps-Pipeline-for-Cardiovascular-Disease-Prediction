#!/bin/bash
# setup_github_secrets.sh - Run this to set all GitHub secrets

set -e

echo "🔐 Setting up GitHub Secrets..."
echo ""

# Check if GITHUB_TOKEN is set
if [ -z "$GITHUB_TOKEN" ] && [ -z "$GH_TOKEN" ]; then
    echo "❌ ERROR: GITHUB_TOKEN or GH_TOKEN not set!"
    echo "Export your token first:"
    echo "  export GITHUB_TOKEN='ghp_xxxxxxxxxxxx'"
    exit 1
fi

# Use whichever token is available
TOKEN="${GITHUB_TOKEN:-$GH_TOKEN}"

# Ensure gh is in PATH
export PATH="$HOME/.local/bin:$PATH"

echo "1️⃣  Authenticating with GitHub..."
echo "$TOKEN" | gh auth login --with-token 2>/dev/null || {
    echo "⚠️  Note: gh might already be authenticated or using browser flow"
}

echo ""
echo "2️⃣  Getting Terraform outputs..."
cd /home/abandonedmonk/Work/ZOOMCAMP/MLOps-Zoomcamp-Project/infra

# Get ARNs from Terraform
AWS_ROLE_ARN=$(terraform output -raw github_actions_role_arn 2>/dev/null || echo "")
SNS_TOPIC_ARN=$(terraform output -raw sns_topic_arn 2>/dev/null || echo "")

if [ -z "$AWS_ROLE_ARN" ]; then
    echo "⚠️  WARNING: Could not get AWS_ROLE_ARN from Terraform"
    echo "   Make sure Terraform is applied: terraform apply"
    echo "   Or enter manually below:"
    read -p "AWS_ROLE_ARN: " AWS_ROLE_ARN
fi

if [ -z "$SNS_TOPIC_ARN" ]; then
    echo "⚠️  WARNING: Could not get SNS_TOPIC_ARN from Terraform"
    echo "   Make sure Terraform is applied: terraform apply"
    echo "   Or enter manually below:"
    read -p "SNS_TOPIC_ARN: " SNS_TOPIC_ARN
fi

echo ""
echo "   AWS_ROLE_ARN: $AWS_ROLE_ARN"
echo "   SNS_TOPIC_ARN: $SNS_TOPIC_ARN"

echo ""
echo "3️⃣  Setting GitHub Secrets..."
cd /home/abandonedmonk/Work/ZOOMCAMP/MLOps-Zoomcamp-Project

# Set AWS_ROLE_ARN
echo "   → Setting AWS_ROLE_ARN..."
echo "$AWS_ROLE_ARN" | gh secret set AWS_ROLE_ARN

# Set EC2_SSH_KEY
echo "   → Setting EC2_SSH_KEY..."
if [ -f "$HOME/.ssh/id_ed25519" ]; then
    cat "$HOME/.ssh/id_ed25519" | gh secret set EC2_SSH_KEY
else
    echo "   ⚠️  WARNING: ~/.ssh/id_ed25519 not found!"
    echo "      Please enter path to your SSH private key:"
    read -p "SSH key path: " SSH_PATH
    cat "$SSH_PATH" | gh secret set EC2_SSH_KEY
fi

# Set SNS_TOPIC_ARN
echo "   → Setting SNS_TOPIC_ARN..."
echo "$SNS_TOPIC_ARN" | gh secret set SNS_TOPIC_ARN

echo ""
echo "4️⃣  Verifying secrets..."
gh secret list

echo ""
echo "✅ Done! All GitHub secrets configured."
echo ""
echo "Next steps:"
echo "  1. Check CI/CD workflows will now work"
echo "  2. Test with a small PR or empty commit"
