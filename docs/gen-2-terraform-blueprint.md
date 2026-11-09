# Project 3 — Generation 2: Terraform blueprint

**Status:** Design asset — November 9, 2026. This document maps the complete Terraform for the Generation 2 matrix. The code it describes is written as the build proceeds through the Generation 1 gates; **nothing in this blueprint is applied**, and applying any part of it is a gated decision on the road in the [Generation 2 design brief](gen-2-design-brief.md).
**State discipline:** Generation 2 has its own Terraform state, separate from Project 2. It references the Project 2 floor — instance, queues, the original flow — by data source only. Generation 2 code can never modify or destroy Project 2 resources.

## 1. Repository layout

```text
terraform/
  gen2/
    main.tf               # provider, backend, the pod composition
    variables.tf          # matrix-wide inputs (instance id, region, tags)
    pods.tf               # one module block per pod — the matrix itself
    routing.tf            # skill router Lambda + Gen-2 flow wiring
    observability.tf      # log groups, dashboards, alarms, eval schedules
    outputs.tf            # pod endpoints, agent card URLs, console links
    pods/
      general-status.tfvars
      general-knowledge.tfvars
      billing-info.tfvars
      billing-casework.tfvars
      priority-triage.tfvars
      standby-surge.tfvars
    modules/
      pod/                # THE cradle pattern — instantiated once per pod
        main.tf
        variables.tf      # the pod contract (below)
        runtime.tf        # AgentCore Runtime + versioned endpoint
        memory.tf         # session memory; long-term strategies off by default
        gateway.tf        # Gateway + this pod's tool targets
        policy.tf         # policy engine attachment + Cedar policies
        identity.tf       # workload identity + execution role (least privilege)
        guardrails.tf     # Bedrock Guardrails profile for this pod
        evaluation.tf     # eval dataset + online evaluation configuration
        outputs.tf        # endpoint ARN, agent card URL, log group
      routing/
        skill_router.py   # the routing decision (pod / human / hybrid)
        main.tf           # Lambda, IAM, Connect flow association
    flows/
      gen2-inbound-flow.json   # Gen-2 inbound flow (separate from P2's flow)
```

## 2. The pod contract

Every pod is the same module with a different load. A pod is fully described by its variable file:

| Variable | Meaning |
| --- | --- |
| `pod_name` | e.g. `billing-casework` |
| `queue` | The Connect queue this pod serves |
| `job_families` | The certified work, mirrored on the pod's Agent Card skills |
| `model_id` | The model chosen for this job by bake-off — a variable, never hard-coded |
| `autonomy_tier` | `A` read-only, `B` bounded writes, `C` prepare-only |
| `tool_targets` | The Gateway tools this pod — and only this pod — may call |
| `policy_tier` | The Cedar policy set evaluated at this pod's Gateway |
| `memory_long_term` | Default `false`; caller memory is a separate approved decision |
| `eval_suite` | The scenario set this pod must pass to be promoted |
| `enabled` | The gate switch — see section 4 |

Adding a pod to the matrix is adding one module block and one tfvars file. Removing one is deleting the block. The pattern never changes; only the load does.

## 3. Resource inventory

Per pod (from `modules/pod`):

- `aws_bedrockagentcore_agent_runtime` — the pod's agent, container or direct-code deployment, A2A protocol configuration, session isolation on.
- `aws_bedrockagentcore_agent_runtime_endpoint` — the versioned endpoint traffic is pinned to; promotion moves the pin, never the code under it.
- `aws_bedrockagentcore_memory` — short-term session memory. Long-term strategies are declared only when `memory_long_term` is true, which no pod sets by default.
- `aws_bedrockagentcore_gateway` + `aws_bedrockagentcore_gateway_target` — one gateway per pod; targets are this pod's tools only (Lambda or API), exposed over MCP.
- Policy engine and Cedar policies for the pod's tier, attached at its gateway — every tool call evaluated outside the model before execution.
- `aws_bedrock_guardrail` — the pod's content guardrail profile, versioned and pinned like everything else.
- `aws_iam_role` + scoped policies — the pod's own workload identity; no shared roles, no cross-pod permissions.
- `aws_cloudwatch_log_group` + metric filters — the pod's trace home, feeding evaluation and the insight loop.

Matrix-wide (root module):

- The skill router Lambda and its IAM role (read-only lookups: pod health, evaluation standing, registry state).
- The Generation 2 inbound contact flow (`aws_connect_contact_flow`) — a new flow; Project 2's published flow is untouched.
- CloudWatch dashboard for the matrix board, alarms per pod (error rate, escalation anomalies, evaluation drift), and the evaluation schedule.
- Registry publication steps for approved pod versions.

**Provider-gap honesty:** where the Terraform AWS provider has no resource yet for an AgentCore capability (some Registry and Optimization operations are API-first), the blueprint marks the step `API — apply-time script` in the module README rather than inventing a resource. A blueprint that fakes coverage would fail the first real plan; this one shows its seams.

## 4. The gates are in the code

Each pod's module block carries `count = var.pods_enabled["billing-casework"] ? 1 : 0` semantics via its `enabled` variable. The road from the design brief is therefore literal in the code:

| Road gate | Code state |
| --- | --- |
| Gen 1 proof | Only the pod module exists — proven by Generation 1's single instantiation |
| Shadow matrix | Billing/Priority pods applied to a shadow root with no flow association |
| First staffing | `general-*` and `billing-info` enabled; Gen-2 flow associated to a test number |
| First bounded write | `billing-casework` enabled with exactly one Tier B tool target |
| Priority triage | `priority-triage` enabled, Tier C, prepare-only policies |
| Surge & back-office | `standby-surge` enabled; task-channel wiring added |

A gate decision is a variable change, a plan review, and an apply — the same discipline as any infrastructure change, because that is what it is.

## 5. What a reviewer can verify without applying anything

- `terraform fmt -check` and `terraform validate` pass on the scaffold (no credentials, no state, no cost).
- Every pod's tool list, policy tier and autonomy boundary is readable from its tfvars alone.
- No resource in the Gen-2 tree references a Project 2 resource for write — data sources only.
- The destroy story is symmetric: removing a pod's block removes exactly that pod; the floor remains.

That is the point of the blueprint as a demonstration asset: the entire second generation can be audited at a desk, in code, before a single resource exists.
