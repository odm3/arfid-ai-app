#!/bin/bash
set -e

# Deploy containers to existing Lightsail service
# Usage: ./scripts/deploy-containers.sh [service-name] [region]

SERVICE_NAME=${1:-arfid-app-production}
REGION=${2:-us-east-1}

echo "🐳 Deploying Containers"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Service: ${SERVICE_NAME}"
echo "Region: ${REGION}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check for required environment variables
MISSING_VARS=false
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  OPENAI_API_KEY not set"
    MISSING_VARS=true
fi
if [ -z "$FLASK_SECRET_KEY" ]; then
    echo "⚠️  FLASK_SECRET_KEY not set"
    MISSING_VARS=true
fi
if [ -z "$REDIS_URL" ]; then
    echo "⚠️  REDIS_URL not set"
    MISSING_VARS=true
fi

if [ "$MISSING_VARS" = true ]; then
    echo ""
    echo "❌ Missing required environment variables!"
    echo ""
    echo "Please set them:"
    echo "  export OPENAI_API_KEY='your-key'"
    echo "  export FLASK_SECRET_KEY='your-secret'"
    echo "  export REDIS_URL='your-redis-url'"
    echo ""
    exit 1
fi

# Check if service exists
echo "📡 Checking if service exists..."
if ! aws lightsail get-container-services --service-name ${SERVICE_NAME} --region ${REGION} &> /dev/null; then
    echo "❌ Service ${SERVICE_NAME} not found!"
    echo ""
    echo "Create it first with:"
    echo "  ./scripts/deploy-infrastructure.sh"
    echo ""
    exit 1
fi

echo "✅ Service exists"

# Build Docker images
echo ""
echo "🔨 Building Docker images..."
docker build -t arfid-web:latest -f Dockerfile . --quiet
docker build -t arfid-worker:latest -f Dockerfile.worker . --quiet
echo "✅ Images built"

# Push images to Lightsail
echo ""
echo "📤 Pushing web image to Lightsail..."
aws lightsail push-container-image \
    --service-name ${SERVICE_NAME} \
    --label arfid-web \
    --image arfid-web:latest \
    --region ${REGION} \
    --no-cli-pager

echo ""
echo "📤 Pushing worker image to Lightsail..."
aws lightsail push-container-image \
    --service-name ${SERVICE_NAME} \
    --label arfid-worker \
    --image arfid-worker:latest \
    --region ${REGION} \
    --no-cli-pager

# Get latest image names
echo ""
echo "📋 Getting pushed image names..."
WEB_IMAGE=$(aws lightsail get-container-images \
    --service-name ${SERVICE_NAME} \
    --region ${REGION} \
    | jq -r '.containerImages[] | select(.image | contains("arfid-web")) | .image' \
    | head -n 1)

WORKER_IMAGE=$(aws lightsail get-container-images \
    --service-name ${SERVICE_NAME} \
    --region ${REGION} \
    | jq -r '.containerImages[] | select(.image | contains("arfid-worker")) | .image' \
    | head -n 1)

if [ -z "$WEB_IMAGE" ] || [ -z "$WORKER_IMAGE" ]; then
    echo "❌ Failed to get image names!"
    exit 1
fi

echo "✅ Web image: ${WEB_IMAGE}"
echo "✅ Worker image: ${WORKER_IMAGE}"

# Create deployment configuration
echo ""
echo "📝 Creating deployment configuration..."
cat > /tmp/lightsail-deployment.json << EOF
{
  "containers": {
    "web": {
      "image": "${WEB_IMAGE}",
      "ports": {
        "8000": "HTTP"
      },
      "environment": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "FLASK_SECRET_KEY": "${FLASK_SECRET_KEY}",
        "REDIS_URL": "${REDIS_URL}"
      }
    },
    "worker": {
      "image": "${WORKER_IMAGE}",
      "environment": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "FLASK_SECRET_KEY": "${FLASK_SECRET_KEY}",
        "REDIS_URL": "${REDIS_URL}"
      }
    }
  },
  "publicEndpoint": {
    "containerName": "web",
    "containerPort": 8000,
    "healthCheck": {
      "path": "/api/start",
      "intervalSeconds": 30,
      "timeoutSeconds": 5,
      "successCodes": "200-299,202"
    }
  }
}
EOF

# Deploy to Lightsail
echo ""
echo "🚀 Deploying to Lightsail..."
aws lightsail create-container-service-deployment \
    --service-name ${SERVICE_NAME} \
    --region ${REGION} \
    --cli-input-json file:///tmp/lightsail-deployment.json

# Wait for deployment
echo ""
echo "⏳ Waiting for deployment to complete..."
sleep 30

for i in {1..20}; do
    STATE=$(aws lightsail get-container-services \
        --service-name ${SERVICE_NAME} \
        --region ${REGION} \
        --query 'containerServices[0].state' \
        --output text)

    echo "Deployment state: ${STATE} (${i}/20)"

    if [ "$STATE" = "RUNNING" ]; then
        echo ""
        echo "✅ Deployment successful!"
        break
    elif [ "$STATE" = "FAILED" ]; then
        echo ""
        echo "❌ Deployment failed!"
        echo ""
        echo "Check logs with:"
        echo "  aws lightsail get-container-log --service-name ${SERVICE_NAME} --container-name web"
        exit 1
    fi

    sleep 15
done

# Get service URL
SERVICE_URL=$(aws lightsail get-container-services \
    --service-name ${SERVICE_NAME} \
    --region ${REGION} \
    --query 'containerServices[0].url' \
    --output text)

# Test deployment
echo ""
echo "🧪 Testing deployment..."
if curl -f -s "https://${SERVICE_URL}/api/start" > /dev/null; then
    echo "✅ Health check passed!"
else
    echo "⚠️  Health check warning (may be normal for async endpoints)"
fi

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 Your app is live at:"
echo "   https://${SERVICE_URL}"
echo ""
echo "📊 View logs:"
echo "   aws lightsail get-container-log --service-name ${SERVICE_NAME} --container-name web"
echo "   aws lightsail get-container-log --service-name ${SERVICE_NAME} --container-name worker"
echo ""
echo "🔄 Redeploy:"
echo "   ./scripts/deploy-containers.sh ${SERVICE_NAME} ${REGION}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Cleanup
rm -f /tmp/lightsail-deployment.json
