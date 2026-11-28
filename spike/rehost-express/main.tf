# Project #3 — Gate 0 spike re-host: same A2A server, outside AgentCore
# Runtime, on ECS Express Mode (Nov 28, 2026).
#
# Why Express Mode: the Runtime's no-authorizer endpoint requires SigV4
# and Connect sends only an API key as a bearer (Gate 0 failed on auth,
# Nov 24, HTTP 403). Express Mode gives the same container a public
# HTTPS address (https://<service>.ecs.us-east-1.on.aws) on an
# AWS-managed certificate — no domain, no ACM certificate needed — and
# the container checks the bearer itself against the API key in
# Secrets Manager (main.py: AGENT_API_KEY_SECRET_ARN).
#
# What this creates (6 resources):
#   * 3 IAM roles: task execution (pull image, write logs), infrastructure
#     (lets ECS build the load balancer etc.), task (the container's own
#     permissions: Bedrock InvokeModel + read its API-key secret).
#   * CloudWatch log group (14-day retention).
#   * The Express gateway service itself (Fargate task + ALB + HTTPS).
#
# What it REUSES (not created here — still owned by spike/terraform):
#   * ECR repo agentic-connect/general-1-spike + the :latest image.
#   * Secrets Manager secret agentic-connect/general-1-spike/api-key
#     (KMS key alias/agentic-connect-spike).
#   * The AgentCore Runtime stays parked; nothing here touches it.
#
# Teardown: terraform destroy from this directory removes the service,
# the roles and the log group. The ECR repo, secret and Runtime stay.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.50.0, < 7.0.0"
      # >= 6.50.0: fixes the "Provider produced inconsistent result
      # after apply" error on aws_ecs_express_gateway_service
      # (provider 6.50.0 release notes, June 10, 2026).
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  common_tags = merge(
    {
      Project     = "agentic-connect"
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.common_tags,
  )

  # The spike image, built by CodeBuild and pushed to ECR.
  image_uri = "${data.aws_ecr_repository.spike.repository_url}:${var.image_tag}"
}

data "aws_ecr_repository" "spike" {
  name = "agentic-connect/general-1-spike"
}

data "aws_secretsmanager_secret" "api_key" {
  name = "agentic-connect/general-1-spike/api-key"
}

data "aws_kms_alias" "connect_secret" {
  name = "alias/agentic-connect-spike"
}

# --- Execution role: ECS pulls the image and writes container logs. ---
resource "aws_iam_role" "execution" {
  name        = "agentic-connect-rehost-execution"
  description = "Re-host: ECS task execution role - pull the spike image, write logs"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# --- Infrastructure role: lets ECS build the ALB, target group, scaling. ---
resource "aws_iam_role" "infrastructure" {
  name        = "agentic-connect-rehost-infrastructure"
  description = "Re-host: ECS infrastructure role - lets ECS manage the load balancer and scaling"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "infrastructure" {
  role       = aws_iam_role.infrastructure.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices"
}

# --- Task role: the container's own permissions. Mirrors the spike
# Runtime execution role (verified Nov 28): Bedrock InvokeModel on the
# Haiku 4.5 model + read its own API-key secret (+ KMS decrypt). ---
resource "aws_iam_role" "task" {
  name        = "agentic-connect-rehost-task"
  description = "Re-host: ECS task role - Bedrock InvokeModel + read the API-key secret"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = local.common_tags
}

resource "aws_iam_role_policy" "task" {
  name = "agentic-connect-rehost-task"
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockInvokeSpikeModel"
        Effect = "Allow"
        Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = [
          "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
          "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
        ]
      },
      {
        Sid      = "ReadOwnApiKeySecret"
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = data.aws_secretsmanager_secret.api_key.arn
      },
      {
        Sid      = "DecryptOwnApiKeySecret"
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = data.aws_kms_alias.connect_secret.target_key_arn
      },
    ]
  })
}

# --- Logs ---
resource "aws_cloudwatch_log_group" "rehost" {
  name              = "/aws/ecs/agentic-connect-rehost"
  retention_in_days = 14
  tags              = local.common_tags
}

# --- The Express gateway service ---
resource "aws_ecs_express_gateway_service" "spike" {
  service_name = var.service_name
  # cluster defaults to "default"; network defaults to the default VPC.

  execution_role_arn      = aws_iam_role.execution.arn
  infrastructure_role_arn = aws_iam_role.infrastructure.arn
  task_role_arn           = aws_iam_role.task.arn

  cpu    = var.cpu
  memory = var.memory

  # /ping is served by main.py without auth (the Dockerfile healthcheck
  # uses it too) — the load balancer's health check.
  health_check_path = "/ping"

  wait_for_steady_state = true

  primary_container {
    image          = local.image_uri
    container_port = 9000

    environment {
      name  = "AGENT_API_KEY_SECRET_ARN"
      value = data.aws_secretsmanager_secret.api_key.arn
    }

    aws_logs_configuration {
      log_group = aws_cloudwatch_log_group.rehost.name
    }
  }

  tags = local.common_tags
}
