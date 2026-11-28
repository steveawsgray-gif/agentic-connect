output "service_arn" {
  description = "Express gateway service ARN"
  value       = aws_ecs_express_gateway_service.spike.service_arn
}

output "public_url" {
  description = "Public HTTPS endpoint — the URL Connect will call (register with AppIntegrations)"
  value       = "https://${tolist(aws_ecs_express_gateway_service.spike.ingress_paths)[0].endpoint}"
}

output "service_name" {
  description = "Express gateway service name"
  value       = aws_ecs_express_gateway_service.spike.service_name
}

output "next_steps" {
  description = "What to do after apply"
  value       = "1) Auth test: curl the public URL's /ping with no auth (expect 401) and the agent card with Authorization: Bearer <apiKey> (expect the card) — see scripts/register-connect.sh. 2) Run scripts/register-connect.sh steps 2-6 with the new URL. 3) Test call through the Gen-1 test flow; re-run the 8 Gate 0 points."
}
