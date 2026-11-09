# Project 3 — Generation 2: call-flow walkthrough

**Status:** Design asset — November 9, 2026. A narrated contact journey through the Generation 2 matrix, written from the [Generation 2 design brief](gen-2-design-brief.md). This is a design walkthrough, not a transcript of a live call — Generation 1 carries the project's live proof.

## The flow, in blocks

```text
Caller → Gen-2 inbound flow (Connect)
  → recording + logging on
  → Lambda customer lookup (Project 2's data dip, reused read-only)
  → intent + risk classification
  → SKILL ROUTER decision ──┬─ POD        → owning pod takes the contact (A2A)
                            ├─ HUMAN      → queue + proficiency routing criteria
                            └─ HYBRID     → pod prepares, human joins warm
  → pod work loop: knowledge → Gateway tools (policy-checked) → consults (A2A, capped)
  → outcome: RESOLVED | ESCALATE | UNSUPPORTED | FAILED_SAFE  (+ handoff packet)
  → Connect closes the record: CTR, recording, disposition — one contact, one record
```

## Walkthrough 1 — a billing dispute, resolved by the matrix

**14:02:11 — Intake.** A known caller dials in. Connect starts the recording, runs the Project 2 customer lookup, and learns: existing customer, one open billing case. Intent classification hears "charged twice for October" — Billing, dispute family, no distress markers, English.

**14:02:19 — The router decides.** The skill router weighs intent, queue, language, risk and pod standing. The Billing information pod is certified for dispute information and is in good evaluation standing; dispute *intake* (a Tier B write) belongs to the Billing casework pod. Decision: **POD**, owner = Billing casework, with the information pod available for consultation. The decision and its inputs are written to the contact record — auditable later, not a model's mood.

**14:02:24 — The owning pod opens.** The casework pod greets the caller as an automated assistant (disclosed, always), confirms the duplicate charge from the billing system through its Gateway — a read the pin allows — and explains what it found in plain language. Behind the conversation, it consults the Billing knowledge pod over A2A for the current dispute-policy wording; the caller hears one agent, the matrix held a consultation.

**14:03:40 — The bounded write.** The pod proposes: "I can open a dispute case for the duplicate October charge and schedule the review callback. Shall I?" The caller agrees. Confirm-before-commit satisfied, the pod calls its one Tier B tool — dispute intake — through the Gateway. Policy evaluates the call against tier, tool and context: allowed. The tool creates the case idempotently (a retry cannot create two), returns the case reference, and the pod confirms it to the caller with the callback time.

**14:04:05 — Outcome.** `RESOLVED`. Connect closes the automated contact with the outcome, the case reference and the pod's version in the record; the AgentCore trace holds every turn, tool call and the policy decision. Total human involvement: none — and the contact record shows exactly why that was safe.

## Walkthrough 2 — the same afternoon, an exception

**15:17:02 — Intake.** A Priority caller, voice markers of distress, a vulnerable-service issue. Classification flags risk before intent is even complete.

**15:17:06 — The router decides HUMAN.** No pod is certified for this, by design. Connect sets proficiency routing criteria on the contact — the specialist skill first, relaxing in steps only as configured — and the contact waits for the right human, not the first free one.

**15:17:40 — The hybrid assist.** While the caller waits the measured seconds, the Priority triage pod does its Tier C work in the background: it assembles the caller's case facts into the handoff packet. When the human joins, they open with the situation already in front of them. The pod never spoke to the caller. That, too, is staffing the floor.

**15:19:55 — Outcome.** `ESCALATE` — recorded as a designed success. In Generation 2 metrics, a fast, warm, well-prepared escalation raises the matrix's score; it never lowers it.

## Walkthrough 3 — surge, briefly

**18:40 — A service outage triples call volume**, mostly "is it down, when is it back." The standby surge pod arms at its narrowed scope — status and information only — and absorbs the volume wave. The exception tier's queue stays near normal, because the humans are meeting the outage's hard contacts, not its hundred identical questions. When volume falls, the standby pod stands down; its contacts, outcomes and costs are in the same records as every other pod's.

## What the walkthrough demonstrates

- **One accountable agent per contact**, even when two pods touched it.
- **The pin working invisibly**: every tool call policy-checked, the one write confirmed before it committed.
- **Routing as the floor's central act** — pod, human and hybrid chosen per contact, from skills and standing, with the reasons on the record.
- **Escalation as a first-class outcome**, prepared by the matrix even when the matrix never speaks.
