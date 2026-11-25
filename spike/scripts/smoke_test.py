#!/usr/bin/env python3
"""Local smoke test for the Gate 0 spike agent (no AWS, no model).

Starts against a server running with SPIKE_NO_MODEL=1 and
SPIKE_DEV_API_KEY=test-key-123 (see test-spike-local.sh). Replays the
Connect HTTPS request flow from the AWS sample events, with the role
values exactly as the AWS docs print them (ROLE_USER), and asserts the
spike's behaviour at each step.

Usage: python3 smoke_test.py [base_url]
Exit code 0 = all checks passed.
"""
import json
import sys
import urllib.request
import urllib.error

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:9000"
EXT = "https://docs.aws.amazon.com/connect/a2a/ext/v1"
EVENT_KEY = f"{EXT}/eventType"
KEY = "test-key-123"
CTX = "ctx-smoke-1"
INSTANCE_ARN = "arn:aws:connect:us-east-1:258032684610:instance/71134274-3650-457c-b614-5f198db32f65"
CONTACT_ARN = INSTANCE_ARN + "/contact/smoke-contact-1"

FIXED_REPLY = (
    "Hello — you've reached the General Support test agent. "
    "This is a controlled test reply from the Gate 0 spike: "
    "I don't look up cases yet, I just prove the connection works. "
    "Please go ahead — I'll answer the same way each time, "
    "and then hand you to a human agent."
)

passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS  {name}")
    else:
        failed += 1
        print(f"FAIL  {name}  {detail}")


def http(method, path, body=None, headers=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, dict(e.headers), json.loads(raw or b"{}")
        except ValueError:
            return e.code, dict(e.headers), {"raw": raw.decode(errors="replace")}


def rpc(req_id, method, params, key=KEY, extra_headers=None):
    headers = {}
    if key is not None:
        headers["Authorization"] = f"Bearer {key}"
    headers["A2A-Extensions"] = EXT
    headers["traceparent"] = "00-4bf92f3577b34da6a3ce929d0e0e4736-b7ad6b7169203331-01"
    headers["tracestate"] = "connect=parentSpanId:12345678-1234-1234-1234-123456789012"
    if extra_headers:
        headers.update(extra_headers)
    return http("POST", "/", {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params},
                headers=headers)


def msg(message_id, context_id, parts, event_type=None, role="ROLE_USER", kind=True):
    m = {"messageId": message_id, "contextId": context_id, "role": role, "parts": parts}
    if kind:
        m["kind"] = "message"
    if event_type:
        m["metadata"] = {EVENT_KEY: event_type}
        m["extensions"] = [EXT]
    return {"message": m}


# 1. /ping -----------------------------------------------------------------
status, _, body = http("GET", "/ping")
check("GET /ping -> 200 healthy", status == 200 and body.get("status") == "healthy", str(body))

# 2. Agent card --------------------------------------------------------------
status, _, card = http("GET", "/.well-known/agent-card.json")
check("GET /.well-known/agent-card.json -> 200", status == 200, str(card)[:200])
check("card name/version", card.get("name") == "general-1-spike" and card.get("version") == "0.1.0", str(card)[:200])
check("card declares the Connect extension",
      EXT in [e.get("uri") for e in (card.get("capabilities", {}).get("extensions") or [])],
      str(card.get("capabilities")))
check("card declares apiKey security",
      "apiKey" in (card.get("securitySchemes") or {}), str(card.get("securitySchemes")))
check("card protocol 1.0 / JSONRPC",
      card.get("protocolVersion") == "1.0" and card.get("preferredTransport") == "JSONRPC",
      str({k: card.get(k) for k in ("protocolVersion", "preferredTransport")}))

# 3. Auth: missing + wrong key -> 401 ---------------------------------------
status, _, _ = rpc("auth-1", "message/send",
                   msg("m-x", CTX, [{"kind": "text", "text": "hi"}]), key=None)
check("no bearer token -> 401", status == 401, f"got {status}")
status, _, _ = rpc("auth-2", "message/send",
                   msg("m-x", CTX, [{"kind": "text", "text": "hi"}]), key="wrong-key")
check("wrong bearer token -> 401", status == 401, f"got {status}")

# 4. INIT_SESSION with ROLE_USER (exactly as the AWS samples print it) ------
status, resp_headers, body = rpc("init-1", "message/send", msg(
    "m-init-1", CTX,
    [{"kind": "data", "data": {"initSession": {
        "instanceArn": INSTANCE_ARN,
        "contactArn": CONTACT_ARN,
        "supportedFinishTypes": ["COMPLETE", "ESCALATE"],
        "subscribeToTracingEvents": True,
        "history": [],
    }}}],
    event_type="INIT_SESSION"))
result = body.get("result", {})
check("INIT_SESSION (ROLE_USER) -> 200", status == 200, f"got {status}: {str(body)[:300]}")
check("INIT_SESSION_RESPONSE returned",
      result.get("kind") == "message"
      and result.get("metadata", {}).get(EVENT_KEY) == "INIT_SESSION_RESPONSE"
      and result.get("parts", [{}])[0].get("data", {}).get("initSessionResponse", {}).get("statusCode") == "200",
      str(result)[:400])
check("A2A-Extensions header echoed on the response",
      resp_headers.get("A2A-Extensions") == EXT or resp_headers.get("a2a-extensions") == EXT,
      str(resp_headers))

# 5. CHANNEL_STATE READY -----------------------------------------------------
status, _, body = rpc("chan-1", "message/send", msg(
    "m-chan-1", CTX,
    [{"kind": "data", "data": {"channelState": {"state": "READY"}}}],
    event_type="CHANNEL_STATE"))
result = body.get("result", {})
check("CHANNEL_STATE READY -> 200 + working task",
      status == 200 and result.get("kind") == "task"
      and result.get("status", {}).get("state") == "working",
      f"got {status}: {str(body)[:300]}")

# 6. Turn 1: fixed reply, trace span, terminal completed, NO finish ---------
status, _, body = rpc("turn-1", "message/send", msg(
    "m-turn-1", CTX,
    [{"kind": "text", "text": "Hello, I need help with my case"}],
    role="user"))
result = body.get("result", {})
task_id_1 = result.get("id", "")
artifacts = result.get("artifacts", [])
texts = [p.get("text", "") for a in artifacts for p in a.get("parts", []) if p.get("kind") == "text"]
trace_parts = [p for a in artifacts for p in a.get("parts", [])
               if p.get("kind") == "data" and "tracingSpan" in (p.get("data") or {})]
check("turn 1 -> 200 + completed task",
      status == 200 and result.get("kind") == "task"
      and result.get("status", {}).get("state") == "completed",
      f"got {status}: {str(body)[:300]}")
check("turn 1 reply is exactly the fixed reply", texts == [FIXED_REPLY], str(texts)[:300])
check("turn 1 carries a TRACING_SPAN artifact", len(trace_parts) == 1,
      f"artifacts: {str(artifacts)[:300]}")
if trace_parts:
    spans = trace_parts[0]["data"]["tracingSpan"]["otlp"]["resourceSpans"][0]["scopeSpans"][0]["spans"]
    names = [s["name"] for s in spans]
    check("trace has invoke_agent root + chat child spans",
          names == [f"invoke_agent general-1-spike", "chat us.anthropic.claude-haiku-4-5-20251001-v1:0"],
          str(names))
    check("trace adopts Connect's traceId",
          spans[0]["traceId"] == "4bf92f3577b34da6a3ce929d0e0e4736",
          spans[0]["traceId"])
check("turn 1 has NO finish (FINISH is not per-turn)",
      not (result.get("status", {}).get("message") or {}).get("parts"),
      str(result.get("status"))[:300])

# 7. Re-INIT on the same contextId (chat / reconnect behaviour) -------------
status, _, body = rpc("init-2", "message/send", msg(
    "m-init-2", CTX,
    [{"kind": "data", "data": {"initSession": {
        "instanceArn": INSTANCE_ARN, "contactArn": CONTACT_ARN,
        "supportedFinishTypes": ["COMPLETE", "ESCALATE"],
        "subscribeToTracingEvents": True, "history": [],
    }}}],
    event_type="INIT_SESSION"))
result = body.get("result", {})
check("re-INIT on same contextId -> INIT_SESSION_RESPONSE again",
      result.get("metadata", {}).get(EVENT_KEY) == "INIT_SESSION_RESPONSE",
      str(result)[:300])

# 8. Turn 2: FINISH ESCALATE --------------------------------------------------
status, _, body = rpc("turn-2", "message/send", msg(
    "m-turn-2", CTX,
    [{"kind": "text", "text": "Yes, I want to speak to a person"}],
    role="user"))
result = body.get("result", {})
finish = None
smsg = (result.get("status", {}) or {}).get("message") or {}
for p in smsg.get("parts", []):
    if p.get("kind") == "data" and "finish" in (p.get("data") or {}):
        finish = p["data"]["finish"]
check("turn 2 -> completed task with FINISH ESCALATE",
      result.get("status", {}).get("state") == "completed"
      and finish is not None and finish.get("type") == "ESCALATE"
      and "human agent" in finish.get("reason", ""),
      f"finish={finish} status={str(result.get('status'))[:300]}")

# 9. tasks/get returns the turn-1 task ---------------------------------------
status, _, body = rpc("get-1", "tasks/get", {"id": task_id_1})
result = body.get("result", {})
check("tasks/get returns the turn-1 task",
      status == 200 and result.get("id") == task_id_1, f"got {status}: {str(body)[:300]}")

# 10. Message WITHOUT a "kind" field (SDK leniency probe) --------------------
status, _, body = rpc("init-3", "message/send", msg(
    "m-init-3", "ctx-smoke-2",
    [{"kind": "data", "data": {"initSession": {
        "instanceArn": INSTANCE_ARN, "contactArn": CONTACT_ARN,
        "supportedFinishTypes": ["COMPLETE", "ESCALATE"],
        "subscribeToTracingEvents": True, "history": [],
    }}}],
    event_type="INIT_SESSION", kind=False))
result = body.get("result", {})
check("INIT_SESSION without message.kind still accepted",
      result.get("metadata", {}).get(EVENT_KEY) == "INIT_SESSION_RESPONSE",
      str(result)[:300])

# 11. DTMF input is treated as a turn ---------------------------------------
status, _, body = rpc("dtmf-1", "message/send", msg(
    "m-dtmf-1", "ctx-smoke-2",
    [{"kind": "data", "data": {"dtmfInputComplete": {
        "inputString": "1234", "terminationReason": "END_CHARACTER"}}}],
    event_type="DTMF_INPUT_COMPLETE"))
result = body.get("result", {})
texts = [p.get("text", "") for a in result.get("artifacts", []) for p in a.get("parts", []) if p.get("kind") == "text"]
check("DTMF_INPUT_COMPLETE -> fixed reply turn",
      result.get("status", {}).get("state") == "completed" and texts == [FIXED_REPLY],
      f"got {str(body)[:300]}")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
