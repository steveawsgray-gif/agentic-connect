output "agent_runtime_arn" {
  description = "AgentCore Runtime ARN for the spike agent"
  value       = aws_bedrockagentcore_agent_runtime.spike.agent_runtime_arn
}

output "agent_runtime_id" {
  description = "AgentCore Runtime ID for the spike agent"
  value       = aws_bedrockagentcore_agent_runtime.spike.agent_runtime_id
}

output "agent_runtime_url" {
  description = "Public invocations URL — the AccessUrl to register with AppIntegrations (Connect calls this)"
  value       = local.runtime_invocations_url
}

output "api_key_secret_arn" {
  description = "Secrets Manager ARN holding the Connect API key (Connect reads this; the container reads it too)"
  value       = aws_secretsmanager_secret.agent_api_key.arn
}

output "ecr_repository_url" {
  description = "ECR repository URL for the spike image"
  value       = aws_ecr_repository.spike.repository_url
}

output "connect_instance_arn" {
  description = "Connect instance ARN the secret resource policy is scoped to"
  value       = local.connect_instance_arn
}

output "next_steps" {
  description = "What to do after apply"
  value       = "1) Run scripts/register-connect.sh (auth test first: curl the invocations URL with only the bearer key — if it 403s, Gate 0 fails on auth, see README risk #1). 2) Register the A2A_SERVER application, associate it, add the collaborator, update the security profile, publish. 3) Test call through the Gen-1 test flow and work the Gate 0 verification table in the README."
}
