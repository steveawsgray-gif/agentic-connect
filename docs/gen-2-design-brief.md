# Project 3 — Generation 2 design brief: the loaded matrix

**Status:** Design brief — November 9, 2026
**Build state:** Destination-state design only. Generation 2 is not built, and it is not scheduled. It is reached, if at all, through the Generation 1 proof gates and Steven's word at each step.
**Relationship to Generation 1:** This brief designs the state the [Generation 1 brief](gen-1-design-brief.md) is built to grow into. Generation 1's cradle pattern, outcomes contract and evaluation discipline are deliberately designed so they can be cloned, pod by pod, into the matrix described here.

## The design in one paragraph

Generation 1 infused a step: one governed agent borrowed one seat in General Support while humans owned the floor. Generation 2 staffs the floor: a matrix of queue-dedicated agent pods, each a clone of the Generation 1 cradle loaded for a specific job family, becomes the primary handler for every contact type it has been certified to resolve. Humans do not leave. They invert — from the destination every contact was heading for, to the exception tier that takes everything the matrix is not certified for: judgement, emotion, negotiation, vulnerability, and the genuinely new. Amazon Connect remains the system of record for the contact and the floor manager. Amazon Bedrock AgentCore remains the control plane for every agent on it. Skills-based routing decides, contact by contact, whether a pod, a human, or both should take the work.

> Generation 1 infused a step. Generation 2 staffs the floor — and the humans hold the exceptions, which is where their value always was.

## 1. What changes, and what does not

**What changes from Generation 1:**

- One agent becomes a matrix: several pods, each dedicated to a queue and a job family.
- The agent stops being a guest in one queue and becomes the primary handler for certified work in all three queues.
- Routing stops being an eligibility gate for one agent and becomes the central decision of the floor: pod, human, or hybrid.
- Write authority, forbidden in Generation 1, becomes possible — pod by pod, tool by tool, each one separately earned.
- Evaluation stops being a release gate for one agent and becomes the continuous operating discipline of the whole matrix.

**What does not change:**

- Connect owns telephony, queues, recordings, contact records and human escalation. AgentCore owns agent behaviour, tools, policy and traces.
- The conversational workers are custom agents built on Bedrock models in AgentCore cradles — never Connect-native agents.
- Every agent works a bounded job, with named work it must never do.
- Escalation to a human is immediate on request, always available, and treated as a designed outcome, not a failure.
- Caller ID is a routing signal, never authentication.
- No pod reaches the floor on a demo. Each one arrives through evidence: offline evaluation, shadow running, canary traffic and supervised proof.

## 2. The matrix: one pattern, many loads

A **pod** is one Generation 1 cradle, cloned and loaded for one job family: its own Runtime endpoint and version, a model chosen for that job by bake-off, its own memory scope, its own Gateway tools under least-privilege identity, its own policy tier and guardrail profile, and its own evaluation suite. The pattern is proven once in Generation 1; the matrix is that pattern repeated with discipline.

| Pod family | Job families | Autonomy tier |
| --- | --- | --- |
| General — status and accounts | Case status, account information, service navigation | **Tier A** — resolve autonomously, read-only |
| General — knowledge | Hours, policies, procedures, what happens next | **Tier A** — resolve from approved knowledge |
| Billing — information | Billing explanations, payment status, dispute information | **Tier A** — read-only |
| Billing — casework | Dispute intake, case creation drafts, callback scheduling | **Tier B** — bounded writes, earned tool by tool |
| Priority — triage | Structured intake, severity assessment, case preparation, routing | **Tier C** — prepare and hand off; never resolve |
| Standby — surge and overflow | Status and information at reduced scope during spikes and outages | **Tier A, narrowed** — absorbs volume, protects the human tier |

Three design rules hold the matrix together:

1. **One accountable agent per contact.** A pod may consult another pod, but exactly one pod owns the contact and its outcome. There is never a committee talking to a caller.
2. **Pods are loaded, not improvised.** A pod's job, tools, policy tier and evaluation suite are versioned and approved before it takes traffic. A pod that has not passed its gates is not on the floor, whatever the demo pressure.
3. **The matrix degrades gracefully.** Any pod can be withdrawn independently — for a defect, a drift alarm, or a business decision — and its traffic falls back to the human queue or a neighbouring pod without taking the floor down.

AgentCore Registry is the catalogue of record for the matrix: the governed place where agent versions, tools and skills are published, reviewed and approved. "Loaded" is a registry state, not a hope — only an approved, evaluated version can be assigned traffic.

## 3. Autonomy tiers: write authority is earned, never general

Generation 1's hardest rule — no writes, ever — is a starting position, not a permanent one. Generation 2 replaces the blanket ban with tiers, because a Billing pod that can open a dispute case is genuinely more useful than one that can only describe how disputes work. The tiers keep the Generation 1 discipline while letting capability grow where the evidence supports it.

- **Tier A — read and resolve.** Information and status work, read-only tools, exactly as Generation 1. This is the default tier for every new pod.
- **Tier B — bounded writes.** A pod may change state only through individually approved Gateway tools, each one designed to be narrow, idempotent and auditable, and each one gated by the pin (see section 5). Confirm-before-commit applies to anything a caller would notice: the agent states what it is about to do, the caller agrees, the tool executes, the result is confirmed back. Irreversible or high-value actions are not Tier B at any level of confidence — they go to a human.
- **Tier C — prepare, never resolve.** Priority work is the most guarded because the callers are the most exposed. The Priority pod's value is speed and structure: it gathers the facts, assesses severity against approved criteria, prepares the case and routes it to the right human with a complete packet. It makes no promises, offers no resolutions and never sits between a distressed caller and a human longer than the intake takes.

Payment-card data stays out of the matrix entirely at every tier. Where a payment itself must be taken, the contact uses a secure payment flow or a human — the pods handle the conversation around payments, never card numbers.

Promotion between tiers is per pod and per tool, decided on evaluation evidence and incident history, and reversible: a tool that misbehaves is withdrawn without withdrawing the pod.

## 4. Routing: skills decide who takes the contact

In Generation 2 the routing decision is the floor's central act, and it is made from skills in both directions:

- **Human skills** use Connect's native proficiency routing: predefined attributes and proficiency levels assigned to human agents, with routing criteria set on the contact in steps — the most specific match first, relaxing only as steps expire. The exception tier is staffed by proficiency, not by whoever happens to be free.
- **Agent skills** are advertised on each pod's A2A Agent Card — the standard mechanism by which an A2A server publishes its identity, skills and endpoint for discovery. The matrix knows what each pod is certified to do because the pod declares it, in the open, in its card.
- **The skill router** combines the two. It is a routing decision made in the contact flow with the help of a small routing service, using intent, queue, language, risk markers, caller state, pod health, evaluation standing and current load. Its outputs are exactly three: assign a pod, route to a human by proficiency, or run a hybrid — a pod prepares and a human joins with the work already done.

The router's decisions are policy and signals, not a model's whim: the criteria are written down, versioned, and auditable in the contact record. A contact that matches no certified pod goes to a human by default. Uncertainty routes to people, never to the nearest agent.

Agent-to-agent collaboration happens behind the owning pod, not instead of it. A General pod that hits a billing-policy question can consult the Billing knowledge pod over A2A and use the answer inside its own conversation. The caller experiences one agent; the matrix experiences a consultation. Consultation depth is capped, latency is budgeted, and if the consult fails or times out, the owning pod escalates rather than improvising.

## 5. The pin at scale

Generation 1 put a pin in one cradle. Generation 2 needs the pin to hold across a matrix, so control is layered:

- **Per-pod identity and tools.** Each pod acts under its own workload identity, with only the Gateway tools its tier allows. No pod can borrow another pod's tools; a Billing tool cannot be reached from a General session.
- **Policy at the Gateway.** AgentCore Policy — deterministic rules evaluated outside the model, at the tool boundary — allows or denies every tool call against the pod's tier, the tool's risk class and the contact's context. Guardrails continue to govern content at the model boundary. The model proposes; the pin disposes.
- **Promotion pipeline.** No pod version takes traffic directly. A candidate version passes its offline evaluation suite, runs in shadow against live traffic without touching callers, takes a canary slice, and proves itself in an A/B comparison against the incumbent — AgentCore's traffic-splitting and evaluation machinery exists for exactly this — before it is promoted in the Registry. A failed stage is a stop, not a negotiation.
- **Kill switches at two levels.** Every pod has its own withdrawal control, and the matrix has a global one. Either can be exercised without a deployment, and exercising one is a normal operational act, not an incident admission.
- **Continuous evaluation.** Production traces feed online evaluation and the insight loop — recurring failure patterns, intent clusters and trajectory outliers — so drift is caught from evidence across hundreds of sessions, not from one bad call read in isolation. Steven's tailoring loop, the fine-tuning input he feeds the build, operates on this evidence: changes are proposed, validated offline, A/B-tested, and shipped — never hot-edited into a live pod.

## 6. Memory: shared knowledge, private callers

Generation 1 kept memory inside the session. Generation 2 separates two things Generation 1 could afford to treat as one:

- **Service memory is shared.** Approved knowledge, failure patterns and trajectory insights are common property of the matrix — one pod's hard lesson becomes every pod's evaluation case. This is where the matrix genuinely learns.
- **Caller memory is private by default.** Long-term memory of an individual caller is off unless a specific, consented, retention-bound use is designed and approved. Where it is ever enabled, it is namespaced per pod, minimised, and treated as data the agent may use — never as authority. A remembered preference is not authentication, and a remembered fact is not permission.

This separation is deliberate: the matrix should get smarter about the *work* continuously, and about *people* only under explicit design.

## 7. The human exception tier

Generation 2 is designed around a claim about humans, not against them: the contacts that remain after the matrix takes the certified work are the contacts where human value is highest — ambiguity, emotion, negotiation, vulnerability, complaint, novelty. The exception tier is therefore staffed and protected like the premium resource it is:

- Humans are routed by proficiency, with routing-step analytics showing where criteria are met, relaxed or exhausted, so staffing follows the real exception mix rather than a guess.
- Escalation arrives warm: the handoff packet, the recording and the agent trace are correlated, so the human starts from the agent's work, not from "how can I help you?"
- Agents absorb surge first. The standby pod takes overflow at narrowed scope so a spike in simple contacts never floods the exception tier; humans meet the spike's hard contacts, not its volume.
- People also run the matrix: reviewing escalations for quality, reading evaluation failures, and feeding the tailoring loop. In Generation 2, "working the floor" includes teaching the floor.

A caller can reach a human at any point, on request, without argument or obstacle — in Generation 2 exactly as in Generation 1. The matrix's credibility rests on that door never closing.

## 8. The road from Generation 1 to Generation 2

Generation 2 is not a project; it is a sequence of gates, each with its own evidence and its own decision. Nothing on this road is automatic.

1. **Generation 1 proof.** The Generation 1 gates pass: one pod, one job, supervised evidence. Without this, there is no road.
2. **Shadow matrix.** Billing and Priority pods run in shadow — receiving live inputs, producing would-be answers that no caller hears, scored against what humans actually did. Shadow results decide which pod is even a candidate.
3. **First staffing.** The General pod family goes autonomous for its certified Tier A jobs. Billing joins read-only. The floor is now genuinely mixed, and the exception tier is measured for the first time.
4. **First bounded write.** One Tier B tool — recommended: Billing dispute intake — is designed, pinned, evaluated and canaried on its own. Write authority enters the matrix through exactly one door, watched.
5. **Priority triage.** The Tier C pod takes intake and preparation for Priority, the most guarded launch of the sequence, only after the escalation machinery has been proven by every earlier step.
6. **Surge and back-office.** The standby pod is armed for overflow, and pods begin taking asynchronous task work — after-contact summaries, case preparation, quality sampling — through Connect's task channel, where latency budgets are generous and supervision is natural.

Each gate can end the road. A matrix that stops at step 3 is not a failed Generation 2; it is a floor that found its correct mix.

## 9. Risks, and the questions this brief does not answer

- **Multi-pod consultation on voice is unproved.** Generation 1's Gate 0 proves one A2A agent in one interaction. Generation 2 assumes pods can consult and hand off without wrecking voice latency. That needs its own spike before any step past shadow, and compounded latency is the most likely technical killer of the whole design.
- **Cost per resolved contact decides the business case.** Pods scale elastically, but a matrix that resolves cheap contacts at premium model prices loses to the humans it staffs beside. Pod-level cost accounting — cost per resolved contact against the human baseline — is a first-class metric from step 3 onward, not a finance afterthought.
- **Evaluation coverage must grow with the matrix.** Every pod, tier and tool multiplies the scenario space. The promotion pipeline only protects contacts the evaluation suites actually cover; uncovered work must route to humans by construction, not by hope.
- **Drift is a when, not an if.** Models, knowledge and caller behaviour all move. The continuous evaluation loop exists because a pod certified in January is a hypothesis by June.
- **Open decisions for Steven, in his order, not this brief's:** which pod is second after Billing; the appetite for Tier B writes beyond dispute intake; whether caller long-term memory is ever switched on; and how much of the surge pod's narrowed scope is acceptable to callers in a crisis. The brief recommends; it does not decide.

## 10. What Generation 2 is not

- **Not a plan to remove humans.** It is a plan to spend humans where they are worth the most.
- **Not one giant general agent.** The matrix is many narrow pods precisely because narrow jobs can be pinned, evaluated and trusted; a generalist cannot.
- **Not Connect-native AI wearing a costume.** Every worker is a custom agent in an AgentCore cradle, or it is not Project 3.
- **Not built, and not a promise.** It is the destination the Generation 1 design is aimed at, written down so Generation 1's choices — the cradle pattern, the outcomes contract, the handoff schema, the evaluation discipline — are made in a way the matrix can inherit.

Generation 1 proves a governed agent can hold one seat. Generation 2 is the argument that the same discipline, cloned and routed by skill, can staff a floor — with the humans exactly where forty years of contact-centre work says they belong: on the contacts that were never routine in the first place.
