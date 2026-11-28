variable "aws_region" {
  description = "AWS region (same as the Project #2 Connect instance)"
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

variable "service_name" {
  description = "Express gateway service name (also the first part of the public URL)"
  type        = string
  default     = "agentic-connect-spike"
}

variable "image_tag" {
  description = "ECR image tag for the spike container (built by CodeBuild first)"
  type        = string
  default     = "latest"
}

variable "cpu" {
  description = "CPU units for the task (256 = 0.25 vCPU, smallest valid)"
  type        = string
  default     = "256"
}

variable "memory" {
  description = "Memory in MiB for the task (512 = smallest valid)"
  type        = string
  default     = "512"
}

variable "common_tags" {
  description = "Extra tags merged onto every resource"
  type        = map(string)
  default     = {}
}
