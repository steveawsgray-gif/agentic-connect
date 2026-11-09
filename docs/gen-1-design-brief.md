# Project 3 — Generation 1 design brief

**Status:** Design brief — November 9, 2026  
**Build state:** Design only. No Project 3 resources have been built or deployed.  
**Build gate:** Implementation starts after the AWS certification, on Steven's word.

## The design in one paragraph

Project 3 adds one governed, custom AI agent to the working Project 2 contact centre. The first agent works only in General Support, handles case-status and service-navigation enquiries, uses read-only tools, and escalates everything outside that narrow job to the human floor. Amazon Connect remains the system of record for the contact; Amazon Bedrock AgentCore is the control plane for the agent. Connect owns telephony, queues, recordings, contact records and human escalation. AgentCore holds the selected model in a versioned cradle — Runtime, Memory, Gateway, Identity, Policy, Guardrails, Observability and Evaluations — so the model's intelligence can be used without giving it the run of the floor.

> The model is the ordnance. AgentCore is the handling gear. Guardrails and policy are the pin.

## 1. The starting point is a working floor, not a blank account

Project 2 is already live and validated:

- Amazon Connect instance `sgray-connect-migration-primer` in `us-east-1`.
- Published inbound number **+1 531-247-6511**, attached to the Main Inbound customer-lookup flow.
- Priority Support, Billing and General Support queues, operating Monday to Friday, 08:00–18:00 America/Toronto.
- A Lambda customer-lookup step backed by DynamoDB. Known callers route from their customer record; unknown callers fall back safely to General Support.
- Call recordings, contact records and a Firehose-to-S3-to-Athena reporting path are already in place.
- Steven's final validation call proved the live path end to end on October 30, 2026.

Project 3 does not rebuild that floor, replace its queues or grow an AI layer inside Project 2's original flow. It creates a separately versioned Generation 1 flow for testing. The original published flow remains untouched as the rollback position.

## 2. Generation 1 has one job

### Working name

**General-1: Case Status and Service Navigation**

### The job it may do

General-1 may:

- establish why the caller is calling;
- answer service-navigation questions from approved knowledge, including hours, queue responsibilities and what happens next;
- ask for a case reference when the caller wants a case status;
- retrieve a limited case status through a read-only tool;
- explain the returned status in plain language;
- ask one clarifying question when the request is ambiguous;
- end the contact as resolved only when the caller's request was answered from approved knowledge or a successful tool result;
- escalate to a human with a concise handoff packet whenever the work leaves its boundary.

### The work it must never do

General-1 must not:

- take a payment or discuss payment-card data;
- change an account, case, appointment, address or any other record;
- create, close, reopen or reassign a case;
- handle Priority Support or Billing work beyond identifying the correct human queue;
- authenticate a caller from a phone number;
- disclose a case status when the supplied case reference and caller context do not match;
- invent a status, policy, time commitment or next step;
- continue after the caller asks for a human;
- treat a model answer as authority when no knowledge source or tool result supports it.

### Autonomy boundary

| Request or action | General-1 decision |
| --- | --- |
| Approved hours or service information | Answer alone |
| Case status after a successful record match | Answer alone |
| Ambiguous request | Clarify once, then escalate if still unclear |
| Billing or Priority issue | Transfer to the correct human queue |
| Any request to change state | Escalate; no write tool exists |
| Complaint, distress or vulnerability | Escalate to a human |
| Caller asks for a human | Escalate immediately |
| Tool, policy or model failure | Fail safely to General Support |

The first release is deliberately read-only. A useful agent that cannot change records can still prove the architecture, the controls and the handoff. Write authority is a later design decision, not a Generation 1 shortcut.

## 3. The contact journey

1. During testing, the caller enters the Generation 1 flow through a separate test entry point. The Project 2 number remains attached to the original flow until the design has passed its supervised proof gates.
2. Connect performs its existing recording, logging and customer-lookup steps.
3. An eligibility gate offers General-1 only when the contact is routed to General Support, the language is supported, a human fallback is available and no Priority or Billing marker is present. The caller may decline and go straight to the human queue.
4. Connect starts the agent session with the minimum context required: contact identifier, channel, language, routing result and an AgentCore session identifier. The full customer record is not passed into the model, and the model never receives the caller's phone number.
5. General-1 answers from approved knowledge or invokes the case-status tool through AgentCore Gateway.
6. The agent returns one of four outcomes: `RESOLVED`, `ESCALATE`, `UNSUPPORTED` or `FAILED_SAFE`. An escalation also carries the target queue.
7. For `RESOLVED`, Connect closes the automated portion of the contact and records the outcome.
8. For `ESCALATE`, Connect transfers the caller to the target human queue. For `UNSUPPORTED` or `FAILED_SAFE`, Connect transfers the caller to General Support. Every transfer carries the handoff packet.
9. Connect remains responsible for the recording, contact record, queue time and final disposition. AgentCore retains the trace of agent turns, tool calls, latency and outcome.

Caller ID remains a routing signal, not proof of identity. Generation 1 uses demonstration data, so a matched case-status answer is acceptable for the portfolio build. A production design would require a separate authentication step before disclosing case information.

## 4. The preferred integration is A2A, proved before the agent is built

The preferred seam between Connect and the custom agent is the Agent-to-Agent protocol, or A2A:

- Connect Customer's agent-to-agent collaboration can bring an external AI agent into a live interaction over A2A, including bidirectional voice, while Connect coordinates context, observability and escalation.
- AgentCore Runtime can host an A2A server with an Agent Card describing the agent's identity, skills and endpoint.
- The conversational worker remains Steven's custom agent on AgentCore. It is not replaced by a Connect-native AI agent.

That distinction is the project. Connect is the contact system and the floor manager. AgentCore is where the custom agent is built, governed and observed.

### Gate 0 — integration spike

Before any agent logic is built, a short spike must prove all of the following on the actual Project 2 instance:

- A2A collaboration is available for the instance and Region in the form the design requires;
- a minimal AgentCore Runtime A2A endpoint can join a test interaction;
- Connect passes the required context into the session;
- the agent can return a controlled outcome;
- escalation returns the live contact to General Support;
- the Connect contact record and AgentCore trace can be correlated;
- voice latency is acceptable for a natural conversation;
- disabling the endpoint restores the human-only path cleanly.

If A2A cannot be proved, the build stops at Gate 0 and Steven chooses the next route from the evidence. The design does not silently substitute a Connect-native agent, because that would change Project 3's thesis.

## 5. Inside the cradle

| Cradle component | Generation 1 use |
| --- | --- |
| Runtime | Hosts one versioned, code-defined agent endpoint with isolated sessions |
| Memory | Short-term session context only; no long-term customer memory |
| Gateway | Exposes the approved tools through Model Context Protocol, or MCP |
| Identity | Gives the agent its own workload identity and controlled tool access |
| Policy | Enforces the tool allowlist and conditions at Gateway, outside the model |
| Guardrails | Screens configured inputs and outputs for content and sensitive information |
| Observability | Traces model turns, tool calls, latency, errors and outcomes |
| Evaluations | Runs repeatable quality and safety tests before and after release |

### Agent implementation

The reference implementation is a code-defined Strands Agents application hosted on AgentCore Runtime and exposed as an A2A server. AgentCore is model-agnostic, so the design does not marry the project to one foundation model before testing.

The model is selected by a small bake-off using the same evaluation set for each candidate. The selection criteria are, in order:

1. correct escalation and refusal behaviour;
2. grounded factual accuracy;
3. voice conversation latency;
4. tool-use reliability;
5. cost per resolved contact.

“Tailoring” means the work around the model: instructions, approved knowledge, tool schemas, examples, policy, evaluation cases and Steven's corrections after reviewing failures. It does not mean weight fine-tuning by default. Steven supplies the architectural and business judgement on the loop; every accepted correction becomes a versioned change and the full evaluation set runs again.

### Memory rule

Generation 1 remembers only what it needs during the current contact. It does not build a long-term profile of a caller, carry facts between calls or learn privately from production conversations. Any future long-term memory requires its own purpose, retention and consent design.

## 6. Tools and knowledge stay narrow

### Tool 1 — case status

The only business tool in the first release is a read-only case-status lookup.

- It is exposed through AgentCore Gateway as an MCP tool.
- A Project 3 adapter performs the lookup; Project 2's routing Lambda is not modified.
- The model supplies only the case reference. The adapter obtains the caller key from the authenticated session context, not from a model-generated argument.
- Because the Project 2 directory is keyed by caller number, the adapter can perform a direct item read and compare the supplied case reference server-side. It does not need a table scan or a new index for the demonstration data.
- The adapter reads only the fields required to answer the status question.
- The model receives a minimized result: whether a match was found, whether the case is open, the owning queue and a coded next step.
- The model does not receive the full customer row.
- Invalid input, no match and a case-reference mismatch all produce escalation, not a guessed answer.

### Approved knowledge

The agent's reading material is a small, versioned knowledge set covering:

- business hours and closure behaviour;
- what each queue handles;
- how case status and escalation work;
- what information a human agent may ask for next;
- the privacy line: what the automated agent cannot confirm or change.

Knowledge sources live with the project, have an owner and a version, and are tested like code. General-1 does not browse the open web.

### Tools deliberately excluded

Generation 1 has no browser tool, no code interpreter, no payment tool, no customer-record write tool and no free-form database query. Leaving those capabilities out is part of the safety case.

## 7. The pin is enforcement outside the model

A prompt instruction is advice to the model. It is not a control. Generation 1 therefore places enforcement outside the agent's reasoning loop.

AgentCore Policy, attached to Gateway, is the pin for tool use. The policy design starts from denial and permits only the named case-status operation under the session conditions the design defines. AgentCore Policy uses Cedar, and current AgentCore policy evaluation can also consume signals from Amazon Bedrock Guardrails.

Amazon Bedrock Guardrails provide a second layer at the model boundary for configured content and sensitive-information checks on inputs and outputs. Neither layer is treated as magic. The evaluation set must prove that forbidden requests do not reach a tool and that unsafe or unsupported answers do not reach the caller.

### Non-negotiable control rules

- No tool exists unless it is named in the Generation 1 allowlist.
- No successful match, no case disclosure.
- No knowledge source or tool result, no factual claim.
- No state-changing action exists in the first release.
- A request for a human overrides task completion.
- A timeout, malformed tool result or policy denial produces a safe escalation.
- A feature flag can remove General-1 from the flow without changing the human queues.
- The original Project 2 flow remains the immediate rollback.

## 8. A human receives a handoff, not a mystery

Every escalation carries a short packet:

- Connect contact identifier;
- AgentCore session and trace identifiers;
- escalation reason code;
- the caller's request in one or two plain sentences;
- the case reference, if the caller supplied one;
- tools attempted and their outcome categories;
- the last supported fact given to the caller;
- the agent's recommended next human action.

The packet contains no hidden model reasoning. It records what happened, what was verified and why the human is receiving the contact. The human should never have to make the caller start over.

Connect is the customer-activity record. AgentCore is the agent-behaviour record. The two records are joined by contact and session identifiers, not merged into one undifferentiated log.

## 9. Success is correct behaviour, not deflection

Generation 1 is not judged by how many callers it keeps away from people. It is judged by whether it does the right thing with each contact.

### Measures

- percentage of in-scope contacts with the expected outcome;
- grounded-answer rate under human review;
- escalation correctness;
- case-disclosure errors;
- forbidden-tool attempts blocked;
- failure-to-queue rate during injected faults;
- first-response and full-turn latency;
- model and AgentCore cost per resolved contact;
- cost and handle time of an escalated contact;
- caller requests for a human that were honoured immediately.

### Evaluation set

The first evaluation set contains 60 scenarios:

| Scenario group | Count |
| --- | ---: |
| In-scope status and service questions | 20 |
| Ambiguous or incomplete requests | 10 |
| Out-of-scope and state-changing requests | 10 |
| Prompt-injection and data-extraction attempts | 10 |
| Tool, model and timeout failures | 10 |

Deterministic checks verify the outcome, tool use and forbidden-action behaviour. Human review scores factual grounding, clarity and tone. AgentCore Evaluations may assist with repeatable scoring, but they do not replace Steven's review of the failures.

### Proposed release gates

Generation 1 does not proceed to a live supervised test unless:

- 100% of state-changing requests escalate without any state-changing action;
- 100% of mismatched case checks produce no disclosure;
- 100% of forbidden-tool attempts are blocked;
- 100% of injected service failures land safely in General Support;
- at least 95% of in-scope scenarios produce the expected outcome;
- every caller request for a human escalates immediately;
- Steven has reviewed every remaining failure and accepted or corrected it.

Latency and cost ceilings are set from Gate 0 and model bake-off measurements rather than invented in the design.

## 10. Build sequence after certification

### Work package 0 — integration spike

Prove the A2A seam, context passing, outcome return, escalation, trace correlation and kill switch with the smallest possible endpoint.

**Exit gate:** A short evidence note records what worked, what did not and whether the preferred architecture remains viable.

### Work package 1 — cradle skeleton

Create the versioned AgentCore Runtime endpoint, workload identity, observability, configuration, budget alarms and infrastructure as code. Terraform is the first choice to match Project 2; any AgentCore coverage gap is isolated and documented rather than hidden behind console changes.

**Exit gate:** An empty but governed cradle can be deployed, invoked, traced, disabled and removed.

### Work package 2 — knowledge and the one tool

Publish the approved knowledge set, build the read-only case-status adapter and expose it through Gateway with least-privilege access.

**Exit gate:** Tool contract tests pass for match, no match, malformed input and service failure.

### Work package 3 — agent and pin

Build the Strands agent, A2A card, instructions, outcome contract, Policy rules and Guardrails configuration. Run the model bake-off.

**Exit gate:** One selected model and one agent version pass the offline evaluation set.

### Work package 4 — Connect integration

Build the Generation 1 test flow, separate test entry point, eligibility gate, outcome branches, handoff attributes and rollback switch. Project 2's original published flow and its published number remain untouched during testing.

**Exit gate:** Steven's scripted validation calls prove resolved, escalated, unsupported and failed-safe paths.

### Work package 5 — supervised proof

Run controlled calls with a human monitoring the floor. Review every trace and failure with Steven, tailor the agent, rerun the full evaluation set and publish the evidence in the Project 3 README.

**Exit gate:** The repository shows the working agent, its controls, its test results and its limits without overstating what was built.

## 11. Proposed repository shape

```text
agentic-connect/
├── README.md
├── docs/
│   ├── gen-1-design-brief.md
│   ├── gen-1-validation-results.md
│   └── diagrams/
├── agent/
│   ├── src/
│   ├── instructions/
│   └── agent-card/
├── tools/
│   └── case-status/
├── knowledge/
├── policies/
├── evals/
│   ├── scenarios/
│   └── reports/
├── connect/
│   └── gen-1-flow/
└── infra/
```

The layout is a proposal for the build, not a claim that these folders exist today.

## 12. Decisions for Steven's redline

The draft recommends the following decisions. None is treated as settled until Steven marks it:

1. **First job:** case status and service navigation in General Support.
2. **Integration:** A2A first, with Gate 0 proof and no silent substitution of a Connect-native agent.
3. **Authority:** read-only tools only; no state change in Generation 1.
4. **Memory:** short-term session memory only; no long-term caller memory.
5. **Model:** choose by bake-off, not by brand preference.
6. **Implementation:** code-defined Strands agent on AgentCore Runtime.
7. **Infrastructure:** Terraform first, matching Project 2, with any AgentCore gap documented.
8. **Success measure:** correct outcome and cost per resolved contact, not deflection.

## 13. What Generation 1 proves — and what it does not

Generation 1 proves that a custom, governed agent can take one real seat beside the human floor: enter through the contact system, use one controlled tool, answer from approved knowledge, protect its boundary and hand back a clean contact when the work is not its own.

It does not prove the second-generation matrix. Billing remains human. Priority remains human. No agent changes a record, and no queue is displaced. Those limits are the point: coexistence first, evidence before expansion.

The path from here is visible in the second-generation diagram. Generation 1 earns the right to take the next step only by behaving correctly in the smallest possible job.

## Sources

- [Amazon Bedrock AgentCore FAQs](https://aws.amazon.com/bedrock/agentcore/faqs/) — Runtime, Memory, Gateway, Identity, Observability, Evaluations and Policy capabilities.
- [Deploy A2A servers in AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-a2a.html) — A2A hosting, Agent Cards and protocol support.
- [Policy in Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy.html) — policy engines, Gateway interception and Cedar.
- [Amazon Connect Customer release notes](https://docs.aws.amazon.com/connect/latest/adminguide/amazon-connect-release-notes.html) — agent-to-agent collaboration with external agents over A2A.
- [Amazon Connect flow block definitions](https://docs.aws.amazon.com/connect/latest/adminguide/contact-block-definitions.html) — Lambda, External Tool and queue-transfer building blocks.
- Project 2 architecture and deployment results, Steven Gray's portfolio records, October 2026.
