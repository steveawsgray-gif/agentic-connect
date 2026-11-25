#!/usr/bin/env bash
# Gate 0 spike — one-time CodeBuild setup (CloudShell has no Docker, so
# the spike image is built in the cloud and pushed to ECR).
#
# What this creates, and nothing else:
#   1. IAM service role agentic-connect-spike-codebuild, trusted by
#      codebuild.amazonaws.com, with an inline policy allowing ONLY:
#      CloudWatch Logs (CreateLogGroup/CreateLogStream/PutLogEvents on
#      the build log group) and ECR (GetAuthorizationToken on *, plus
#      push/pull actions on the spike repo only).
#   2. CodeBuild project agentic-connect-spike-build: source = this
#      repo on GitHub, buildspec spike/agent/buildspec.yml, privileged
#      mode (required for docker build), NO_ARTIFACTS, 30-minute
#      timeout, CloudWatch logs enabled.
#
# It does NOT touch the Connect instance, flows, DID, Lex bot,
# qconnect assistant, or the Terraform state. It prints no credential,
# key, or secret.
#
# Idempotent: run it again and it re-applies the role policy and
# updates the project instead of failing.
#
# Run from anywhere (it writes its JSON to /tmp). From the repo:
#   cd ~/agentic-connect && git pull && bash spike/scripts/setup-codebuild.sh
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID="258032684610"
ROLE_NAME="agentic-connect-spike-codebuild"
POLICY_NAME="agentic-connect-spike-codebuild-policy"
PROJECT_NAME="agentic-connect-spike-build"
REPO_NAME="agentic-connect/general-1-spike"
REPOSITORY_URI="258032684610.dkr.ecr.us-east-1.amazonaws.com/agentic-connect/general-1-spike"
LOG_GROUP="/aws/codebuild/agentic-connect-spike-build"

ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/$ROLE_NAME"
ECR_REPO_ARN="arn:aws:ecr:$REGION:$ACCOUNT_ID:repository/$REPO_NAME"

TMPDIR="$(mktemp -d /tmp/spike-codebuild-XXXXXX)"
trap 'rm -rf "$TMPDIR"' EXIT

echo "== Gate 0 spike: CodeBuild setup =="
echo "Region: $REGION | Account: $ACCOUNT_ID"
echo "Role:    $ROLE_NAME"
echo "Project: $PROJECT_NAME"

# --- 1. Service role ------------------------------------------------------
cat > "$TMPDIR/trust-policy.json" <<'TRUST_JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "codebuild.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
TRUST_JSON

cat > "$TMPDIR/inline-policy.json" <<'INLINE_JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": [
        "arn:aws:logs:us-east-1:258032684610:log-group:/aws/codebuild/agentic-connect-spike-build",
        "arn:aws:logs:us-east-1:258032684610:log-group:/aws/codebuild/agentic-connect-spike-build:*"
      ]
    },
    {
      "Sid": "EcrAuth",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EcrSpikeRepo",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:DescribeImages",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "arn:aws:ecr:us-east-1:258032684610:repository/agentic-connect/general-1-spike"
    }
  ]
}
INLINE_JSON

ROLE_JUST_CREATED=0
if aws iam get-role --role-name "$ROLE_NAME" --region "$REGION" >/dev/null 2>&1; then
  echo "Role $ROLE_NAME already exists — keeping it, re-applying the policy."
else
  echo "Creating role $ROLE_NAME..."
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document "file://$TMPDIR/trust-policy.json" \
    --description "Gate 0 spike: CodeBuild service role - build the spike image and push it to ECR" \
    --region "$REGION" >/dev/null
  ROLE_JUST_CREATED=1
fi

echo "Applying inline policy $POLICY_NAME (logs + ECR only)..."
aws iam put-role-policy --role-name "$ROLE_NAME" \
  --policy-name "$POLICY_NAME" \
  --policy-document "file://$TMPDIR/inline-policy.json" \
  --region "$REGION"
echo "Role ARN: $ROLE_ARN"

if [ "$ROLE_JUST_CREATED" = "1" ]; then
  echo "Waiting 10s for the new role to propagate through IAM..."
  sleep 10
fi

# --- 2. CodeBuild project -------------------------------------------------
cat > "$TMPDIR/project.json" <<'PROJECT_JSON'
{
  "name": "agentic-connect-spike-build",
  "description": "Gate 0 spike: build the general-1-spike image and push it to ECR (CloudShell has no Docker)",
  "source": {
    "type": "GITHUB",
    "location": "https://github.com/steveawsgray-gif/agentic-connect.git",
    "buildspec": "spike/agent/buildspec.yml"
  },
  "artifacts": {
    "type": "NO_ARTIFACTS"
  },
  "environment": {
    "type": "LINUX_CONTAINER",
    "image": "aws/codebuild/amazonlinux2-x86_64-standard:5.0",
    "computeType": "BUILD_GENERAL1_SMALL",
    "privilegedMode": true,
    "environmentVariables": [
      {
        "name": "REPOSITORY_URI",
        "value": "258032684610.dkr.ecr.us-east-1.amazonaws.com/agentic-connect/general-1-spike",
        "type": "PLAINTEXT"
      }
    ]
  },
  "serviceRole": "arn:aws:iam::258032684610:role/agentic-connect-spike-codebuild",
  "timeoutInMinutes": 30,
  "logsConfig": {
    "cloudWatchLogs": {
      "status": "ENABLED",
      "groupName": "/aws/codebuild/agentic-connect-spike-build"
    }
  }
}
PROJECT_JSON

EXISTING="$(aws codebuild batch-get-projects --names "$PROJECT_NAME" \
  --region "$REGION" --query 'projects[0].name' --output text)"
if [ -n "$EXISTING" ] && [ "$EXISTING" != "None" ]; then
  echo "Project $PROJECT_NAME already exists — updating it..."
  aws codebuild update-project --cli-input-json "file://$TMPDIR/project.json" \
    --region "$REGION" >/dev/null
  echo "Project updated."
else
  echo "Creating project $PROJECT_NAME..."
  aws codebuild create-project --cli-input-json "file://$TMPDIR/project.json" \
    --region "$REGION" >/dev/null
  echo "Project created."
fi
PROJECT_ARN="$(aws codebuild batch-get-projects --names "$PROJECT_NAME" \
  --region "$REGION" --query 'projects[0].arn' --output text)"
echo "Project ARN: $PROJECT_ARN"

echo
echo "== CodeBuild setup complete =="
echo "Role:    $ROLE_ARN"
echo "Project: $PROJECT_ARN"
echo
echo "NEXT — start the build:"
echo "  aws codebuild start-build --project-name $PROJECT_NAME --region $REGION"
echo "Then check it with:"
echo "  aws codebuild batch-get-builds --ids <build id> --region $REGION"
echo "Logs: CloudWatch log group $LOG_GROUP"
echo "When the build succeeds, re-run terraform apply from spike/terraform"
echo "to create the AgentCore Runtime with the image in place."
