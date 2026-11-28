# Re-host — Gate 0 spike on ECS Express Mode

Same A2A server as the Nov 24 AgentCore spike, hosted outside Runtime
behind a public HTTPS endpoint Connect can call. Express Mode was chosen
Nov 28: it hands you a public HTTPS address
(`https://<service>.ecs.us-east-1.on.aws`) on an AWS-managed certificate —
no domain, no ACM certificate needed.

## What it creates (6 resources)

- 3 IAM roles: execution (pull image, write logs), infrastructure (lets
  ECS build the load balancer, scaling), task (Bedrock InvokeModel on
  Haiku 4.5 + read the API-key secret).
- CloudWatch log group `/aws/ecs/agentic-connect-rehost` (14 days).
- The Express gateway service: Fargate task (0.25 vCPU / 0.5 GB) +
  Application Load Balancer with HTTPS, health check on `/ping`.

## What it reuses (owned by `spike/terraform`, untouched)

- ECR repo `agentic-connect/general-1-spike` and the `:latest` image
  (build it first with CodeBuild: `aws codebuild start-build
  --project-name agentic-connect-spike-build --region us-east-1`).
- Secrets Manager secret `agentic-connect/general-1-spike/api-key`.
- The AgentCore Runtime stays parked; nothing here touches it.

## Run

```
cd ~/agentic-connect && git pull
cd spike/rehost-express
terraform init
terraform plan    # review, then approve before apply
terraform apply
```

`terraform output public_url` gives the HTTPS endpoint to register
with AppIntegrations (see `scripts/register-connect.sh` steps 2–6,
with the new URL in place of the Runtime invocations URL).

## Cost

About $1–2 for the session; roughly $25–45/month if left standing
(smallest task size + load balancer). Teardown is your call:

```
terraform destroy
```

Destroy removes the service, the roles and the log group. The ECR
repo, the secret and the Runtime stay.
