#!/bin/bash
set -e

# Automated GitHub OIDC Setup for AWS
# Usage: ./scripts/setup-oidc.sh [github-username/repo-name]

GITHUB_REPO=${1}

if [ -z "$GITHUB_REPO" ]; then
    echo "Usage: ./scripts/setup-oidc.sh github-username/repo-name"
    echo "Example: ./scripts/setup-oidc.sh oscarmccullough/floating-beach-01770"
    exit 1
fi

echo "🔐 Setting up GitHub OIDC for AWS Lightsail"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Repository: ${GITHUB_REPO}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI is not installed. Please install it first."
    exit 1
fi

# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "✅ AWS Account ID: ${ACCOUNT_ID}"

# Step 1: Create OIDC Provider (if doesn't exist)
echo ""
echo "📋 Step 1/5: Creating OIDC Identity Provider..."

OIDC_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"

if aws iam get-open-id-connect-provider --open-id-connect-provider-arn ${OIDC_ARN} &> /dev/null; then
    echo "✅ OIDC provider already exists"
else
    echo "Creating OIDC provider..."
    aws iam create-open-id-connect-provider \
        --url https://token.actions.githubusercontent.com \
        --client-id-list sts.amazonaws.com \
        --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
    echo "✅ OIDC provider created"
fi

# Step 2: Create Trust Policy
echo ""
echo "📋 Step 2/5: Creating IAM trust policy..."

cat > /tmp/github-trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:${GITHUB_REPO}:*"
        }
      }
    }
  ]
}
EOF

echo "✅ Trust policy created for repo: ${GITHUB_REPO}"

# Step 3: Create IAM Role
echo ""
echo "📋 Step 3/5: Creating IAM role..."

ROLE_NAME="GitHubActionsARFIDDeploy"

if aws iam get-role --role-name ${ROLE_NAME} &> /dev/null; then
    echo "⚠️  Role ${ROLE_NAME} already exists. Updating trust policy..."
    aws iam update-assume-role-policy \
        --role-name ${ROLE_NAME} \
        --policy-document file:///tmp/github-trust-policy.json
    echo "✅ Trust policy updated"
else
    echo "Creating role ${ROLE_NAME}..."
    aws iam create-role \
        --role-name ${ROLE_NAME} \
        --assume-role-policy-document file:///tmp/github-trust-policy.json \
        --description "Role for GitHub Actions to deploy ARFID app to Lightsail"
    echo "✅ Role created"
fi

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

# Step 4: Create and Attach Permissions Policy
echo ""
echo "📋 Step 4/5: Creating permissions policy..."

cat > /tmp/lightsail-deploy-policy.json << 'EOF'
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
EOF

POLICY_NAME="LightsailDeploymentPolicy"
POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/${POLICY_NAME}"

if aws iam get-policy --policy-arn ${POLICY_ARN} &> /dev/null; then
    echo "✅ Policy ${POLICY_NAME} already exists"
else
    echo "Creating policy ${POLICY_NAME}..."
    aws iam create-policy \
        --policy-name ${POLICY_NAME} \
        --policy-document file:///tmp/lightsail-deploy-policy.json \
        --description "Permissions for deploying ARFID app to Lightsail"
    echo "✅ Policy created"
fi

# Attach policy to role
echo "Attaching policy to role..."
aws iam attach-role-policy \
    --role-name ${ROLE_NAME} \
    --policy-arn ${POLICY_ARN} 2>/dev/null || echo "✅ Policy already attached"

echo "✅ Permissions configured"

# Step 5: Configure GitHub Secrets
echo ""
echo "📋 Step 5/5: Configuring GitHub Secrets..."

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo ""
    echo "⚠️  GitHub CLI (gh) is not installed."
    echo ""
    echo "Manual setup required:"
    echo "1. Go to: https://github.com/${GITHUB_REPO}/settings/secrets/actions"
    echo "2. Add secret: AWS_ROLE_ARN = ${ROLE_ARN}"
    echo ""
    echo "Or install GitHub CLI:"
    echo "  macOS: brew install gh"
    echo "  Linux: https://github.com/cli/cli/blob/trunk/docs/install_linux.md"
else
    # Check if authenticated
    if ! gh auth status &> /dev/null; then
        echo "🔑 Not authenticated with GitHub. Logging in..."
        gh auth login
    fi

    echo "Setting AWS_ROLE_ARN secret..."
    gh secret set AWS_ROLE_ARN -b"${ROLE_ARN}" -R ${GITHUB_REPO}
    echo "✅ AWS_ROLE_ARN secret set"

    # Prompt for other secrets
    echo ""
    read -p "Do you want to set other secrets now? (OPENAI_API_KEY, FLASK_SECRET_KEY, REDIS_URL) [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter OPENAI_API_KEY: " OPENAI_KEY
        gh secret set OPENAI_API_KEY -b"${OPENAI_KEY}" -R ${GITHUB_REPO}

        read -p "Generate FLASK_SECRET_KEY automatically? [Y/n]: " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            FLASK_SECRET=$(openssl rand -hex 32)
            gh secret set FLASK_SECRET_KEY -b"${FLASK_SECRET}" -R ${GITHUB_REPO}
            echo "✅ Generated and set FLASK_SECRET_KEY"
        fi

        read -p "Enter REDIS_URL (Upstash): " REDIS_URL
        gh secret set REDIS_URL -b"${REDIS_URL}" -R ${GITHUB_REPO}

        echo "✅ All secrets configured!"
    fi
fi

# Cleanup temp files
rm -f /tmp/github-trust-policy.json /tmp/lightsail-deploy-policy.json

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ GitHub OIDC Setup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Summary:"
echo "  OIDC Provider: ✅ Created"
echo "  IAM Role: ${ROLE_NAME}"
echo "  Role ARN: ${ROLE_ARN}"
echo "  Policy: ${POLICY_NAME}"
echo "  Repository: ${GITHUB_REPO}"
echo ""
echo "🔐 GitHub Secret Required:"
echo "  AWS_ROLE_ARN = ${ROLE_ARN}"
echo ""
echo "📚 Additional Secrets Needed:"
echo "  OPENAI_API_KEY - Your OpenAI API key"
echo "  FLASK_SECRET_KEY - Generate with: openssl rand -hex 32"
echo "  REDIS_URL - Your Upstash Redis URL"
echo ""
echo "🚀 Next Steps:"
echo "  1. Verify secrets at: https://github.com/${GITHUB_REPO}/settings/secrets/actions"
echo "  2. Commit and push to trigger deployment:"
echo "     git push origin main"
echo "  3. Monitor deployment:"
echo "     gh run watch"
echo ""
echo "📖 Full documentation: docs/GITHUB_OIDC_SETUP.md"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
