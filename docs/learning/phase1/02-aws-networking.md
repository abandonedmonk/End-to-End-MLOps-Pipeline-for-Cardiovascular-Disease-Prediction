# 02 — AWS Networking (VPC, Subnets, Security Groups)

## What We Did

Created a custom VPC from scratch because the AWS account had **no default VPC** (it was deleted or never created). This is more common than you'd think — AWS accounts created before 2013 have a default VPC, but newer ones may not.

Our network layout:

```
Internet
    │
    ├── Security Group: SSH(22) + MLflow(5000) + API(8000) from your IP only
    │
    └── EC2 (Public IP: 32.196.26.238)
            │
            ├── Security Group: PostgreSQL(5432) from EC2-SG only
            │
            └── RDS PostgreSQL (Private, no public IP)
```

Resources created:
- 1 VPC (`10.0.0.0/16`)
- 2 public subnets (`10.0.0.0/24` in us-east-1a, `10.0.1.0/24` in us-east-1b)
- 1 Internet Gateway
- 1 Route Table + 2 Route Table Associations
- 2 Security Groups (EC2-SG, RDS-SG)

## Theory: VPC Concepts

### CIDR Blocks

CIDR (Classless Inter-Domain Routing) defines IP ranges:

| CIDR | IPs | Use |
|------|-----|-----|
| `10.0.0.0/16` | 65,536 | VPC — gives you room for many subnets |
| `10.0.0.0/24` | 256 | Subnet — enough for dozens of instances |
| `10.0.0.0/32` | 1 | Single IP — used in security group rules |
| `0.0.0.0/0` | All IPs | "Anywhere on the internet" — use sparingly |

The `/N` suffix means "first N bits are fixed". `/16` = first 16 bits fixed = 2^16 = 65,536 addresses.

### Public vs Private Subnets

| Feature | Public Subnet | Private Subnet |
|---------|---------------|----------------|
| Internet Gateway route | Yes | No |
| Public IP on instances | Yes | No |
| Internet access (outbound) | Yes | Only via NAT Gateway |
| Internet access (inbound) | Yes (if SG allows) | No |
| Use case | Load balancers, bastion hosts, web servers | Databases, internal APIs |

We use **only public subnets** because:
- Free tier — NAT Gateway costs ~$32/month (not free)
- EC2 needs to reach the internet (for Docker pulls, pip install, Prefect Cloud)
- RDS is "private" via security groups, not subnet routing

### Internet Gateway (IGW)

An IGW is the door between your VPC and the internet. Without it, no EC2 instance can reach anything outside the VPC — no package installs, no API calls, no Prefect Cloud.

The route table makes it work:

```
Destination    Target
10.0.0.0/16    local           # Within VPC — route locally
0.0.0.0/0      igw-xxxx        # Everything else — go to internet
```

### Security Groups vs Network ACLs

| Feature | Security Group | Network ACL |
|---------|----------------|-------------|
| Layer | Instance level | Subnet level |
| Stateful? | Yes (return traffic auto-allowed) | No (must allow both directions) |
| Allow rules only? | Yes (no deny rules) | Both allow and deny |
| Default | Deny all inbound, allow all outbound | Allow all inbound and outbound |

We use **Security Groups only** — they're sufficient and simpler. NACLs add complexity without benefit for our use case.

### Security Group Chaining

Our RDS security group references the EC2 security group:

```hcl
ingress {
  from_port        = 5432
  to_port          = 5432
  protocol         = "tcp"
  security_groups  = [var.ec2_security_group_id]  # Not a CIDR — another SG!
}
```

This means: "Allow PostgreSQL access from any instance that has the EC2 security group attached." If someone launches an EC2 in a different VPC, they can't reach RDS even if they know the endpoint — their instance doesn't have the EC2-SG.

### Why Two Subnets?

RDS requires a **DB Subnet Group** spanning at least 2 Availability Zones. Even though we run Single-AZ, the subnet group needs 2 subnets. This is an AWS requirement for RDS, not a Terraform requirement.

## How We Debugged the "No Default VPC" Problem

### Symptom

```
Error: no matching EC2 VPC found
  with module.rds.data.aws_vpc.default
```

### Root Cause

Our AWS account had no default VPC. The Terraform `data "aws_vpc" "default"` data source returns nothing.

### Diagnosis

```bash
aws ec2 describe-vpcs --query 'Vpcs[*].[VpcId,IsDefault,CidrBlock]' --output table
# Output: (empty)
```

### Fix

Added a `modules/vpc/` module that creates:
- VPC with DNS support enabled
- 2 public subnets in different AZs
- Internet Gateway + route table for internet access

This adds 8 resources but is necessary. Without it, nothing works — no networking, no EC2, no RDS.

## Practical Tips

### Finding Your Public IP for Security Groups

```bash
curl https://checkip.amazonaws.com
# Output: 103.224.7.24
# Use as: 103.224.7.24/32 in your_ip variable
```

Your IP might change (ISP reassignment). If you can't SSH into EC2:
1. Check your current IP with `curl checkip.amazonaws.com`
2. Update `your_ip` in `terraform.tfvars`
3. Run `terraform apply` — it updates the security group in-place (no EC2 rebuild)

### Testing Security Group Rules

```bash
# From your machine — test if port is reachable
nc -zv 32.196.26.238 5000
# If "Connection refused" → security group allows it, but service isn't running
# If "Connection timed out" → security group blocks it (wrong IP)
# If "Connected" → both SG and service work
```

### The `map_public_ip_on_launch` Trap

```hcl
resource "aws_subnet" "public" {
  map_public_ip_on_launch = true  # Auto-assign public IP to instances
}
```

This only applies to instances launched **without** an Elastic IP. Since we use an EIP, the instance gets both a temporary public IP (from the subnet) and the EIP. The temporary IP goes away when the EIP attaches. This is normal.

### Elastic IP Costs

Elastic IPs are free **while attached to a running instance**. But:
- Allocated but unattached: $0.005/hr
- Attached to a stopped instance: $0.005/hr
- **This is NOT covered by free tier** — expect ~$3.60/month

If you want to save money during development:
```bash
# Stop EC2 when not working
aws ec2 stop-instances --instance-ids i-0bda8692493c15a77
# But EIP will charge $0.005/hr while instance is stopped
# Release EIP only if you're done for a long time (it changes IP!)
```
