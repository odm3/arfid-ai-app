#!/bin/bash
set -e

# Automated AWS Lightsail deployment script
# Usage: ./scripts/deploy-lightsail.sh [service-name] [region]

SERVICE_NAME=${1:-arfid-app}
REGION=${2:-us-east-1}
POWER=${3:-micro}  # nano, micro, small, medium, large, xlarge

echo "🚀 Deploying to AWS Lightsail"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Service: ${SERVICE_NAME}"
echo "Region: ${REGION}"
echo "Power: ${POWER}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check for required environment variables
if [ -z "$OPENAI_API_KEY" ] || [ -z "$FLASK_SECRET_KEY" ] || [ -z "$REDIS_URL" ]; then
    echo "⚠️  Missing environment variables!"
    echo ""
    echo "Please set the following:"
    echo "  export OPENAI_API_KEY='your-key'"
    echo "  export FLASK_SECRET_KEY='your-secret'"
    echo "  export REDIS_URL='your-redis-url'"
    echo ""
    read -p "Do you want to continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if Lightsail service exists
echo "📡 Checking if Lightsail service exists..."
if aws lightsail get-container-services --service-name ${SERVICE_NAME} --region ${REGION} &> /dev/null; then
    echo "✅ Service ${SERVICE_NAME} exists"
    SERVICE_EXISTS=true
else
    echo "📦 Service ${SERVICE_NAME} does not exist, will create it"
    SERVICE_EXISTS=false
fi

# Create service if it doesn't exist
if [ "$SERVICE_EXISTS" = false ]; then
    echo "🔨 Creating Lightsail container service..."
    aws lightsail create-container-service \
        --service-name ${SERVICE_NAME} \
        --power ${POWER} \
        --scale 1 \
        --region ${REGION} \
        --tags key=Application,value=arfid key=ManagedBy,value=script

    echo "⏳ Waiting for service to be active..."
    sleep 10

    # Wait for service to be ready
    for i in {1..30}; do
        STATE=$(aws lightsail get-container-services \
            --service-name ${SERVICE_NAME} \
            --region ${REGION} \
            --query 'containerServices[0].state' \
            --output text)

        if [ "$STATE" = "ACTIVE" ] || [ "$STATE" = "READY" ]; then
            echo "✅ Service is ready"
            break
        fi

        echo "Waiting... (${i}/30) State: ${STATE}"
        sleep 10
    done
fi

# Build Docker images
echo ""
echo "🔨 Building Docker images..."
docker build -t arfid-web:latest -f Dockerfile .
docker build -t arfid-worker:latest -f Dockerfile.worker .

# Push images to Lightsail
echo ""
echo "📤 Pushing web image to Lightsail..."
aws lightsail push-container-image \
    --service-name ${SERVICE_NAME} \
    --label arfid-web \
    --image arfid-web:latest \
    --region ${REGION}

echo ""
echo "📤 Pushing worker image to Lightsail..."
aws lightsail push-container-image \
    --service-name ${SERVICE_NAME} \
    --label arfid-worker \
    --image arfid-worker:latest \
    --region ${REGION}

# Get image names
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

echo "Web image: ${WEB_IMAGE}"
echo "Worker image: ${WORKER_IMAGE}"

# Get environment variables (with defaults if not set)
OPENAI_KEY=${OPENAI_API_KEY:-"YOUR_OPENAI_KEY_HERE"}
FLASK_SECRET=${FLASK_SECRET_KEY:-"YOUR_FLASK_SECRET_HERE"}
REDIS_CONNECTION=${REDIS_URL:-"YOUR_REDIS_URL_HERE"}

# Create deployment JSON
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
        "OPENAI_API_KEY": "${OPENAI_KEY}",
        "FLASK_SECRET_KEY": "${FLASK_SECRET}",
        "REDIS_URL": "${REDIS_CONNECTION}"
      }
    },
    "worker": {
      "image": "${WORKER_IMAGE}",
      "environment": {
        "OPENAI_API_KEY": "${OPENAI_KEY}",
        "FLASK_SECRET_KEY": "${FLASK_SECRET}",
        "REDIS_URL": "${REDIS_CONNECTION}"
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
echo "⏳ Waiting for deployment to complete (this may take 3-5 minutes)..."
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
        echo "Check logs with: aws lightsail get-container-log --service-name ${SERVICE_NAME} --container-name web"
        exit 1
    fi

    sleep 15
done

# Get service URL
echo ""
echo "📊 Getting service details..."
SERVICE_URL=$(aws lightsail get-container-services \
    --service-name ${SERVICE_NAME} \
    --region ${REGION} \
    --query 'containerServices[0].url' \
    --output text)

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 Your app is live at:"
echo "   https://${SERVICE_URL}"
echo ""
echo "📊 Monitor your service:"
echo "   aws lightsail get-container-services --service-name ${SERVICE_NAME}"
echo ""
echo "📜 View logs:"
echo "   aws lightsail get-container-log --service-name ${SERVICE_NAME} --container-name web"
echo "   aws lightsail get-container-log --service-name ${SERVICE_NAME} --container-name worker"
echo ""
echo "🔄 Update deployment:"
echo "   ./scripts/deploy-lightsail.sh ${SERVICE_NAME} ${REGION}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Cleanup
rm -f /tmp/lightsail-deployment.json
