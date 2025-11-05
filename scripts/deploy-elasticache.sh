#!/bin/bash
set -e

# Deploy ElastiCache Redis using CloudFormation
# Usage: ./scripts/deploy-elasticache.sh [environment] [region]

ENVIRONMENT=${1:-production}
REGION=${2:-us-east-1}
STACK_NAME="${ENVIRONMENT}-arfid-redis"

echo "🚀 Deploying ElastiCache Redis for ${ENVIRONMENT} in ${REGION}"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI is not installed. Please install it first."
    exit 1
fi

# Get default VPC
echo "📡 Getting default VPC..."
VPC_ID=$(aws ec2 describe-vpcs \
    --region ${REGION} \
    --filters "Name=isDefault,Values=true" \
    --query 'Vpcs[0].VpcId' \
    --output text)

if [ "$VPC_ID" == "None" ]; then
    echo "❌ No default VPC found. Please create one or specify a VPC ID."
    exit 1
fi

echo "✅ Using VPC: ${VPC_ID}"

# Get subnets
echo "📡 Getting subnets..."
SUBNET_IDS=$(aws ec2 describe-subnets \
    --region ${REGION} \
    --filters "Name=vpc-id,Values=${VPC_ID}" \
    --query 'Subnets[*].SubnetId' \
    --output text | tr '\t' ',')

if [ -z "$SUBNET_IDS" ]; then
    echo "❌ No subnets found in VPC."
    exit 1
fi

echo "✅ Using subnets: ${SUBNET_IDS}"

# Deploy CloudFormation stack
echo "🚀 Deploying CloudFormation stack..."
aws cloudformation deploy \
    --template-file cloudformation/elasticache-redis.yml \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --parameter-overrides \
        Environment=${ENVIRONMENT} \
        NodeType=cache.t3.micro \
        VpcId=${VPC_ID} \
        SubnetIds=${SUBNET_IDS} \
        LightsailCidrBlock=0.0.0.0/0 \
    --tags \
        Environment=${ENVIRONMENT} \
        Application=arfid \
    --capabilities CAPABILITY_IAM

echo "⏳ Waiting for stack to be ready (this takes 5-10 minutes)..."
aws cloudformation wait stack-create-complete \
    --stack-name ${STACK_NAME} \
    --region ${REGION} 2>/dev/null || \
aws cloudformation wait stack-update-complete \
    --stack-name ${STACK_NAME} \
    --region ${REGION}

# Get outputs
echo "📊 Getting stack outputs..."
REDIS_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --query 'Stacks[0].Outputs[?OutputKey==`RedisConnectionString`].OutputValue' \
    --output text)

echo ""
echo "✅ ElastiCache Redis deployed successfully!"
echo ""
echo "📋 Connection Details:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Redis URL: ${REDIS_ENDPOINT}"
echo ""
echo "Add this to your environment variables:"
echo "REDISCLOUD_URL=${REDIS_ENDPOINT}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 Next steps:"
echo "1. Enable VPC peering for Lightsail:"
echo "   aws lightsail enable-vpc-peering --region ${REGION}"
echo ""
echo "2. Update your Lightsail deployment with this Redis URL"
echo ""
echo "3. Estimated cost: $12-15/month"
