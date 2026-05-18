#!/bin/bash
# deploy-aws.sh — Deploy the DoE backend to AWS App Runner
# Usage: ./deploy-aws.sh [--env staging|production]
set -e

REGION="${DOE_AWS_REGION:-us-east-1}"
SERVICE_NAME="doe-backend"
ENV="${1:-staging}"

# ── Prerequisites ─────────────────────────────────────────────────
if ! command -v aws &>/dev/null; then
   echo "ERROR: AWS CLI not found. Install with: pip install awscli"
   exit 1
fi

if [[ -z "${AWS_PROFILE+x}" ]]; then
   echo "NOTE: No AWS_PROFILE set. Using default credentials."
fi

# ── Build & Push to ECR ──────────────────────────────────────────
ACCOUNT_ID=$(aws sts get-caller-identifier --output text --query Account)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
REPO_NAME="${SERVICE_NAME,,}"
IMAGE_TAG="${ECR_URI}/${REPO_NAME}:latest"

echo "[1/5] Authenticating to ECR …"
aws ecr get-login-password --region "$REGION" | \
   docker login --username AWS --password-stdin "$ECR_URI"

echo "[2/5] Building Docker image …"
docker build -t "$IMAGE_TAG" ./backend
docker push "$IMAGE_TAG"

# ── Create/Update App Runner Service ──────────────────────────────
echo "[3/5] $(aws apprunner create-service \
   --service-name "$SERVICE_NAME" \
   --source-configuration ImageRepository='{ImageIdentifier='"$IMAGE_TAG"',ImageRepositoryType=ECR}' \
   --instance-roles 'arn:aws:iam::${ACCOUNT_ID}:role/apprunner-ro' \
   --health-check-config 'Timeout=30,Interval=30,SuccessfulStatusCodes=200-399' \
   --deault-configuration HealthCheckPath=/health,Concurrency=BATCH,AutoScalingConfigurationArn=arn:aws:apprunner::${ACCOUNT_ID}:scaling/your-scaling-config' \
   --instance-configuration 'Cpu=1024,Memory=2048' \
   --tags Key=env,Value=$ENV,Key=project,Value=mirai-doe \
   --cli-input-json '{\"ServiceName\":\"'"$SERVICE_NAME\"}',\"SourceConfiguration\":{\"ImageRepository\":{\"ImageIdentifier\":\"'"$IMAGE_TAG\"'\",\"ImageRepositoryType\":\"ECR\"}},\"InstanceConfiguration\":{\"Cpu\":\"1024\",\"Memory\":\"2048\"}}' \
   --output text --query 'Service.ServiceUrl')"

echo "[4/5] Service starts resolving at ~30s"
echo "[5/5] Example: http://<service-id>.$REGION.awselasticbeanstalk.com"
