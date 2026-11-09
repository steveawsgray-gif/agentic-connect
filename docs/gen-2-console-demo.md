# Project 3 — Generation 2: console demo

**Status:** Design asset — November 9, 2026. The demonstration script for the Generation 2 matrix, written from the [Generation 2 design brief](gen-2-design-brief.md). It walks the two consoles the architecture is operated from. It is a demo of the design — screens are described as the design specifies them; live proof belongs to Generation 1.

**The one-sentence version for the viewer:** *Connect is where you watch the customers. AgentCore is where you watch the agents. Generation 2 is operated from both, and every contact exists in both.*

## View 1 — The floor (Amazon Connect console)

What the supervisor sees is a familiar contact centre with one new dimension: who — pod or human — is holding each contact.

- **Queues panel:** Priority, Billing and General Support as in Project 2, each showing contacts split by holder: pod-held, human-held, hybrid (pod preparing, human joined). Queue times and service levels read as they always have.
- **Exception tier panel:** the human agents, shown with their proficiency profiles. Routing-step reporting shows where contacts matched at the strictest criteria, where steps relaxed, and where they exhausted to any-agent — the evidence staffing decisions are made from.
- **Surge indicator:** when the standby pod is armed, the floor view shows it as a capacity state, with the narrowed scope it is operating at.

**Demo beat 1 (30 seconds):** "This is still a contact centre. Same queues, same recordings, same contact records. The only difference is that some of the seats are held by governed agents — and you can see exactly which ones, contact by contact."

## View 2 — The matrix (Amazon Bedrock AgentCore console)

What the operator sees is the loaded matrix itself: one row per pod, the state of every cradle on the floor.

| Pod | Version | Tier | Eval standing | Resolved | Escalated | Cost / resolved |
| --- | --- | --- | --- | --- | --- | --- |
| general-status | 1.4.0 | A | Passing | 96% | 4% | baseline |
| general-knowledge | 1.2.1 | A | Passing | 94% | 6% | baseline |
| billing-info | 1.1.0 | A | Passing | 93% | 7% | baseline |
| billing-casework | 0.9.3 (canary) | B | Canary — A/B running | — | — | watch |
| priority-triage | 1.0.2 | C | Passing | n/a (prepares) | 100% by design | baseline |
| standby-surge | 1.0.0 | A (narrowed) | Armed / stood down | — | — | — |

*(Illustrative values for the demo script — the columns are the design; the numbers are what production would fill in.)*

- **Per-pod drill-down:** model and version, tool allowlist, policy tier, memory scope, guardrail profile — the pod's entire load, readable on one screen.
- **Trace view:** every turn, tool call and policy decision for any session, correlated to the Connect contact by ID.
- **Evaluation view:** online scores per pod, failure-pattern and intent insights, and the promotion pipeline — which version is in shadow, which is in canary, what the A/B says.

**Demo beat 2 (60 seconds):** "Each row is one cradle: a Bedrock model, held by AgentCore, pinned by policy. Nothing on this board takes a call it hasn't been evaluated for — and the board shows the evidence, not a promise."

## The three moves the demo exists to show

1. **Follow one contact across both consoles.** Take the billing dispute from the [call-flow walkthrough](gen-2-call-flow-walkthrough.md): find it in the Connect record (recording, outcome, case reference), then open the same contact's trace in AgentCore and walk the tool calls and the policy decision that allowed the one bounded write. One contact, two consoles, zero gaps.
2. **Withdraw a pod.** From the matrix board, billing-casework is stood down. The floor view absorbs it in real time: its contacts route to the human Billing queue, the queue depth moves, nothing errors, no caller is dropped. "The matrix degrades gracefully — a pod is a load you can set down."
3. **Promote a version.** Show a candidate pod version in shadow, its offline evaluation results, the canary slice and the A/B comparison — then the registry state change that makes it the loaded version. "Nobody edits a live agent here. Versions earn the floor."

## What the demo deliberately does not do

It does not place a live call and pretend the matrix answered it. Generation 1's supervised proof is where live calls happen — one pod, one job, real evidence. This demo shows the destination that proof is aimed at: the complete Terraform, the two consoles, and the flows, with every screen labelled design-stage. An architect's demo is the design, shown whole — not a stage set.
