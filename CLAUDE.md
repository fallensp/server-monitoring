# Server Monitoring Project

## Monthly Billing Report Routine

Generate monthly cost reports per billing center as Excel (.xlsx) files.

### Billing Centers

- **Billing Center 1 (Project: titantech)**: Resources tagged with `Project=titantech` in Singapore (ap-southeast-1) + Jakarta (ap-southeast-3)
  - EC2: c5-winlose-job (i-0d01e008541224efc), c22-server (i-0c7685dbceac08f53) in Singapore
  - EC2: sms-gateway-api (i-048793c2fa0a5d46f, t3.small) in Singapore
  - EC2: soccer-crawler-spot (i-0c03bae191d6fd71e) in Jakarta — **terminated as of Feb 2026**
  - RDS: c22-database, c5-sqlserver (both db.t3.small sqlserver-ex) in Singapore
  - Aurora Serverless V2 in Singapore — **scaled down/deleted as of Feb 2026**
  - Includes shared Singapore infrastructure costs (EC2-Other, VPC, CloudWatch, storage, data transfer)

- **Billing Center 2 (Tokyo Region)**: All resources in ap-northeast-1 — use actual costs from Cost Explorer

- **Billing Center 3 (Project: bubble)**: Resources tagged with `Project=bubble` (note: capital P) in Singapore

- **Billing Center 4 (Project: pictureworks)**: All resources in Hong Kong (ap-east-1)
  - EC2: rmbg-api-gpu (i-002afded5bb537b5d, g4dn.xlarge) — GPU instance
  - EC2: bubble-game-api (i-008e95030cd6abee4, t3.medium)
  - EC2: bubble-game-staging (i-06f7463daff5646f1, t3.small)
  - RDS: sg-postgres (db.t3.micro postgres)

### How to Generate

1. Fetch actual costs from AWS Cost Explorer for Tokyo (ap-northeast-1) — these are exact
2. Fetch actual RDS usage types for Singapore to identify Aurora costs
3. For titantech and bubble, estimate EC2/RDS compute costs based on instance types and AWS pricing (cost allocation tags are NOT activated, so Cost Explorer cannot filter by tag)
4. Add actual infrastructure costs (EBS, VPC, CloudWatch, storage) from Cost Explorer for Singapore, Jakarta, and us-east-1
5. Output as `{Month}_{Year}_Billing.xlsx` with subtotals per center and grand total

### Known Limitations

- AWS Cost Allocation Tags for `Project` are not activated — cannot query Cost Explorer by tag directly
- EC2/RDS compute costs for billing centers 1 and 3 are estimates based on instance type pricing
- Stopped instances have $0 compute cost but may still incur EBS storage charges
