#!/bin/bash
set -e

# Deploy AWS infrastructure using CloudFormation
# Usage: ./scripts/deploy-infrastructure.sh [environment] [region] [power]

ENVIRONMENT=${1:-production}
REGION=${2:-us-east-1}
POWER=${3:-micro}
STACK_NAME="arfid-${ENVIRONMENT}-infrastructure"
SERVICE_NAME="arfid-app-${ENVIRONMENT}"

echo "🏗️  Deploying AWS Infrastructure"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Environment: ${ENVIRONMENT}"
echo "Region: ${REGION}"
echo "Stack: ${STACK_NAME}"
echo "Service: ${SERVICE_NAME}"
echo "Power: ${POWER}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI is not installed. Please install it first."
    exit 1
fi

# Validate CloudFormation template
echo "✅ Validating CloudFormation template..."
aws cloudformation validate-template \
    --template-body file://cloudformation/lightsail-service.yml \
    --region ${REGION} > /dev/null

echo "✅ Template is valid"

# Deploy CloudFormation stack
echo ""
echo "🚀 Deploying CloudFormation stack..."
aws cloudformation deploy \
    --template-file cloudformation/lightsail-service.yml \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --parameter-overrides \
        ServiceName=${SERVICE_NAME} \
        Power=${POWER} \
        Scale=1 \
        Environment=${ENVIRONMENT} \
        HealthCheckPath=/api/start \
        ContainerPort=8000 \
    --tags \
        Environment=${ENVIRONMENT} \
        Application=ARFID \
        ManagedBy=CloudFormation \
    --no-fail-on-empty-changeset

echo ""
echo "⏳ Waiting for stack to be ready..."
aws cloudformation wait stack-create-complete \
    --stack-name ${STACK_NAME} \
    --region ${REGION} 2>/dev/null || \
aws cloudformation wait stack-update-complete \
    --stack-name ${STACK_NAME} \
    --region ${REGION}

# Get stack outputs
echo ""
echo "📊 Getting stack outputs..."

SERVICE_URL=$(aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --query 'Stacks[0].Outputs[?OutputKey==`ServiceUrl`].OutputValue' \
    --output text)

FULL_URL=$(aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --query 'Stacks[0].Outputs[?OutputKey==`FullUrl`].OutputValue' \
    --output text)

ESTIMATED_COST=$(aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --query 'Stacks[0].Outputs[?OutputKey==`EstimatedMonthlyCost`].OutputValue' \
    --output text)

CONSOLE_URL=$(aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --query 'Stacks[0].Outputs[?OutputKey==`ManagementConsoleUrl`].OutputValue' \
    --output text)

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Infrastructure Deployed Successfully!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Details:"
echo "  Stack: ${STACK_NAME}"
echo "  Service: ${SERVICE_NAME}"
echo "  Region: ${REGION}"
echo "  Cost: ${ESTIMATED_COST}/month"
echo ""
echo "🌐 URLs:"
echo "  Service URL: ${SERVICE_URL}"
echo "  Full URL: ${FULL_URL}"
echo "  Console: ${CONSOLE_URL}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📦 Next Steps:"
echo ""
echo "1. Deploy containers:"
echo "   ./scripts/deploy-containers.sh ${SERVICE_NAME} ${REGION}"
echo ""
echo "2. Or use the all-in-one script:"
echo "   ./scripts/deploy-all.sh ${ENVIRONMENT} ${REGION}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Save outputs to file for later use
cat > /tmp/arfid-stack-outputs.json << EOF
{
  "stackName": "${STACK_NAME}",
  "serviceName": "${SERVICE_NAME}",
  "region": "${REGION}",
  "serviceUrl": "${SERVICE_URL}",
  "fullUrl": "${FULL_URL}",
  "estimatedCost": "${ESTIMATED_COST}"
}
EOF

echo ""
echo "💾 Stack info saved to: /tmp/arfid-stack-outputs.json"
