# Gate 0 spike — DRAFT for Steven's review

**Status: draft only. Nothing here has been deployed to AWS. No AWS credentials, keys, or passwords are in any file.**

This is the smallest possible agent that can prove the Project #3 seam:
Amazon Connect Customer → A2A → a custom Bedrock agent on AgentCore
Runtime. It answers every turn with **one fixed reply**, sends the
mandatory trace span, and on the second turn ends the collaboration
with **FINISH / ESCALATE** so the contact returns to a human in General
Support. No tools, no case lookup, no memory. If this seam cannot be
proved, the build **stops at Gate 0** — no silent Connect-native
substitution (Gen-1 brief §4, redline 2).

## Files in this draft

| File | What it is |
|---|---|
| `agent/main.py` | The spike server: Strands agent (Haiku 4.5, temp 0, no tools) + custom A2A executor + bearer check + ROLE_* normalisation + `/ping`. |
| `agent/requirements.txt` | Pinned deps (a2a-sdk 0.3.26, strands-agents 1.57.2, boto3 1.43, uvicorn 0.34 — the versions in the AWS AgentCore A2A guide). |
| `agent/Dockerfile` (+ `.dockerignore`) | AgentCore Runtime container, port 9000, non-root. |
| `agent/buildspec.yml` | CodeBuild buildspec: builds `spike/agent` and pushes `:latest` to ECR (CloudShell has no Docker). |
| `terraform/main.tf` | KMS key + API-key secret, ECR repo, IAM execution role, CloudWatch log group, `aws_bedrockagentcore_agent_runtime`. Project #2 style (root module, `common_tags`, `terraform.tfvars.example`). |
| `terraform/variables.tf`, `outputs.tf`, `terraform.tfvars.example` | Inputs/outputs. The `agent_runtime_url` output is the AccessUrl Connect calls. |
| `scripts/register-connect.sh` | Steps 2–6 of the Connect setup, as auditable CLI commands (see below). Step 1 is the decisive auth test. |
| `scripts/setup-codebuild.sh` | One-time setup: creates the CodeBuild service role + `agentic-connect-spike-build` project. |
| `scripts/test-spike-local.sh` + `scripts/smoke_test.py` | Local smoke test — replays the Connect HTTPS flow with no AWS and no model. **23/23 checks pass** (see "Local verification"). |

**Where this lives in the repo:** the spike is a self-contained probe
under `spike/` in this repo (`spike/agent/`, `spike/terraform/`,
`spike/scripts/`), kept together because the scripts use relative
paths (`register-connect.sh` defaults `TF_DIR` to `../terraform`; the
test scripts assume the `agent/` layout). The Gen-1 brief §11 layout
(`agent/src/` + `infra/`) governs the real WP1 agent build — when
Gate 0 passes, this spike is either deleted or kept under `spike/` as
the regression probe. Your call at the review.

## What the spike proves — the 8 Gate 0 points

From the Gen-1 brief §4. Each point, what proves it, and where the
evidence lives:

| # | Gate 0 point | Proved by | Evidence |
|---|---|---|---|
| 1 | A2A collaboration available for the instance + region in the required form | Tier check (done 24 Nov: `MAX_PACKAGE=true`, Customer tier) + the test call reaching the agent | CloudShell tier check (recorded) + the call itself |
| 2 | A minimal AgentCore Runtime A2A endpoint can join a test interaction | The test call: INIT_SESSION → CHANNEL_STATE READY → 2 turns → FINISH | `init_session` / `channel_ready` / `turn_complete` log lines in CloudWatch |
| 3 | Connect passes the required context into the session | `initSession` carries contactArn, instanceArn, supportedFinishTypes, contactContext (channel) | `init_session` log line shows contact_arn, channel, finish types — check `channel` is `voice` (needs the Access Contact Control Panel permission) |
| 4 | The agent can return a controlled outcome | Both turns return exactly the fixed reply, nothing else | Hear it on the call; `turn_complete` log lines |
| 5 | Escalation returns the live contact to General Support | Turn 2 sends FINISH ESCALATE; the orchestrator's Escalate tool returns the contact to the flow's Escalate path → transfer to the General Support queue | You are transferred to a human in General Support on the test call; the CTR shows the transfer |
| 6 | The Connect contact record and the AgentCore trace can be correlated | The TRACING_SPAN adopts Connect's `traceparent` traceId; the contact ARN is logged with the same session | `turn_complete` log line: `trace_id` equals Connect's trace id; contact_arn in the `init_session` line |
| 7 | Voice latency is acceptable | Turn latency (model call + round trip) logged per turn | `turn_complete` `latency_ms` + how the call feels; no invented ceiling — the number from Gate 0 sets the WP3 ceiling |
| 8 | Disabling the endpoint restores the human-only path cleanly | Delete (or disable) the AppIntegrations application / remove the collaborator, then call again: the caller reaches General Support with no agent step | Test call after teardown goes straight to a human; original published flow untouched throughout |

## Order of operations

### Scripted (Terraform + scripts)

1. **Build + push the image.** CloudShell has no Docker, so the image
   is built in the cloud by CodeBuild (the local `docker build` route
   below still works if you have Docker on your own machine):
   - Once: `bash scripts/setup-codebuild.sh` — creates the CodeBuild
     service role and the `agentic-connect-spike-build` project
     (buildspec `agent/buildspec.yml`, privileged mode for Docker).
     The build must produce an **arm64** image — AgentCore Runtime
     accepts only arm64 ("Supported platforms: [arm64]"; the x86_64
     image built 24 Nov was rejected). The project uses the aarch64
     standard image with environment type `ARM_CONTAINER` (the image
     is rejected under `LINUX_CONTAINER`); with Docker locally, build
     with `--platform linux/arm64`.
   - Then: `aws codebuild start-build --project-name
     agentic-connect-spike-build --region us-east-1` — builds
     `spike/agent` and pushes `:latest` to the ECR repo Terraform
     created. Check it with `aws codebuild batch-get-builds --ids
     <build id> --region us-east-1`, or the build log in CloudWatch
     (`/aws/codebuild/agentic-connect-spike-build`).
   - With Docker locally instead: from `agent/`,
     `docker build -t general-1-spike:latest .`, then log in to ECR
     and push to the repository Terraform creates (the URL is the
     `ecr_repository_url` output).
   Do the build **before** `terraform apply`, or apply twice (once for
   the repo, push, then again with the image in place). The first
   apply on 24 Nov created 11 of 12 resources; only the Runtime
   failed — the image was not in ECR yet — so the second apply is the
   one that creates it.
2. **Terraform apply** (from `terraform/`; Terraform 1.14.0 was
   installed in CloudShell 24 Nov; `init`, `validate` and `plan` all
   run clean, and the first apply created 11 of 12 resources — only
   the Runtime failed, for the missing image; see step 1):
   `cp terraform.tfvars.example terraform.tfvars` (check the values),
   `terraform apply`. This creates the KMS key, the API-key secret
   (key generated by Terraform, never written to a file), the ECR
   repo, the execution role, and the Runtime.
3. **Run `scripts/register-connect.sh`.** It stops at the first problem
   and never prints the API key. Its step 1 is the decisive test —
   see risk #1 below.

### Steven in the console / CLI (not scripted — no Terraform covers these)

4. **Assistant FIRST.** The qconnect assistant must exist before the
   Lex bot can be built: the `QInConnectIntent` intent's configuration
   takes the assistant's ARN, and the build fails without it (found
   live 24 Nov — "missing a required qInConnectAssistantConfiguration
   field"). Create it first — `aws qconnect create-assistant --name
   general-1-spike-assistant --type AGENT --region us-east-1`, or in
   the console under AI Agents — and note its ARN. **Created 24 Nov:**
   assistant ID `664dda35-3188-40ea-a006-b67bf673c7de`, ARN
   `arn:aws:wisdom:us-east-1:258032684610:assistant/664dda35-3188-40ea-a006-b67bf673c7de`
   (status ACTIVE). The script also needs its ID later
   (`ASSISTANT_ID=`).
5. **Lex bot (self-service prerequisite).** Our test is self-service —
   the caller talks to the spike before any human — so a Lex V2 bot
   with the `AMAZON.QInConnectIntent` intent must be associated with
   the instance (setup guide: the bot is required for self-service;
   pure agent assistance does not need one). In the intent, set the
   Amazon Q in Connect Configuration to the assistant ARN from step 4
   and save; and give a custom intent one sample utterance (e.g.
   `hello` on the placeholder NewIntent) — the build fails with no
   utterances in the locale. Then Build, create a version + a separate
   alias for it — the built-in TestBotAlias is locked to Draft and its
   association cannot be changed, so create e.g. `SpikeV1` pointing at
   version 1 — and associate the bot with the instance. **Association
   is the V2 path, by alias ARN** (`associate-lex-bot` is the old V1
   operation — it fails with "Lex V1 bots are no longer supported"):
   `aws connect associate-bot --instance-id <id> --lex-v2-bot
   AliasArn=arn:aws:lex:us-east-1:258032684610:bot-alias/FDQF4VBHBJ/<ALIAS_ID>
   --region us-east-1`. **Bot
   created 24 Nov: `general-1-spike-bot`, ID `FDQF4VBHBJ`, en_US;
   version 1 created; built-in TestBotAlias (ID TSTALIASID) points at
   Draft; **`SpikeV1` alias created 24 Nov, ID `ZSMASIXRCM`, version 1,
   Available** — associate this one. **Associated 24 Nov — `list-bots`
   confirms the SpikeV1 alias ARN on the instance; Lex prerequisite
   met.** The script checks for the association and stops if it is
   missing.
6. **Access Contact Control Panel.** Add this permission to the same
   security profile in the console if the spike should receive contact
   context (channel, addresses). Without it the spike still works, but
   Gate 0 point 3 cannot be proved in full.
7. **Gen-1 test flow.** In Flow Designer, build the separate Gen-1
   test flow (per the brief: a separately versioned flow for testing;
   the original published flow stays untouched as rollback). Add the
   **Connect assistant** block before Transfer to queue, set the Agent
   Assistance AI agent to the published orchestrator version ARN the
   script prints, and set the flow's Escalate path to transfer to the
   General Support queue. **The DID question — DECIDED Nov 24, 2026
   (Steven): test through the separate Gen-1 test entry point.** The
   published number (+1 531-247-6511) stays on the original flow until
   the design passes its supervised proof gates; the published DID
   moves only at WP4.
8. **Test call** (script below), then work the verification table
   above. When Gate 0 is decided, **teardown** is `terraform destroy`
   + delete the AppIntegrations application
   (`aws appintegrations delete-application`) — point 8 is proved by
   the call after teardown.

## The test call script (what to say, what should happen)

Call the Gen-1 test entry point. The orchestrator is configured with
`immediateHandoff: true`, so the spike answers from the first turn.

1. **You speak** (anything — e.g. "Hello, I need help with my case").
   **You hear** the fixed reply, word for word (see `FIXED_REPLY` in
   `main.py`). The agent does not ask a follow-up and does not look
   anything up.
2. **You speak again** (anything — e.g. "Yes, I want to speak to a
   person"). **You hear** the fixed reply again — then the call hands
   you to a human agent in General Support. That handoff is the
   FINISH ESCALATE: the spike ends the collaboration, the orchestrator
   runs its Escalate tool, and the flow transfers you.
3. If the call does anything else — a different reply, a long silence,
   an error message, no transfer — that is a Gate 0 finding, not a
   glitch to work around. Note exactly what happened and which step it
   was.

## Design decisions (why it is built this way)

- **Why not `serve_a2a` / `StrandsA2AExecutor`.** The AgentCore SDK's
  `serve_a2a()` and Strands' executor treat every incoming message as
  a plain user turn. Connect's INIT_SESSION, CHANNEL_STATE,
  INTERRUPTION and ERROR are extension messages in A2A metadata — a
  generic executor would feed them to the model as user text. The
  spike therefore uses the raw a2a-sdk (`A2AStarletteApplication` +
  `DefaultRequestHandler`) with a custom `AgentExecutor` that
  dispatches on the extension `eventType`. The model itself is still a
  plain Strands agent; only the A2A plumbing is hand-rolled.
- **The model is invoked, its output discarded.** The spike sends the
  fixed reply regardless. The Bedrock call is a liveness probe: it
  proves the model path from inside the Runtime container (execution
  role, InvokeModel, tokens, latency). If the model deviates from the
  fixed reply, that is logged (`model_deviated_from_fixed_reply`), not
  surfaced to the caller. `SPIKE_NO_MODEL=1` skips the call (local
  smoke test).
- **FINISH is on turn 2, not turn 1.** The contract is explicit:
  "Send FINISH only when your agent is done with the conversation,
  not at the end of every turn." Turn 1 completes without FINISH;
  turn 2 ends the collaboration with FINISH ESCALATE (only if
  ESCALATE is in `supportedFinishTypes` — otherwise COMPLETE, and the
  log says so loudly; if neither is listed, no FINISH is sent).
- **Bearer check inside the container.** The Connect guide prescribes
  exactly this: "Check the bearer token on each incoming connection
  or request, and reject the connection or request if the token
  doesn't match the API key that you issued." Wrong/missing key →
  HTTP 401 (Connect does not retry 401). The key lives in Secrets
  Manager; the container fetches it at startup. Nothing secret is in
  any file.
- **ROLE_* normalisation.** The AWS sample payloads print
  `"role": "ROLE_USER"` / `"ROLE_AGENT"`, but a2a-sdk 0.3.26 only
  accepts `"user"` / `"agent"` and rejects ROLE_* with a pydantic
  error (verified locally). A middleware rewrites ROLE_* → user/agent
  before the SDK parses the body; if Connect already sends
  user/agent, it is a no-op. See UNVERIFIED #3.
- **Tracing is hand-built OTLP, not the OTEL SDK.** One root span
  (`invoke_agent general-1-spike`, SERVER) + one child span
  (`chat <model>`, CLIENT) per turn, with `aws.connect.span.message`
  input/output events, sent as a TRACING_SPAN artifact after the
  response and before the terminal status update. This is mandatory:
  Connect disables endpoints that do not send the required trace data.
- **HTTPS only, no WebSocket server.** The spike serves JSON-RPC over
  HTTPS (text). Audio streaming needs `wss://` and is out of scope
  (`audioStreamingEnabled: false`); the spike fails audio turns cleanly
  with a structured BAD_REQUEST error instead of pretending.
- **Re-INIT is idempotent.** Chat re-sends INIT_SESSION on every
  message and a voice reconnect re-sends it with the same contextId.
  A repeat INIT_SESSION refreshes contact info but keeps the turn
  counter — verified in the smoke test.
- **The Agent Card URL comes from the Runtime, not Terraform.** The
  service injects `AGENTCORE_RUNTIME_URL` into the container at
  deploy time; the card uses it. Terraform does not set it (the URL
  contains the runtime's own ARN — setting it in Terraform would be
  circular).

## Risk #1 — the Runtime authorizer (the question Gate 0 exists to answer)

Connect sends **only an API key as a bearer token**. It cannot
SigV4-sign and cannot mint a JWT. AgentCore Runtime's authorizers are
IAM (SigV4) and custom JWT (OIDC) — and the Terraform provider only
exposes `custom_jwt_authorizer` (verified in the provider source:
`authorizerConfigurationBlock` has exactly one child). The draft
therefore sets **no** `authorizer_configuration` block. What that
means on the wire is genuinely unresolved in the AWS docs: the CDK
docs say IAM is the default when no authorizer is set, while a
runtime whose `authorizerConfiguration` is null is also described as
having "no authorization configured". The Connect model only works if
the bearer path reaches the container.

**Finding 24 Nov (creation):** `Authorization` cannot be allowlisted
without a custom JWT authorizer — the service rejects the Runtime
creation ("Authorization header can be specified in
requestHeaderAllowlist only when runtime is set up with
customJWTAuthorizer for OAuth based authorization"). The AWS docs
confirm it (custom headers doc: the `Authorization` header requires
a `customJWTAuthorizer`; API keys are meant to be passed as
`X-Api-Key`). Connect's key is not a JWT, so no JWT authorizer can
accept it, and the container-side bearer check cannot receive the
key through the Runtime proxy. `Authorization` was removed from the
allowlist so the Runtime can be created. The curl test still decides
open vs IAM-locked — with the header stripped, its outcomes are now:
**401** (endpoint open, bearer stripped — the API-key check cannot
work through the Runtime; auth model needs redesign), **403**
(IAM-locked — Gate 0 fails on auth, fallback is hosting outside
Runtime, ECS / App Runner, where Connect's bearer reaches the
container directly). Either way the auth model is a redesign item,
not a config tweak.

**Decisive test** (script step 1, two minutes after apply):
`curl` the invocations URL (`.../runtimes/<ARN>/invocations/.well-known/agent-card.json`)
with only `Authorization: Bearer <key>` and no SigV4.
- **200 + the agent card →** the bearer path works; proceed.
- **403 AccessDenied → Gate 0 FAILS on auth.** The Runtime cannot
  host a Connect external agent this way. The fallback is to host the
  A2A server outside Runtime (e.g. ECS / App Runner behind a public
  HTTPS endpoint — the hosting shape the Connect guide's "the provider
  gives you the endpoint URL and an API key" model describes). That is
  a **Gate 0 architecture decision for Steven**, not a silent
  substitution: the agent stays custom Bedrock; only the hosting
  changes, and it goes back to you before anything is built.

## Terraform gaps (documented, not hidden)

| Gap | Why it is not in Terraform | Where it is handled |
|---|---|---|
| AppIntegrations `A2A_SERVER` application | No first-party Terraform resource exists. CloudFormation's `AWS::AppIntegrations::Application` exists but its `ApplicationType` allows only `STANDARD \| SERVICE \| MCP_SERVER` — no `A2A_SERVER` — and it has no `AuthConfig` (API key) property. | `register-connect.sh` step 2 (CLI, per the guide). |
| Connect integration association, type `APPLICATION` | The official `aws_connect_integration_association` resource does not support the `APPLICATION` type. A third-party provider (USAN/awsext) fills the gap — **not adopted**: a spike should not add an unaudited third-party provider to the state. | `register-connect.sh` step 3 (CLI). |
| qconnect orchestrator AI agent + collaborator, security profile, publish | API-only feature (qconnect/connect APIs); no Terraform coverage. | `register-connect.sh` steps 4–6 (CLI) + console for the permission. |
| Gen-1 test flow | Flow Designer / console work. | Console (step 7 above). |

Also: `network_configuration` is **required** by the provider schema
(the draft sets `PUBLIC`); `protocol_configuration.server_protocol =
"A2A"` was verified valid in the provider source; `request_header_configuration`
is set to allowlist `traceparent`, `tracestate`,
`A2A-Extensions` — `Authorization` was removed 24 Nov (see the
finding in risk #1: it cannot be allowlisted without a custom JWT
authorizer, and Connect's key is not a JWT).

## UNVERIFIED — details the docs do not settle (the live run decides)

1. **Runtime authorizer NONE.** Whether omitting
   `authorizer_configuration` leaves the invocations endpoint callable
   with only the API-key bearer (no SigV4). Decisive test in risk #1.
2. **Header forwarding through the Runtime proxy.** Whether
   `traceparent`, `tracestate` and `A2A-Extensions` reach the
   container (the allowlist is set, but field reports say the proxy
   strips headers without an `X-Amzn-Bedrock-AgentCore-Runtime-Custom-`
   prefix, except `Authorization`). The spike logs exactly which
   headers arrived at INIT_SESSION (`headers_seen` in the
   `init_session` log line). If `traceparent` does not arrive, the
   trace span starts a fresh trace id — correlation (point 6) is then
   partial, and that is a Gate 0 finding. `Authorization` reaching the
   container is proven by the 401/200 behaviour, not by the log.
3. **ROLE_USER / ROLE_AGENT on the wire.** Whether Connect actually
   sends `ROLE_*` or the docs samples use stale naming. The middleware
   handles both; the `role_normalized` log line tells you which one
   Connect sent (if it never appears, Connect sends user/agent).
4. **CHANNEL_STATE acknowledgement shape.** The AWS docs publish no
   sample response for CHANNEL_STATE. The spike answers with a
   non-final `working` status update. If Connect expects something
   else, the live call will show it (e.g. a repeated CHANNEL_STATE or
   an error event). Note: a cosmetic SDK warning,
   "Queue is closed. Event will not be dequeued.", appears in the log
   after the CHANNEL_STATE response in local testing — the returned
   task still carries state `working`, so it is treated as noise.
5. **Text immediate-handoff restrictions.** The no-orchestration-prompt
   / no-guardrail / Complete-tool-only restriction on the orchestrator
   is documented for **audio** immediate handoff. Whether it also
   applies to **text** immediate handoff is not stated. The draft
   configures `immediateHandoff: true` with no prompt; if
   `create-ai-agent` rejects it on validation, retry with
   `immediateHandoff: false` plus an orchestration prompt.
6. **Agent Card fields Connect requires.** No exhaustive list is
   published. The draft serves a full standard card (name, url,
   version, provider, protocol 1.0, JSONRPC, capabilities with the
   Connect extension, one skill, apiKey security scheme). If Connect
   rejects the card at registration or at call time, the error will
   name the missing field — that is a Gate 0 finding, not a guess.
7. **The `tracestate` parent span.** Connect sends
   `tracestate: connect=parentSpanId:{full-uuid}` alongside the W3C
   `traceparent`. The spike adopts the traceparent's parent span id
   as the root span's parent (per the contract's "adopt the propagated
   traceId and parent span") and logs the tracestate value. Whether
   Connect expects the full-UUID parent instead is not stated.
8. **Runtime session header.** The AgentCore docs show clients sending
   `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`; Connect does not
   send it. Whether the proxy requires it for A2A sessions (or
   generates one) is not documented — the live call decides.

## Local verification (done 2026-11-24, this environment)

`bash scripts/test-spike-local.sh` — **23/23 checks pass**, no AWS, no
model (`SPIKE_NO_MODEL=1`, throwaway dev key). The driver
(`scripts/smoke_test.py`) replays the Connect HTTPS flow from the AWS
sample events: `/ping`, agent card (name, version, extension,
apiKey scheme, protocol 1.0/JSONRPC), 401 without/wrong bearer,
INIT_SESSION with `ROLE_USER` → INIT_SESSION_RESPONSE (200) with the
A2A-Extensions header echoed, CHANNEL_STATE READY → working task,
turn 1 → exactly the fixed reply + TRACING_SPAN artifact (root
`invoke_agent` span + `chat` child span, adopting Connect's traceId)
+ terminal completed with **no** FINISH, re-INIT on the same contextId
→ INIT_SESSION_RESPONSE again (turn counter kept), turn 2 → terminal
completed with **FINISH ESCALATE**, `tasks/get` returns the turn-1
task, INIT_SESSION without a `kind` field still accepted,
DTMF_INPUT_COMPLETE treated as a text turn with the fixed reply.

Two real bugs were found and fixed by this smoke test (both are why the
test exists): a2a-sdk models `capabilities.extensions` as
`AgentExtension` objects (not bare URI strings), and message parts
arrive as `Part` RootModels whose real part lives in `.root` — the
unwrapping is in `_unwrap_part()`.

**Not validated here:** `docker build` and `terraform validate`
(neither binary exists in this environment). Run both before apply;
the README steps above include the commands.

## Deliberately left out (for Steven to decide)

- **No tools, no case lookup, no Gateway/MCP, no Policy, no
  Guardrails, no Memory.** The spike proves the seam only. WP2/WP3
  add the read-only case-status tool behind Gateway with Policy +
  Guardrails; the brief's redlines govern those steps.
- **No model bake-off.** The spike uses Haiku 4.5 because it is
  already authorized on the account. The bake-off (brief §5, redline
  5) happens in WP3 against the same evaluation set — the spike's job
  is the seam, not the model choice.
- **No CI, no image-build script, no state backend.** The Terraform
  uses local state (Project #2's pattern); a remote backend is a WP1
  decision.
- **No WebSocket server.** HTTPS only. If a later phase wants audio
  streaming (`wss://`), the server needs a WebSocket transport — a
  separate design decision, not an extension of this file.
- **No cost estimate.** Runtime + Bedrock + Connect usage pricing for
  the spike is small but unverified; the cost-per-resolved-contact
  measure (redline 8) is a WP3/WP5 output, not a spike claim.

## Sources (all read 2026-11-24)

- Connect admin guide, "Build an external AI agent server":
  https://docs.aws.amazon.com/connect/latest/adminguide/a2a-voice.html
- "A2A protocol contract for external AI agents":
  https://docs.aws.amazon.com/connect/latest/devguide/a2a-developer-guide.html
- "Set up an external AI agent integration":
  https://docs.aws.amazon.com/connect/latest/adminguide/a2a-setup-external.html
- "How agent-to-agent collaboration works":
  https://docs.aws.amazon.com/connect/latest/adminguide/a2a-how-it-works.html
- AgentCore dev guide, "Deploy A2A servers in AgentCore Runtime":
  https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-a2a.html
- Terraform provider source, `aws_bedrockagentcore_agent_runtime`
  schema (hashicorp/terraform-provider-aws, `main`,
  `internal/service/bedrockagentcore/agent_runtime.go`):
  `agent_runtime_artifact` (container/code), `protocol_configuration`
  (`server_protocol`), `network_configuration` (required),
  `request_header_configuration` (allowlist), `authorizer_configuration`
  (only `custom_jwt_authorizer` — no NONE / AWS_IAM in Terraform).
- Gen-1 design brief: `docs/gen-1-design-brief.md` in
  `steveawsgray-gif/agentic-connect` (Gate 0 list §4, repo layout §11,
  redlines §12). Project #2 Terraform style:
  `steveawsgray-gif/amazon-connect-migration-primer`, `terraform/`.
