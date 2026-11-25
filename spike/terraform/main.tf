# Project 3 — Gate 0 spike: minimal AgentCore Runtime A2A endpoint
# (General-1, fixed reply only). DRAFT — for Steven's review; nothing
# here has been applied.
#
# REVIEW GUIDE (what each section is):
#   KMS + Secrets Manager   The Connect API key. Customer-managed KMS key
#                           is REQUIRED — Connect cannot read a secret
#                           encrypted with the default aws/secretsmanager
#                           key (Connect setup guide, "Store the external
#                           agent's API key").
#   ECR                     Container image for the spike agent.
#   IAM                     Runtime execution role (Bedrock InvokeModel,
#                           read its own API-key secret, CloudWatch Logs).
#   CloudWatch Logs         Spike log group (14-day retention).
#   AgentCore Runtime       The A2A endpoint itself: container on port
#                           9000, protocol A2A, PUBLIC network.
#
# DELIBERATELY NOT IN TERRAFORM (gaps — see README "Terraform gaps"):
#   * AppIntegrations A2A_SERVER application registration
#     (no first-party Terraform resource; the CloudFormation
#     AWS::AppIntegrations::Application type does not list A2A_SERVER
#     or AuthConfig) — scripts/register-connect.sh step 2.
#   * Connect integration association, type APPLICATION (the official
#     aws_connect_integration_association resource does not support
#     the APPLICATION type; a third-party provider, USAN/awsext, fills
#     the gap — NOT adopted here) — register-connect.sh step 3.
#   * The qconnect orchestrator AI agent + collaborator, the security
#     profile update, and publishing the version (API-only feature,
#     no Terraform coverage) — register-connect.sh steps 4–6.
#   * The Gen-1 test contact flow (Flow Designer / console).
#
# No authorizer_configuration block is set on the runtime — see the
# comment on the resource. That omission is the spike's #1 question.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.18.0, < 7.0.0"
      # >= 6.18.0: first version shipping aws_bedrockagentcore_agent_runtime.
      # Project #2 pins ~> 5.0; the spike needs the 6.x line for AgentCore.
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
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

  # arn:aws:connect:<region>:<account>:instance/<instance-id>
  connect_instance_arn = "arn:aws:connect:${var.aws_region}:${data.aws_caller_identity.current.account_id}:instance/${var.connect_instance_id}"

  # The Runtime's public invocations URL — the AccessUrl Connect calls.
  # (AgentCore A2A guide, Step 4: the card is fetched from this URL.)
  runtime_invocations_url = "https://bedrock-agentcore.${var.aws_region}.amazonaws.com/runtimes/${urlencode(aws_bedrockagentcore_agent_runtime.spike.agent_runtime_arn)}/invocations/"
}

# ---------------------------------------------------------------------------
# KMS key + API-key secret (Connect reads the key from Secrets Manager)
# ---------------------------------------------------------------------------
resource "aws_kms_key" "connect_secret" {
  description             = "Gate 0 spike: encrypts the Connect API key secret (Connect must be able to decrypt it)"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  tags                    = local.common_tags

  # Connect needs kms:Decrypt, only through Secrets Manager — verbatim
  # from the Connect setup guide ("Store the external agent's API key").
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowAccountAdmin"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid       = "AllowConnectToDecryptSecret"
        Effect    = "Allow"
        Principal = { Service = "connect.amazonaws.com" }
        Action    = "kms:Decrypt"
        Resource  = "*"
        Condition = {
          StringEquals = {
            "kms:ViaService" = "secretsmanager.${var.aws_region}.amazonaws.com"
          }
        }
      },
    ]
  })
}

resource "aws_kms_alias" "connect_secret" {
  name          = "alias/agentic-connect-spike"
  target_key_id = aws_kms_key.connect_secret.key_id
}

# The API key itself: generated here, stored in Secrets Manager, never
# written to a file or to chat. The container reads it at startup from
# this secret (AGENT_API_KEY_SECRET_ARN); Connect reads the same secret
# to present the key as a bearer token.
resource "random_password" "api_key" {
  length  = 40
  special = false # URL/header-safe alphabet; still 40 chars of entropy
}

resource "aws_secretsmanager_secret" "agent_api_key" {
  name        = "agentic-connect/general-1-spike/api-key"
  description = "Gate 0 spike: API key Connect Customer presents as a bearer token to the spike agent"
  kms_key_id  = aws_kms_key.connect_secret.arn
  tags        = local.common_tags
}

resource "aws_secretsmanager_secret_version" "agent_api_key" {
  secret_id     = aws_secretsmanager_secret.agent_api_key.id
  secret_string = random_password.api_key.result
}

# Resource policy letting ONLY this Connect instance read the secret —
# verbatim from the Connect setup guide.
resource "aws_secretsmanager_secret_policy" "agent_api_key" {
  secret_arn = aws_secretsmanager_secret.agent_api_key.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowConnectToRetrieveSecret"
        Effect    = "Allow"
        Principal = { Service = "connect.amazonaws.com" }
        Action    = "secretsmanager:GetSecretValue"
        Resource  = "*"
        Condition = {
          StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
          ArnEquals    = { "aws:SourceArn" = local.connect_instance_arn }
        }
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# ECR repository for the spike image
# ---------------------------------------------------------------------------
resource "aws_ecr_repository" "spike" {
  name                 = "agentic-connect/general-1-spike"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # spike: teardown must not be blocked by images
  tags                 = local.common_tags

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "spike" {
  repository = aws_ecr_repository.spike.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the last 5 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = { type = "expire" }
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# IAM execution role for the Runtime
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "runtime_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "runtime_execution" {
  name               = "agentic-connect-spike-runtime-execution"
  description        = "Gate 0 spike: execution role for the AgentCore Runtime (Bedrock invoke, own API-key secret, logs)"
  assume_role_policy = data.aws_iam_policy_document.runtime_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "runtime_execution" {
  statement {
    sid    = "BedrockInvokeSpikeModel"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = [
      # Foundation model + the US inference profile for Haiku 4.5.
      "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
      "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
    ]
  }

  statement {
    sid     = "ReadOwnApiKeySecret"
    effect  = "Allow"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.agent_api_key.arn,
    ]
  }

  statement {
    sid    = "DecryptOwnApiKeySecret"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
    ]
    resources = [
      aws_kms_key.connect_secret.arn,
    ]
  }

  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*",
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*",
    ]
  }

  statement {
    sid    = "EcrPullSpikeImage"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "EcrPullSpikeImageRepo"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [
      aws_ecr_repository.spike.arn,
    ]
  }
}

resource "aws_iam_role_policy" "runtime_execution" {
  name   = "agentic-connect-spike-runtime-execution"
  role   = aws_iam_role.runtime_execution.id
  policy = data.aws_iam_policy_document.runtime_execution.json
}

# ---------------------------------------------------------------------------
# CloudWatch Logs (spike log group; the Runtime also writes its own
# /aws/bedrock-agentcore/runtimes/* group — both are worth watching)
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "spike" {
  name              = "/aws/bedrock-agentcore/runtimes/general-1-spike"
  retention_in_days = 14
  tags              = local.common_tags
}

# ---------------------------------------------------------------------------
# AgentCore Runtime — the spike endpoint
# ---------------------------------------------------------------------------
resource "aws_bedrockagentcore_agent_runtime" "spike" {
  agent_runtime_name = "general_1_spike"
  description        = "Gate 0 spike: General-1 fixed-reply agent proving the Connect Customer / AgentCore Runtime A2A seam. No tools, no memory."
  role_arn           = aws_iam_role.runtime_execution.arn
  tags               = local.common_tags

  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.spike.repository_url}:${var.image_tag}"
    }
  }

  protocol_configuration {
    # A2A (not MCP, not HTTP): the container serves JSON-RPC on port
    # 9000 at the root path. Verified against the provider source
    # (hashicorp/aws main, agent_runtime.go): server_protocol is the
    # ServerProtocol enum and "A2A" is a valid value.
    server_protocol = "A2A"
  }

  network_configuration {
    # REQUIRED by the provider schema. PUBLIC: the Runtime endpoint is
    # reached over the public invocations URL, which is what Connect
    # calls. No VPC, no subnets, no security groups for the spike.
    network_mode = "PUBLIC"
  }

  request_header_configuration {
    # Headers the Runtime proxy forwards into the container. Without
    # this, the container never sees the bearer token or the trace
    # context Connect sends. "Authorization" is the documented example
    # in the AgentCore A2A guide; traceparent / tracestate / A2A-
    # Extensions are the Connect contract headers. Whether the proxy
    # forwards the non-Authorization headers is UNVERIFIED (see README
    # risk #2) — the spike logs what actually arrives at INIT_SESSION.
    request_header_allowlist = [
      "Authorization",
      "traceparent",
      "tracestate",
      "A2A-Extensions",
    ]
  }

  environment_variables = {
    AGENT_API_KEY_SECRET_ARN = aws_secretsmanager_secret.agent_api_key.arn
    BEDROCK_MODEL_ID         = var.bedrock_model_id
    AWS_REGION               = var.aws_region
    # NOTE: AGENTCORE_RUNTIME_URL is NOT set here — the Runtime service
    # injects it into the container at deploy time (the container uses
    # it for the Agent Card URL). Setting it here would be circular:
    # the URL contains this runtime's ARN.
  }

  # NO authorizer_configuration block — DELIBERATE, and the spike's #1
  # question. The Terraform provider only exposes custom_jwt_authorizer
  # (verified in the provider source: authorizerConfigurationBlock has
  # exactly one child, custom_jwt_authorizer — there is no NONE and no
  # AWS_IAM in Terraform). Omitting the block means "no authorizer
  # configured". Whether that leaves the invocations endpoint callable
  # with ONLY the API-key bearer token (no SigV4) is UNVERIFIED: the
  # CDK docs say IAM is the default when no authorizer is set, while
  # a runtime with a null authorizerConfiguration is also described
  # as "does not have authorization configured". The Connect model
  # REQUIRES the bearer path to work — Connect cannot SigV4-sign and
  # cannot mint a JWT — so the spike's first live test is: curl the
  # invocations URL with only the bearer key (register-connect.sh
  # step 1). If it returns 403 AccessDenied, the Runtime cannot host
  # a Connect external agent this way and Gate 0 FAILS on auth — the
  # fallback (host the A2A server outside Runtime, e.g. ECS/App
  # Runner behind a public HTTPS endpoint) goes back to Steven; it is
  # NOT silently substituted. Verify after apply with:
  #   aws bedrock-agentcore-control get-agent-runtime \
  #     --agent-runtime-id <id> --query 'authorizerConfiguration'

  depends_on = [
    aws_cloudwatch_log_group.spike,
  ]
}
