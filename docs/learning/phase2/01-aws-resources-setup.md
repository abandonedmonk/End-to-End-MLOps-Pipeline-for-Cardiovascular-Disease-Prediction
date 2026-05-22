# 01 — AWS Resources Setup

Create and configure all AWS resources needed for MLflow: S3, RDS, IAM, security groups, and EC2 instance.

## Prerequisites

- AWS CLI installed and configured: `aws configure`
- Get your public IP: `curl -s https://checkip.amazonaws.com`
- Decide on AWS region (we use `us-east-1` for free tier availability)

## Step 1: Define Variables

Set these in your shell before running commands (customize as needed):

```bash
export AWS_REGION=us-east-1
export S3_BUCKET=heart-disease-mlops-$(date +%s)
export DB_IDENTIFIER=mlflow-db
export DB_NAME=mlflow
export DB_USER=mlflow_user
export DB_PASSWORD='MySecurePass123!'  # Change this!
export DB_CLASS=db.t3.micro
export DB_STORAGE=20
export EC2_KEY_NAME=mlops-keypair
export SECURITY_GROUP_NAME=mlflow-sg
export IAM_ROLE_NAME=EC2S3AccessRole
export INSTANCE_PROFILE_NAME=EC2S3InstanceProfile
export INSTANCE_TYPE=t3.micro

# Get your public IP (used for security group rules)
export MY_IP=$(curl -s https://checkip.amazonaws.com)/32
echo "Your IP for security group: $MY_IP"
```

**Note:** S3 bucket names are globally unique; the timestamp suffix helps avoid conflicts.

## Step 2: Create S3 Bucket

```bash
aws s3api create-bucket \
  --bucket "$S3_BUCKET" \
  --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION"

echo "✓ S3 bucket created: $S3_BUCKET"
```

## Step 3: Create IAM Role for EC2

EC2 needs permissions to read/write S3 without embedded credentials.

**Create trust policy file:**
```bash
cat > /tmp/trust-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
```

**Create role and attach policy:**
```bash
aws iam create-role \
  --role-name "$IAM_ROLE_NAME" \
  --assume-role-policy-document file:///tmp/trust-policy.json

aws iam attach-role-policy \
  --role-name "$IAM_ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess

aws iam create-instance-profile \
  --instance-profile-name "$INSTANCE_PROFILE_NAME"

aws iam add-role-to-instance-profile \
  --instance-profile-name "$INSTANCE_PROFILE_NAME" \
  --role-name "$IAM_ROLE_NAME"

echo "✓ IAM role and instance profile created"
```

## Step 4: Create Security Group

```bash
# Get default VPC
export VPC_ID=$(aws ec2 describe-vpcs \
  --filters "Name=isDefault,Values=true" \
  --query 'Vpcs[0].VpcId' \
  --output text \
  --region "$AWS_REGION")

echo "Using VPC: $VPC_ID"

# Create security group
export SG_ID=$(aws ec2 create-security-group \
  --group-name "$SECURITY_GROUP_NAME" \
  --description "MLflow access - SSH and port 5000" \
  --vpc-id "$VPC_ID" \
  --region "$AWS_REGION" \
  --query 'GroupId' \
  --output text)

echo "Security Group created: $SG_ID"

# Allow SSH from your IP
aws ec2 authorize-security-group-ingress \
  --group-id "$SG_ID" \
  --protocol tcp \
  --port 22 \
  --cidr "$MY_IP" \
  --region "$AWS_REGION"

# Allow MLflow port 5000 from your IP
aws ec2 authorize-security-group-ingress \
  --group-id "$SG_ID" \
  --protocol tcp \
  --port 5000 \
  --cidr "$MY_IP" \
  --region "$AWS_REGION"

echo "✓ Security group configured with SSH and MLflow access from $MY_IP"
```

## Step 5: Create EC2 Key Pair

```bash
# Generate and save key (one-time)
aws ec2 create-key-pair \
  --key-name "$EC2_KEY_NAME" \
  --query 'KeyMaterial' \
  --output text \
  --region "$AWS_REGION" > "${EC2_KEY_NAME}.pem"

chmod 400 "${EC2_KEY_NAME}.pem"
echo "✓ Key pair created and saved: ${EC2_KEY_NAME}.pem"

# (If key already exists, you'll get an error — that's fine)
```

## Step 6: Create RDS PostgreSQL Database

```bash
# Create RDS instance (simple config for free tier)
aws rds create-db-instance \
  --db-instance-identifier "$DB_IDENTIFIER" \
  --db-instance-class "$DB_CLASS" \
  --engine postgres \
  --engine-version 14.7 \
  --allocated-storage "$DB_STORAGE" \
  --storage-type gp2 \
  --master-username "$DB_USER" \
  --master-user-password "$DB_PASSWORD" \
  --db-name "$DB_NAME" \
  --backup-retention-period 0 \
  --publicly-accessible \
  --no-multi-az \
  --region "$AWS_REGION" \
  2>/dev/null

# If already exists, skip the error
echo "RDS instance requested. Waiting for creation..."

# Poll until available (may take 5–10 minutes)
until aws rds describe-db-instances \
  --db-instance-identifier "$DB_IDENTIFIER" \
  --query 'DBInstances[0].DBInstanceStatus' \
  --output text \
  --region "$AWS_REGION" | grep -q available; do
  echo "  Still creating RDS... (check AWS console for status)"
  sleep 30
done

# Get RDS endpoint
export DB_HOST=$(aws rds describe-db-instances \
  --db-instance-identifier "$DB_IDENTIFIER" \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text \
  --region "$AWS_REGION")

echo "✓ RDS endpoint: $DB_HOST"
```

**Note:** RDS creation takes 5–10 minutes. You can proceed to the next step in parallel.

## Step 7: Launch EC2 Instance

```bash
# Find a recent Ubuntu 22.04 LTS AMI for your region
# (Example for us-east-1; adjust for other regions)
export AMI_ID=ami-0c55b159cbfafe1f0

# Verify AMI exists
aws ec2 describe-images --image-ids "$AMI_ID" --region "$AWS_REGION" > /dev/null 2>&1 || {
  echo "AMI not found. Get latest Ubuntu AMI:"
  aws ec2 describe-images \
    --owners 099720109477 \
    --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
    --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
    --output text \
    --region "$AWS_REGION"
  exit 1
}

# Launch instance
export INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --count 1 \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$EC2_KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --iam-instance-profile Name="$INSTANCE_PROFILE_NAME" \
  --monitoring Enabled=false \
  --region "$AWS_REGION" \
  --query 'Instances[0].InstanceId' \
  --output text)

echo "✓ EC2 instance launched: $INSTANCE_ID"
echo "Waiting for public IP assignment..."

sleep 10

# Get public IP
export EC2_PUBLIC_IP=$(aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text \
  --region "$AWS_REGION")

echo "✓ EC2 public IP: $EC2_PUBLIC_IP"
```

## Step 8: Save Configuration

Save all variables for later use:

```bash
cat > ~/.mlflow-aws-config <<EOF
export AWS_REGION=$AWS_REGION
export S3_BUCKET=$S3_BUCKET
export DB_IDENTIFIER=$DB_IDENTIFIER
export DB_NAME=$DB_NAME
export DB_USER=$DB_USER
export DB_PASSWORD=$DB_PASSWORD
export DB_HOST=$DB_HOST
export EC2_KEY_NAME=$EC2_KEY_NAME
export INSTANCE_ID=$INSTANCE_ID
export EC2_PUBLIC_IP=$EC2_PUBLIC_IP
export SG_ID=$SG_ID
export MY_IP=$MY_IP
EOF

echo "✓ Configuration saved to ~/.mlflow-aws-config"
echo "Load it later with: source ~/.mlflow-aws-config"
```

## Verification Checklist

- [ ] S3 bucket exists: `aws s3 ls s3://$S3_BUCKET/`
- [ ] IAM role created: `aws iam get-role --role-name $IAM_ROLE_NAME`
- [ ] Security group created: `aws ec2 describe-security-groups --group-ids $SG_ID`
- [ ] RDS available: `aws rds describe-db-instances --db-instance-identifier $DB_IDENTIFIER --query 'DBInstances[0].DBInstanceStatus'`
- [ ] EC2 running: `aws ec2 describe-instances --instance-ids $INSTANCE_ID --query 'Reservations[0].Instances[0].State.Name'`
- [ ] Can SSH: `ssh -i ${EC2_KEY_NAME}.pem ubuntu@${EC2_PUBLIC_IP} echo "OK"`

## Troubleshooting

**Can't SSH to EC2:**
- Verify EC2 is in `running` state: `aws ec2 describe-instances --instance-ids $INSTANCE_ID`
- Check security group allows port 22 from your IP: `aws ec2 describe-security-groups --group-ids $SG_ID`
- Allow 1–2 minutes for SSH daemon to start after instance launch

**RDS stuck in "creating":**
- Check AWS console > RDS > Databases for error messages
- Free tier quota issue? Verify account has free tier access

**S3 bucket name conflict:**
- S3 names are globally unique; add a random suffix and retry

---

**Next:** Proceed to [02-mlflow-server-setup.md](02-mlflow-server-setup.md) once EC2 and RDS are running.
