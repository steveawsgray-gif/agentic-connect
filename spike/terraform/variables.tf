variable "aws_region" {
  description = "AWS region for the spike (same region as the Project #2 Connect instance)"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project slug used in resource names and tags"
  type        = string
  default     = "agentic-connect"
}

variable "environment" {
  description = "Environment label"
  type        = string
  default     = "dev"
}

variable "connect_instance_id" {
  description = "Project #2 Connect instance ID (sgray-connect-migration-primer). Used to scope the secret resource policy to this instance only."
  type        = string
  default     = "71134274-3650-457c-b614-5f198db32f65"
}

variable "bedrock_model_id" {
  description = "Bedrock model for the spike (Haiku 4.5 — already verified authorized on this account; the spike's model, not the bake-off winner)"
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "image_tag" {
  description = "ECR image tag for the spike container. Build and push the image first (see README step 1), then apply with the tag you pushed."
  type        = string
  default     = "latest"
}

variable "common_tags" {
  description = "Extra tags merged onto every resource"
  type        = map(string)
  default     = {}
}
