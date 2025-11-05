#!/bin/bash
set -e

# Setup GitHub Secrets for CI/CD
# Usage: ./scripts/setup-github-secrets.sh [github-repo]

GITHUB_REPO=${1}

if [ -z "$GITHUB_REPO" ]; then
    echo "Usage: ./scripts/setup-github-secrets.sh owner/repo"
    echo "Example: ./scripts/setup-github-secrets.sh oscarmccullough/floating-beach-01770"
    exit 1
fi

echo "🔐 Setting up GitHub Secrets for ${GITHUB_REPO}"
echo ""

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed."
    echo ""
    echo "Install it with:"
    echo "  macOS: brew install gh"
    echo "  Linux: https://github.com/cli/cli/blob/trunk/docs/install_linux.md"
    echo ""
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo "🔑 Not authenticated with GitHub. Logging in..."
    gh auth login
fi

echo "Required secrets:"
echo "  1. AWS_ACCESS_KEY_ID"
echo "  2. AWS_SECRET_ACCESS_KEY"
echo "  3. OPENAI_API_KEY"
echo "  4. FLASK_SECRET_KEY"
echo "  5. REDIS_URL"
echo ""

# Prompt for each secret
read -p "Enter AWS_ACCESS_KEY_ID: " AWS_ACCESS_KEY_ID
read -p "Enter AWS_SECRET_ACCESS_KEY: " AWS_SECRET_ACCESS_KEY
read -p "Enter OPENAI_API_KEY: " OPENAI_API_KEY

# Generate Flask secret if not provided
read -p "Enter FLASK_SECRET_KEY (leave empty to generate): " FLASK_SECRET_KEY
if [ -z "$FLASK_SECRET_KEY" ]; then
    FLASK_SECRET_KEY=$(openssl rand -hex 32)
    echo "Generated Flask secret: ${FLASK_SECRET_KEY}"
fi

read -p "Enter REDIS_URL: " REDIS_URL

echo ""
echo "📤 Setting GitHub secrets..."

gh secret set AWS_ACCESS_KEY_ID -b"${AWS_ACCESS_KEY_ID}" -R ${GITHUB_REPO}
gh secret set AWS_SECRET_ACCESS_KEY -b"${AWS_SECRET_ACCESS_KEY}" -R ${GITHUB_REPO}
gh secret set OPENAI_API_KEY -b"${OPENAI_API_KEY}" -R ${GITHUB_REPO}
gh secret set FLASK_SECRET_KEY -b"${FLASK_SECRET_KEY}" -R ${GITHUB_REPO}
gh secret set REDIS_URL -b"${REDIS_URL}" -R ${GITHUB_REPO}

echo ""
echo "✅ All secrets set successfully!"
echo ""
echo "📋 Secrets configured:"
echo "  ✓ AWS_ACCESS_KEY_ID"
echo "  ✓ AWS_SECRET_ACCESS_KEY"
echo "  ✓ OPENAI_API_KEY"
echo "  ✓ FLASK_SECRET_KEY"
echo "  ✓ REDIS_URL"
echo ""
echo "🚀 GitHub Actions is now ready to deploy!"
echo ""
echo "Next steps:"
echo "  1. Push to main branch to trigger deployment"
echo "  2. Monitor at: https://github.com/${GITHUB_REPO}/actions"
