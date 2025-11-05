# GitHub OIDC Setup for AWS Lightsail Deployment

This guide shows you how to set up GitHub OIDC (OpenID Connect) authentication with AWS for secure, keyless deployments.

## Why OIDC?

✅ **More secure** - No long-lived AWS credentials stored in GitHub
✅ **Automatic rotation** - Temporary credentials that expire
✅ **Better compliance** - Follows AWS security best practices
✅ **Auditable** - Clear identity in CloudTrail logs

## Prerequisites

- AWS account with admin access
- GitHub repository with Actions enabled
- AWS CLI installed

## Step 1: Create OIDC Identity Provider in AWS

### Using AWS Console:

1. Go to [IAM Console](https://console.aws.amazon.com/iam/)
2. Navigate to **Identity providers** → **Add provider**
3. Select **OpenID Connect**
4. Configure:
   - **Provider URL**: `https://token.actions.githubusercontent.com`
   - **Audience**: `sts.amazonaws.com`
5. Click **Add provider**

### Using AWS CLI:

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

The thumbprint is GitHub's current certificate thumbprint (updated periodically by AWS).

## Step 2: Create IAM Role for GitHub Actions

### Create Trust Policy

Create a file named `github-trust-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_USERNAME/floating-beach-01770:*"
        }
      }
    }
  ]
}
```

**Replace:**
- `YOUR_ACCOUNT_ID` - Your AWS account ID (12 digits)
- `YOUR_GITHUB_USERNAME` - Your GitHub username or organization

**Security Options:**

For tighter security, restrict to specific branches:
```json
"token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_USERNAME/floating-beach-01770:ref:refs/heads/main"
```

### Get Your AWS Account ID

```bash
aws sts get-caller-identity --query Account --output text
```

### Update the Trust Policy File

```bash
# Save your account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Your GitHub username
GITHUB_USER="your-username"

# Update the trust policy
sed -i.bak "s/YOUR_ACCOUNT_ID/$ACCOUNT_ID/g" github-trust-policy.json
sed -i.bak "s/YOUR_GITHUB_USERNAME/$GITHUB_USER/g" github-trust-policy.json
```

### Create the IAM Role

```bash
aws iam create-role \
  --role-name GitHubActionsARFIDDeploy \
  --assume-role-policy-document file://github-trust-policy.json \
  --description "Role for GitHub Actions to deploy ARFID app to Lightsail"
```

## Step 3: Attach Permissions to the Role

Create a permissions policy file named `lightsail-deploy-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudFormationAccess",
      "Effect": "Allow",
      "Action": [
        "cloudformation:CreateStack",
        "cloudformation:UpdateStack",
        "cloudformation:DeleteStack",
        "cloudformation:DescribeStacks",
        "cloudformation:DescribeStackEvents",
        "cloudformation:DescribeStackResources",
        "cloudformation:GetTemplate",
        "cloudformation:ValidateTemplate",
        "cloudformation:ListStacks"
      ],
      "Resource": [
        "arn:aws:cloudformation:*:*:stack/arfid-*/*"
      ]
    },
    {
      "Sid": "LightsailFullAccess",
      "Effect": "Allow",
      "Action": [
        "lightsail:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ECRAccess",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "*"
    },
    {
      "Sid": "IAMPassRole",
      "Effect": "Allow",
      "Action": [
        "iam:PassRole"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": "lightsail.amazonaws.com"
        }
      }
    }
  ]
}
```

### Create and Attach the Policy

```bash
# Create the policy
aws iam create-policy \
  --policy-name LightsailDeploymentPolicy \
  --policy-document file://lightsail-deploy-policy.json

# Get your account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Attach the policy to the role
aws iam attach-role-policy \
  --role-name GitHubActionsARFIDDeploy \
  --policy-arn arn:aws:iam::${ACCOUNT_ID}:policy/LightsailDeploymentPolicy
```

## Step 4: Get the Role ARN

```bash
aws iam get-role \
  --role-name GitHubActionsARFIDDeploy \
  --query 'Role.Arn' \
  --output text
```

**Save this ARN!** You'll need it for GitHub Secrets.

Example output: `arn:aws:iam::123456789012:role/GitHubActionsARFIDDeploy`

## Step 5: Configure GitHub Secrets

Go to your GitHub repository → **Settings** → **Secrets and variables** → **Actions**

Add the following secrets:

### Required Secrets:

1. **`AWS_ROLE_ARN`** - The role ARN from Step 4
   ```
   arn:aws:iam::123456789012:role/GitHubActionsARFIDDeploy
   ```

2. **`OPENAI_API_KEY`** - Your OpenAI API key
   ```
   sk-...
   ```

3. **`FLASK_SECRET_KEY`** - Generate with:
   ```bash
   openssl rand -hex 32
   ```

4. **`REDIS_URL`** - Your Upstash Redis URL
   ```
   rediss://default:...@us1-xxx.upstash.io:6379
   ```

### Using GitHub CLI:

```bash
# Install GitHub CLI
brew install gh  # macOS
# or see https://cli.github.com/

# Login
gh auth login

# Set secrets
gh secret set AWS_ROLE_ARN -b"arn:aws:iam::123456789012:role/GitHubActionsARFIDDeploy"
gh secret set OPENAI_API_KEY -b"sk-your-key"
gh secret set FLASK_SECRET_KEY -b"$(openssl rand -hex 32)"
gh secret set REDIS_URL -b"rediss://default:...@upstash.io:6379"
```

### Optional: AWS Region

If you want to deploy to a different region, add:

```bash
gh secret set AWS_REGION -b"us-west-2"
```

## Step 6: Verify OIDC Setup

Test the workflow:

1. Commit and push a change:
   ```bash
   git add .
   git commit -m "Test OIDC deployment"
   git push origin main
   ```

2. Watch the deployment:
   ```bash
   gh run watch
   ```

3. Check the logs for successful authentication:
   ```
   ✅ Assuming role: arn:aws:iam::123456789012:role/GitHubActionsARFIDDeploy
   ```

## Troubleshooting

### Error: "Not authorized to perform sts:AssumeRoleWithWebIdentity"

**Cause**: Trust policy doesn't match your repository

**Fix**: Check the repository name in trust policy matches exactly:
```bash
aws iam get-role \
  --role-name GitHubActionsARFIDDeploy \
  --query 'Role.AssumeRolePolicyDocument'
```

### Error: "No OIDC provider found"

**Cause**: OIDC provider not created

**Fix**: Create the provider:
```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com
```

### Error: "Access Denied" during deployment

**Cause**: Role permissions insufficient

**Fix**: Verify policy is attached:
```bash
aws iam list-attached-role-policies \
  --role-name GitHubActionsARFIDDeploy
```

### Error: "thumbprint mismatch"

**Cause**: GitHub certificate changed

**Fix**: Update thumbprint (AWS usually does this automatically):
```bash
# Get current thumbprint
aws iam get-open-id-connect-provider \
  --open-id-connect-provider-arn arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com

# Update if needed
aws iam update-open-id-connect-provider-thumbprint \
  --open-id-connect-provider-arn arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

## Security Best Practices

### 1. Restrict by Branch

Limit to main branch only:
```json
"token.actions.githubusercontent.com:sub": "repo:owner/repo:ref:refs/heads/main"
```

### 2. Restrict by Environment

Require GitHub environment approval:
```json
"token.actions.githubusercontent.com:sub": "repo:owner/repo:environment:production"
```

### 3. Least Privilege

Only grant necessary Lightsail permissions:
```json
{
  "Effect": "Allow",
  "Action": [
    "lightsail:CreateContainerService",
    "lightsail:UpdateContainerService",
    "lightsail:GetContainerServices",
    "lightsail:PushContainerImage",
    "lightsail:CreateContainerServiceDeployment"
  ],
  "Resource": "arn:aws:lightsail:*:*:ContainerService/arfid-*"
}
```

### 4. Use Session Tags

Add session tags for better auditing:
```yaml
- name: Configure AWS credentials
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
    aws-region: us-east-1
    role-session-name: GitHubActions-${{ github.run_id }}
```

## Monitoring

### View CloudTrail Logs

Check who assumed the role:
```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue=GitHubActionsARFIDDeploy \
  --max-items 10
```

### IAM Access Analyzer

Enable IAM Access Analyzer to detect overly permissive policies:
```bash
aws accessanalyzer create-analyzer \
  --analyzer-name GitHubActionsAnalyzer \
  --type ACCOUNT
```

## Cleanup

To remove OIDC setup:

```bash
# Detach policy
aws iam detach-role-policy \
  --role-name GitHubActionsARFIDDeploy \
  --policy-arn arn:aws:iam::ACCOUNT_ID:policy/LightsailDeploymentPolicy

# Delete policy
aws iam delete-policy \
  --policy-arn arn:aws:iam::ACCOUNT_ID:policy/LightsailDeploymentPolicy

# Delete role
aws iam delete-role \
  --role-name GitHubActionsARFIDDeploy

# Delete OIDC provider
aws iam delete-open-id-connect-provider \
  --open-id-connect-provider-arn arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com
```

## Migration from Access Keys

If you're migrating from AWS access keys:

1. Set up OIDC (this guide)
2. Test deployment with OIDC
3. Once working, delete the old access keys:
   ```bash
   aws iam delete-access-key \
     --user-name github-actions-user \
     --access-key-id AKIAIOSFODNN7EXAMPLE
   ```
4. Remove `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from GitHub Secrets

## Resources

- [GitHub OIDC Documentation](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [AWS IAM OIDC Provider](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)
- [aws-actions/configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials)

---

**Estimated setup time:** 10-15 minutes
**Security level:** ⭐⭐⭐⭐⭐ Excellent
