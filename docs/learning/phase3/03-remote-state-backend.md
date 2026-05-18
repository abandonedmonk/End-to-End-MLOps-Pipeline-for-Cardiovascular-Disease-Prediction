# 03 — Remote State Backend (S3 + DynamoDB)

## What We Did

Migrated Terraform state from local disk to S3 with DynamoDB state locking:

1. Created DynamoDB table `heart-disease-mlops-tflock` for state locking
2. Configured the existing S3 bucket `heart-disease-mlops-695074562426-tfstate` with versioning + encryption
3. Uncommented `backend.tf` and ran `terraform init -migrate-state` to copy local state to S3
4. Verified the local `.tfstate` file is now empty (state lives in S3)

## Why Remote State (Not Local)

| Aspect | Local State | S3 Remote State |
|--------|------------|-----------------|
| **Locking** | None — two people can `apply` simultaneously | DynamoDB prevents concurrent writes |
| **Durability** | If your disk dies, state is gone | S3 has 11 nines durability |
| **History** | Only the latest state | S3 versioning lets you rollback |
| **Team use** | Must share the file somehow | Everyone points to the same S3 key |
| **Secrets** | Stored in plaintext on disk | S3 encryption at rest |
| **CI/CD** | CI can't access your local file | CI reads from S3 with IAM role |

**Our choice**: S3 + DynamoDB — the standard Terraform remote backend for AWS. Free within free tier (DynamoDB PAY_PER_REQUEST, S3 < 1GB).

## Theory: How Terraform State Works

### What's in the State File?

The `terraform.tfstate` file is a JSON document mapping your `.tf` config to real AWS resources:

```json
{
  "version": 4,
  "serial": 40,
  "outputs": { ... },
  "resources": [
    {
      "mode": "managed",
      "type": "aws_instance",
      "name": "main",
      "instances": [{
        "attributes": {
          "id": "i-0bda8692493c15a77",
          "ami": "ami-0fc0d6e8d70ab2d42",
          "user_data": "hash-of-rendered-script"
        }
      }]
    }
  ]
}
```

This is why **losing the state file is catastrophic** — Terraform no longer knows what resources exist and will try to create duplicates on the next `apply`.

### The State Locking Problem

Without locking, this can happen:

```
Person A: terraform apply  ─── Creates EC2 ─── Updates state with EC2 ID
Person B: terraform apply  ─── Creates same EC2 ─── Overwrites state, loses A's EC2 reference
```

Result: Person A's EC2 exists in AWS but not in Terraform state. It becomes an "orphaned" resource that nobody manages.

DynamoDB locking prevents this:

```
Person A: terraform apply  ─── Acquires lock ─── Creates EC2 ─── Updates state ─── Releases lock
Person B: terraform apply  ─── Tries to acquire lock ─── BLOCKED ─── Waits ─── Gets lock after A finishes
```

### How S3 Backend Works

```
terraform apply
    │
    ├── 1. Acquire DynamoDB lock (PutItem with conditional check)
    │      Lock ID: "heart-disease-mlops-695074562426-tfstate/terraform.tfstate"
    │
    ├── 2. Download current state from S3
    │      GET s3://heart-disease-mlops-695074562426-tfstate/terraform.tfstate
    │
    ├── 3. Compute plan (config vs state vs real AWS)
    │
    ├── 4. Apply changes to AWS
    │
    ├── 5. Upload new state to S3
    │      PUT s3://heart-disease-mlops-695074562426-tfstate/terraform.tfstate
    │      → S3 creates a new version (old version still accessible)
    │
    └── 6. Release DynamoDB lock (DeleteItem)
```

## The Backend Configuration

```hcl
terraform {
  backend "s3" {
    bucket         = "heart-disease-mlops-695074562426-tfstate"
    key            = "terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "heart-disease-mlops-tflock"
  }
}
```

| Field | Purpose |
|-------|---------|
| `bucket` | S3 bucket that holds the state file |
| `key` | Object key (path) within the bucket — can include prefixes like `prod/terraform.tfstate` |
| `region` | Region where the bucket lives |
| `encrypt` | Enforce server-side encryption (AES256) |
| `dynamodb_table` | Table used for state locking |

### Why a Separate S3 Bucket for State

We use `heart-disease-mlops-695074562426-tfstate` (not the main `heart-disease-mlops-695074562426` bucket) because:

1. **Security separation** — State contains secrets (RDS password). A separate bucket with stricter access is safer.
2. **Lifecycle separation** — The main bucket has lifecycle rules that expire monitoring reports. We don't want those rules affecting state.
3. **IAM separation** — CI/CD needs state read/write but not artifact read/write. Separate buckets let us scope permissions precisely.

## The DynamoDB Lock Table

```bash
aws dynamodb create-table \
  --table-name heart-disease-mlops-tflock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

| Setting | Why |
|---------|-----|
| `LockID` (String, Hash Key) | Terraform stores the lock as `bucket-key/path` (e.g., `heart-disease-mlops-695074562426-tfstate/terraform.tfstate`) |
| `PAY_PER_REQUEST` | No capacity to provision — only pays for the ~4 write/read/delete operations per `terraform apply` |
| No sort key | We only need exact lookups, not range queries |

### DynamoDB Free Tier

- 25 GB of storage (we use <1 KB)
- 25 WCUs + 25 RCUs of provisioned capacity — but we use PAY_PER_REQUEST
- PAY_PER_REQUEST gives 1 million reads + 1 million writes free per month
- Terraform uses ~4 operations per apply — effectively free

## The Migration Process

### Step-by-Step What We Did

1. **Created the S3 bucket** (already existed from earlier setup)
2. **Configured bucket security**:
   ```bash
   aws s3api put-bucket-versioning --bucket ...-tfstate --versioning-configuration Status=Enabled
   aws s3api put-bucket-encryption --bucket ...-tfstate --server-side-encryption-configuration '...'
   aws s3api put-public-access-block --bucket ...-tfstate --public-access-block-configuration ...
   ```
3. **Created the DynamoDB table** (see above)
4. **Uncommented `backend.tf`** — activated the S3 backend config
5. **Migrated state**:
   ```bash
   cd infra
   terraform init -migrate-state -force-copy
   ```

### The `-migrate-state` Flag

`terraform init` normally just downloads providers. With `-migrate-state`, it:
1. Reads the current local state
2. Writes it to the new backend (S3)
3. Empties the local `.tfstate` file (sets it to 0 bytes)
4. All future operations use S3

`-force-copy` skips the "are you sure?" prompt (needed in non-interactive environments).

### What If Migration Fails?

If the migration is interrupted halfway:
- Local state is still intact (it's only cleared after successful upload)
- You can retry `terraform init -migrate-state`
- If S3 has a partial state, you can delete it: `aws s3 rm s3://bucket/terraform.tfstate`

## The Stale Lock Problem We Hit

After migration, we got this error:

```
Error: Error acquiring the state lock
ConditionalCheckFailedException: The conditional request failed
Lock Info:
  ID:        66d1d000-4bc5-2149-3c32-77a879768a95
  Operation: OperationTypePlan
```

This happens when a `terraform` process is killed (e.g., Ctrl+C) before releasing the lock. The DynamoDB item remains, blocking all future operations.

### Fix: Force Unlock

```bash
terraform force-unlock 66d1d000-4bc5-2149-3c32-77a879768a95
```

**Warning**: Only use this if you're sure no other Terraform process is running. Force-unlocking while another process is active can corrupt the state.

## How to Debug

### "Error acquiring the state lock"

```bash
# Check if anyone else is running Terraform
ps aux | grep terraform

# If no one is, it's a stale lock — force unlock:
terraform force-unlock <lock-id>

# Or delete the DynamoDB item directly:
aws dynamodb delete-item \
  --table-name heart-disease-mlops-tflock \
  --key '{"LockID":{"S":"heart-disease-mlops-695074562426-tfstate/terraform.tfstate"}}'
```

### "S3 bucket does not exist"

The state bucket must exist **before** you configure it as a backend. Terraform can't create its own state bucket (chicken-and-egg problem).

```bash
aws s3 mb s3://heart-disease-mlops-695074562426-tfstate --region us-east-1
```

### "DynamoDB table does not exist"

Same chicken-and-egg problem. Create the table manually before `terraform init`:

```bash
aws dynamodb create-table --table-name heart-disease-mlops-tflock ...
```

### After Migration, `terraform plan` Shows Drift

If the user_data template changed between the last apply and the migration, Terraform will detect the difference. Check if the change would replace the EC2:

```bash
terraform plan | grep -i "replace"
```

With `user_data_replace_on_change = false` (which we added), user_data changes are **update-in-place** only — no EC2 recreation.

## Practical Tips

### Rollback State to a Previous Version

S3 versioning keeps all state versions. To rollback:

```bash
# List versions
aws s3api list-object-versions --bucket heart-disease-mlops-695074562426-tfstate --prefix terraform.tfstate

# Download a specific version
aws s3api get-object \
  --bucket heart-disease-mlops-695074562426-tfstate \
  --key terraform.tfstate \
  --version-id YOUR_VERSION_ID \
  terraform.tfstate.old
```

### Partial State for Multi-Environment Setups

For separate dev/prod states, use different keys:

```hcl
terraform {
  backend "s3" {
    key = "dev/terraform.tfstate"  # or "prod/terraform.tfstate"
  }
}
```

One bucket, multiple state files, each with its own lock.

### State Security Checklist

- [ ] S3 bucket has versioning enabled
- [ ] S3 bucket has encryption enabled
- [ ] S3 bucket blocks all public access
- [ ] DynamoDB table exists for locking
- [ ] `.tfstate` files are in `.gitignore`
- [ ] `terraform.tfvars` is in `.gitignore`
- [ ] No secrets in `.env.example` (only placeholders)

### Cost of Remote State for This Project

| Resource | Usage | Monthly cost |
|----------|-------|-------------|
| S3 state file (~66KB) | 1 object, versioned | ~$0.001 |
| DynamoDB lock table | ~4 operations/apply | ~$0.000 (within free tier) |
| S3 PUT/GET requests | ~10/month | ~$0.0005 |
| **Total** | | **< $0.01/month** |
