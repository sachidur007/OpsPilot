#!/bin/sh
# Create a non-root IAM user and an App Runner service for the agent.
# Requires a working admin identity. Does not print secret keys.
set -eu
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REPO="opspilot-agent"
USER_NAME="opspilot-bedrock"
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"

aws iam create-user --user-name "$USER_NAME" >/dev/null 2>&1 || true
aws iam put-user-policy --user-name "$USER_NAME" --policy-name OpsPilotBedrock --policy-document "file://${ROOT}/scripts/bedrock-policy.json"
KEY_FILE="$(mktemp)"
if aws iam create-access-key --user-name "$USER_NAME" --output json >"$KEY_FILE"; then
  python3 - "$ROOT/.env" "$KEY_FILE" <<'PY'
import json, sys
from pathlib import Path
env_path, key_path = Path(sys.argv[1]), Path(sys.argv[2])
key = json.loads(key_path.read_text())["AccessKey"]
lines = env_path.read_text().splitlines() if env_path.exists() else []
keep = [line for line in lines if not line.startswith(("AWS_ACCESS_KEY_ID=", "AWS_SECRET_ACCESS_KEY=", "AWS_REGION=", "BEDROCK_MODEL_ID="))]
keep.extend([
    f"AWS_ACCESS_KEY_ID={key['AccessKeyId']}",
    f"AWS_SECRET_ACCESS_KEY={key['SecretAccessKey']}",
    "AWS_REGION=us-east-1",
    "BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-5",
])
env_path.write_text("\n".join(keep) + "\n")
print("wrote IAM access key into .env")
PY
  rm -f "$KEY_FILE"
else
  rm -f "$KEY_FILE"
  echo "IAM user exists and already has a key. Leaving .env unchanged."
fi

aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1 || \
  aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
docker build -t "$REPO" "$ROOT"
docker tag "$REPO:latest" "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:latest"
docker push "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:latest"

aws iam create-role --role-name OpsPilotAppRunnerEcr --assume-role-policy-document "file://${ROOT}/scripts/apprunner-trust.json" >/dev/null 2>&1 || true
aws iam attach-role-policy --role-name OpsPilotAppRunnerEcr --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess >/dev/null 2>&1 || true
aws iam create-role --role-name OpsPilotInstance --assume-role-policy-document "file://${ROOT}/scripts/apprunner-instance-trust.json" >/dev/null 2>&1 || true
aws iam put-role-policy --role-name OpsPilotInstance --policy-name OpsPilotRuntime --policy-document "file://${ROOT}/scripts/bedrock-policy.json"

IMAGE="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${REPO}:latest"
ACCESS_ROLE="arn:aws:iam::${ACCOUNT}:role/OpsPilotAppRunnerEcr"
INSTANCE_ROLE="arn:aws:iam::${ACCOUNT}:role/OpsPilotInstance"
if aws apprunner list-services --region "$REGION" --query "ServiceSummaryList[?ServiceName=='opspilot'].ServiceArn" --output text | grep -q arn; then
  echo "App Runner service opspilot already exists."
else
  aws apprunner create-service --region "$REGION" --service-name opspilot --source-configuration "{
    \"AuthenticationConfiguration\": {\"AccessRoleArn\": \"${ACCESS_ROLE}\"},
    \"AutoDeploymentsEnabled\": false,
    \"ImageRepository\": {
      \"ImageIdentifier\": \"${IMAGE}\",
      \"ImageRepositoryType\": \"ECR\",
      \"ImageConfiguration\": {\"Port\": \"8000\", \"RuntimeEnvironmentVariables\": {\"AWS_REGION\": \"${REGION}\", \"BEDROCK_MODEL_ID\": \"us.anthropic.claude-sonnet-5\", \"OPSPILOT_TRACES\": \"1\"}}
    }
  }" --instance-configuration "{\"Cpu\": \"1024\", \"Memory\": \"2048\", \"InstanceRoleArn\": \"${INSTANCE_ROLE}\"}" >/dev/null
fi
echo "provision requested for account ${ACCOUNT}"
