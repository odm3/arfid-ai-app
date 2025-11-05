#!/bin/bash
set -e

# All-in-one deployment: Infrastructure + Containers
# Usage: ./scripts/deploy-all.sh [environment] [region] [power]

ENVIRONMENT=${1:-production}
REGION=${2:-us-east-1}
POWER=${3:-micro}
SERVICE_NAME="arfid-app-${ENVIRONMENT}"

echo "🚀 Complete AWS Deployment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: ${ENVIRONMENT}"
echo "Region: ${REGION}"
echo "Power: ${POWER}"
echo "Service: ${SERVICE_NAME}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Step 1: Deploy infrastructure
echo "📋 Step 1/2: Deploying Infrastructure (CloudFormation)"
echo ""
./scripts/deploy-infrastructure.sh ${ENVIRONMENT} ${REGION} ${POWER}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Step 2: Deploy containers
echo "📋 Step 2/2: Deploying Containers"
echo ""
./scripts/deploy-containers.sh ${SERVICE_NAME} ${REGION}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 Complete Deployment Finished!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Your ARFID app is now live on AWS Lightsail!"
echo ""
