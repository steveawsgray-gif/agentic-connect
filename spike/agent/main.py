#!/usr/bin/env python3
"""
Gate 0 spike agent — Project #3 (agentic-connect), Generation 1.

Purpose
-------
Prove the A2A seam between Amazon Connect Customer and a custom Bedrock
agent hosted on AgentCore Runtime, with the smallest possible agent.
The agent has NO tools, NO case lookup, NO memory. It answers every
customer turn with ONE fixed, controlled reply, sends the mandatory
TRACING_SPAN for the turn, and on the second turn ends the collaboration
with FINISH / ESCALATE so the contact returns to a human in General
Support. If this seam cannot be proved, the build stops at Gate 0.

Contract sources (read 2026-11-24; see spike-draft README for links)
----------------------------------------------------------------------
- Connect admin guide, "Build an external AI agent server"
  (a2a-voice.html): session order, turn lifecycle, FINISH, errors.
- "A2A protocol contract for external AI agents"
  (a2a-developer-guide.html): extension URI, headers, tracing wire format.
- "Set up an external AI agent integration" (a2a-setup-external.html):
  API-key storage, AppIntegrations registration, collaborator config.
- AgentCore dev guide, "Deploy A2A servers in AgentCore Runtime"
  (runtime-a2a.html): port 9000, root path, invocations URL, /ping.
- a2a-sdk 0.3.26 + strands-agents 1.57.2 (pinned in requirements.txt).

Why NOT serve_a2a / StrandsA2AExecutor
----------------------------------------
The AgentCore SDK's serve_a2a() and Strands' StrandsA2AExecutor treat
every incoming message as a plain user turn. Connect's INIT_SESSION,
CHANNEL_STATE, INTERRUPTION and ERROR events are Connect-extension
messages carried in A2A metadata — a generic executor would feed them
to the model as user text. This spike therefore uses the raw a2a-sdk
(A2AStarletteApplication + DefaultRequestHandler) with a custom
AgentExecutor that dispatches on the extension eventType. The model
itself is still a plain Strands Agent (Bedrock Haiku 4.5, temperature 0,
no tools); only the A2A plumbing is hand-rolled.

Deliberate deviations / UNVERIFIED items are marked UNVERIFIED below
and collected in the spike-draft README.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import boto3
import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps.jsonrpc import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentExtension,
    AgentSkill,
    Artifact,
    DataPart,
    Message,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from starlette.responses import JSONResponse
from strands import Agent
from strands.models import BedrockModel

# ---------------------------------------------------------------------------
# Connect A2A extension constants (verified against the AWS contract page,
# "A2A protocol contract for external AI agents", 2026-11-24).
# ---------------------------------------------------------------------------
EXTENSION_URI = "https://docs.aws.amazon.com/connect/a2a/ext/v1"
EVENT_TYPE_KEY = f"{EXTENSION_URI}/eventType"

# Event types Connect sends / expects (metadata key above).
EV_INIT_SESSION = "INIT_SESSION"
EV_INIT_SESSION_RESPONSE = "INIT_SESSION_RESPONSE"
EV_CHANNEL_STATE = "CHANNEL_STATE"
EV_TEXT_RESPONSE_CHUNK = "TEXT_RESPONSE_CHUNK"
EV_TRACING_SPAN = "TRACING_SPAN"
EV_FINISH = "FINISH"
EV_INTERRUPTION = "INTERRUPTION"
EV_ERROR = "ERROR"
EV_DTMF_INPUT_COMPLETE = "DTMF_INPUT_COMPLETE"

AGENT_NAME = "general-1-spike"
AGENT_VERSION = "0.1.0"

# The one and only thing this agent ever says to a caller. Fixed on
# purpose: the spike proves the seam, not the agent's judgement. The
# model is still invoked (see _invoke_model) so the Bedrock path from
# inside the Runtime container is exercised; its output is logged and
# DISCARDED — the fixed reply is what goes to the caller.
FIXED_REPLY = (
    "Hello — you've reached the General Support test agent. "
    "This is a controlled test reply from the Gate 0 spike: "
    "I don't look up cases yet, I just prove the connection works. "
    "Please go ahead — I'll answer the same way each time, "
    "and then hand you to a human agent."
)

FINISH_REASON = (
    "Spike test complete: handing the caller to a human agent "
    "in General Support."
)

# Silence re-prompt payload Connect sends after extended silence.
SILENCE_TEXT = "<EMPTY_USER_INPUT>"

# ---------------------------------------------------------------------------
# Logging — one JSON object per line on stdout (AgentCore Observability
# picks up container stdout into CloudWatch). Authorization values are
# NEVER logged; only present/absent.
# ---------------------------------------------------------------------------
logger = logging.getLogger("gate0-spike")
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(handler)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
logger.propagate = False


def log(event: str, **fields: Any) -> None:
    record = {"event": event, "agent": AGENT_NAME, **fields}
    logger.info(json.dumps(record, default=str))


# ---------------------------------------------------------------------------
# Configuration (environment only — no secrets in code, no secrets in files).
# ---------------------------------------------------------------------------
def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


AWS_REGION = _env("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = _env(
    "BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
)
# AgentCore Runtime injects AGENTCORE_RUNTIME_URL into the container at
# deploy time (the public invocations URL). Locally it defaults to the
# loopback address so the card is still fetchable in the smoke test.
AGENTCORE_RUNTIME_URL = _env("AGENTCORE_RUNTIME_URL", "http://localhost:9000")
API_KEY_SECRET_ARN = _env("AGENT_API_KEY_SECRET_ARN", "")
SPIKE_NO_MODEL = _env("SPIKE_NO_MODEL", "0") == "1"


def load_api_key() -> str:
    """Load the Connect API key.

    Production path: read it from Secrets Manager (ARN in
    AGENT_API_KEY_SECRET_ARN). The secret holds either the raw key as
    the secret string, or a JSON object with an "api_key" field.
    Local-test path: SPIKE_DEV_API_KEY (never set in AWS, never
    committed). Fails fast if neither is available — an agent that
    cannot authenticate its callers must not start.
    """
    dev_key = _env("SPIKE_DEV_API_KEY", "")
    if API_KEY_SECRET_ARN:
        client = boto3.client("secretsmanager", region_name=AWS_REGION)
        resp = client.get_secret_value(SecretId=API_KEY_SECRET_ARN)
        raw = resp.get("SecretString", "")
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "api_key" in parsed:
                return str(parsed["api_key"])
        except json.JSONDecodeError:
            pass
        return raw
    if dev_key:
        log("auth_dev_key_in_use",
            warning="SPIKE_DEV_API_KEY is set — local testing only, never in AWS")
        return dev_key
    raise RuntimeError(
        "No API key available: set AGENT_API_KEY_SECRET_ARN "
        "(production) or SPIKE_DEV_API_KEY (local test only)."
    )


API_KEY = load_api_key()
API_KEY_SHA256 = hashlib.sha256(API_KEY.encode()).hexdigest()[:12]


def _check_bearer(authorization: Optional[str]) -> bool:
    """Constant-time check of `Authorization: Bearer <apiKey>`."""
    if not authorization:
        return False
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(token.strip(), API_KEY)


# ---------------------------------------------------------------------------
# ASGI middleware — runs BEFORE the a2a-sdk parses the request body.
# Two jobs, both required by the Connect contract:
#   1. Bearer check. Connect sends the API key as a bearer token on
#      every HTTPS request and on the WebSocket upgrade. The Connect
#      admin guide prescribes exactly this: "Check the bearer token on
#      each incoming connection or request, and reject the connection
#      or request if the token doesn't match the API key that you
#      issued." Invalid key -> HTTP 401 (Connect does not retry 401).
#   2. Role normalisation (UNVERIFIED wire detail). The AWS sample
#      payloads use "role": "ROLE_USER" / "ROLE_AGENT", but a2a-sdk
#      0.3.26 only accepts "user" / "agent" and rejects ROLE_* with a
#      pydantic validation error (verified locally 2026-11-24). It is
#      not established whether Connect actually sends ROLE_* on the
#      wire or whether the docs samples use stale naming — so the
#      middleware rewrites ROLE_USER -> user and ROLE_AGENT -> agent
#      wherever a "role" field carries them, and passes everything
#      else through untouched. If Connect already sends user/agent,
#      this is a no-op.
# The middleware also echoes the A2A-Extensions header back on
# responses ("Echo it back to confirm activation", contract page).
# ---------------------------------------------------------------------------
class ConnectCompatMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")

        # Card / health endpoints are unauthenticated GETs.
        if method == "GET":
            await self.app(scope, receive, send)
            return

        if method != "POST" or path != "/":
            await self.app(scope, receive, send)
            return

        # Read the whole body (JSON-RPC over HTTPS: one frame per request).
        body = b""
        more = True
        while more:
            message = await receive()
            body += message.get("body", b"")
            more = message.get("more_body", False)

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        extensions_header = headers.get("a2a-extensions", "")

        async def send_wrapper(out_message):
            # Echo the extension activation header on the response.
            if out_message["type"] == "http.response.start" and extensions_header:
                out_headers = list(out_message.get("headers", []))
                out_headers.append(
                    (b"a2a-extensions", EXTENSION_URI.encode())
                )
                out_message = {**out_message, "headers": out_headers}
            await send(out_message)

        # 1. Bearer check first — before any parsing.
        if not _check_bearer(headers.get("authorization")):
            log("auth_rejected", path=path,
                authorization_present="authorization" in headers)
            payload = json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32000, "message": "Unauthorized: invalid API key"},
            }).encode()
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(payload)).encode())],
            })
            await send({"type": "http.response.body", "body": payload})
            return

        # 2. Role normalisation on the JSON body, if it parses.
        new_body = body
        try:
            parsed = json.loads(body.decode("utf-8")) if body else None
            if _normalize_roles(parsed):
                new_body = json.dumps(parsed).encode("utf-8")
                log("role_normalized")
        except (ValueError, UnicodeDecodeError):
            pass  # Not JSON — leave the body alone; the SDK will error.

        async def receive_replay():
            nonlocal new_body
            if new_body is None:
                return {"type": "http.request", "body": b"", "more_body": False}
            chunk, new_body = new_body, None
            return {"type": "http.request", "body": chunk, "more_body": False}

        await self.app(scope, receive_replay, send_wrapper)


def _normalize_roles(node: Any) -> bool:
    """Rewrite ROLE_USER/ROLE_AGENT -> user/agent in any "role" field.

    Returns True if anything changed. Only touches the value of a key
    literally named "role"; all other strings are left alone.
    """
    changed = False
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "role" and value == "ROLE_USER":
                node[key] = "user"
                changed = True
            elif key == "role" and value == "ROLE_AGENT":
                node[key] = "agent"
                changed = True
            else:
                changed = _normalize_roles(value) or changed
    elif isinstance(node, list):
        for item in node:
            changed = _normalize_roles(item) or changed
    return changed


# ---------------------------------------------------------------------------
# Session state — one record per Connect contextId. Short-term only:
# the record lives for the session and is dropped on cancel / finish.
# Gen-1 keeps the same rule (short-term session memory only, redline 4).
# ---------------------------------------------------------------------------
@dataclass
class SpikeSession:
    context_id: str
    contact_arn: str = ""
    instance_arn: str = ""
    supported_finish_types: list = field(default_factory=lambda: ["COMPLETE", "ESCALATE"])
    subscribe_to_tracing: bool = True
    contact_channel: str = ""
    channel_ready: bool = False
    turns: int = 0
    last_task_id: str = ""


def _event_type(message: Optional[Message]) -> Optional[str]:
    """The Connect event type, from message metadata.

    The contract puts it under the key
    "https://docs.aws.amazon.com/connect/a2a/ext/v1/eventType".
    Falls back to any metadata key ending in "/eventType" so a
    differently-namespaced sender still dispatches.
    """
    if message is None or not message.metadata:
        return None
    if EVENT_TYPE_KEY in message.metadata:
        return str(message.metadata[EVENT_TYPE_KEY])
    for key, value in message.metadata.items():
        if key.endswith("/eventType"):
            return str(value)
    return None


def _unwrap_part(part: Any) -> Any:
    """a2a-sdk 0.3.x models Message parts as Part RootModels — the real
    TextPart / FilePart / DataPart lives in .root."""
    return getattr(part, "root", part)


def _data_part(message: Optional[Message], key: str) -> dict:
    """First data part whose `data` dict contains `key`, else {}."""
    if message is None:
        return {}
    for part in message.parts or []:
        part = _unwrap_part(part)
        if isinstance(part, DataPart) and isinstance(part.data, dict) and key in part.data:
            value = part.data[key]
            return value if isinstance(value, dict) else {"value": value}
    return {}


def _has_audio_part(message: Optional[Message]) -> bool:
    if message is None:
        return False
    for part in message.parts or []:
        kind = getattr(_unwrap_part(part), "kind", "")
        if kind not in ("text", "data"):
            return True
    return False


def _parse_traceparent(value: Optional[str]) -> tuple[str, Optional[str], str]:
    """W3C traceparent -> (trace_id, parent_span_id, flags).

    Falls back to a fresh trace id when the header is absent or
    malformed. (Whether the Runtime proxy forwards Connect's
    traceparent to the container is UNVERIFIED — see README risk #2.
    The draft logs what it actually received at session start, so the
    live run settles it.)
    """
    if value:
        bits = value.strip().split("-")
        if len(bits) == 4 and len(bits[1]) == 32 and len(bits[2]) == 16:
            return bits[1], bits[2], bits[3]
    return uuid.uuid4().hex, None, "01"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nano(epoch_seconds: float) -> str:
    return str(int(epoch_seconds * 1_000_000_000))


# ---------------------------------------------------------------------------
# Tracing — TRACING_SPAN per turn (MANDATORY: Connect disables endpoints
# that do not send the required trace data).
# Wire format (contract page, "Tracing"): an artifactUpdate carrying a
# data part {"tracingSpan": {"otlp": {"resourceSpans": [...]}}}, emitted
# AFTER the response artifact and BEFORE the terminal status update,
# on the turn's taskId. Span names follow the OTEL GenAI conventions:
# root "invoke_agent <agentName>" (SERVER), child "chat <model>" (CLIENT).
# Span events are "aws.connect.span.message" with role/type/participant/
# content attributes. Required on every span: traceId, spanId, name,
# startTimeUnixNano, endTimeUnixNano. The trace context is adopted from
# Connect's traceparent when present (see _parse_traceparent).
# ---------------------------------------------------------------------------
def _build_tracing_span(
    *,
    session: SpikeSession,
    task_id: str,
    trace_id: str,
    parent_span_id: Optional[str],
    trace_flags: str,
    caller_text: str,
    turn_started: float,
    model_started: float,
    model_finished: float,
    turn_finished: float,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    failed: bool = False,
    error_message: str = "",
) -> dict:
    root_span_id = uuid.uuid4().hex[:16]
    chat_span_id = uuid.uuid4().hex[:16]
    total_tokens = (
        (input_tokens or 0) + (output_tokens or 0)
        if input_tokens is not None or output_tokens is not None
        else None
    )

    def kv(key: str, value: Any) -> dict:
        if isinstance(value, bool):
            return {"key": key, "value": {"boolValue": value}}
        if isinstance(value, int):
            return {"key": key, "value": {"intValue": str(value)}}
        return {"key": key, "value": {"stringValue": str(value)}}

    root_attributes = [
        kv("gen_ai.agent.name", AGENT_NAME),
        kv("gen_ai.operation.name", "invoke_agent"),
        kv("gen_ai.request.model", BEDROCK_MODEL_ID),
    ]
    if total_tokens is not None:
        root_attributes.append(kv("aws.connect.usage.total_tokens", total_tokens))
    if failed:
        root_attributes.append(kv("aws.connect.error.type", "SPIKE_TURN_FAILED"))

    chat_attributes = [
        kv("gen_ai.agent.name", AGENT_NAME),
        kv("gen_ai.operation.name", "chat"),
        kv("gen_ai.request.model", BEDROCK_MODEL_ID),
    ]
    if input_tokens is not None:
        chat_attributes.append(kv("gen_ai.usage.input_tokens", input_tokens))
    if output_tokens is not None:
        chat_attributes.append(kv("gen_ai.usage.output_tokens", output_tokens))

    root_span = {
        "traceId": trace_id,
        "spanId": root_span_id,
        "name": f"invoke_agent {AGENT_NAME}",
        "kind": 2,  # SERVER
        "startTimeUnixNano": _nano(turn_started),
        "endTimeUnixNano": _nano(turn_finished),
        "attributes": root_attributes,
        "events": [
            {
                "timeUnixNano": _nano(turn_started),
                "name": "aws.connect.span.message",
                "attributes": [
                    kv("role", "input"),
                    kv("type", "TEXT_MESSAGE"),
                    kv("participant", "user"),
                    kv("content", caller_text),
                ],
            },
            {
                "timeUnixNano": _nano(turn_finished),
                "name": "aws.connect.span.message",
                "attributes": [
                    kv("role", "output"),
                    kv("type", "TEXT_MESSAGE"),
                    kv("participant", "agent"),
                    kv("content", FIXED_REPLY),
                ],
            },
        ],
        "status": {"code": 2, "message": error_message} if failed else {"code": 1},
    }
    if parent_span_id:
        root_span["parentSpanId"] = parent_span_id

    chat_span = {
        "traceId": trace_id,
        "spanId": chat_span_id,
        "parentSpanId": root_span_id,
        "name": f"chat {BEDROCK_MODEL_ID}",
        "kind": 3,  # CLIENT
        "startTimeUnixNano": _nano(model_started),
        "endTimeUnixNano": _nano(model_finished),
        "attributes": chat_attributes,
        "status": {"code": 2, "message": error_message} if failed else {"code": 1},
    }

    return {
        "tracingSpan": {
            "otlp": {
                "resourceSpans": [
                    {
                        "resource": {
                            "attributes": [
                                kv("service.name", AGENT_NAME),
                                kv("agent.name", AGENT_NAME),
                            ]
                        },
                        "scopeSpans": [
                            {
                                "scope": {"name": AGENT_NAME, "version": AGENT_VERSION},
                                "spans": [root_span, chat_span],
                            }
                        ],
                    }
                ]
            },
            "spanContext": {
                "traceId": trace_id,
                "spanId": root_span_id,
                "traceFlags": trace_flags,
                "isRemote": False,
            },
        }
    }


# ---------------------------------------------------------------------------
# The executor — dispatches on the Connect extension eventType.
# ---------------------------------------------------------------------------
class SpikeExecutor(AgentExecutor):
    def __init__(self) -> None:
        self.sessions: dict[str, SpikeSession] = {}
        self._agent: Optional[Agent] = None

    # -- Strands agent (lazy: built on first turn so a bad model config
    #    doesn't fail server startup; SPIKE_NO_MODEL skips it entirely).
    def _get_agent(self) -> Agent:
        if self._agent is None:
            self._agent = Agent(
                name=AGENT_NAME,
                description=(
                    "Gate 0 spike agent for Project #3: one fixed reply, "
                    "no tools, no memory. Proves the Connect/A2A seam."
                ),
                model=BedrockModel(
                    model_id=BEDROCK_MODEL_ID,
                    region_name=AWS_REGION,
                    temperature=0,
                    max_tokens=200,
                ),
                system_prompt=(
                    "You are the General Support test agent for a Gate 0 "
                    "spike. Reply with exactly this sentence and nothing "
                    "else: " + FIXED_REPLY
                ),
                tools=[],
            )
        return self._agent

    async def _invoke_model(self, user_text: str) -> tuple[str, float, float, Optional[int], Optional[int]]:
        """Call the model; return (text, started, finished, in_tok, out_tok).

        The model output is a liveness probe only — the spike always
        sends FIXED_REPLY to the caller. A model that deviates from the
        fixed reply is logged, not surfaced: the spike's contract is
        the fixed reply.
        """
        if SPIKE_NO_MODEL:
            now = time.time()
            return "", now, now, None, None
        agent = self._get_agent()
        started = time.time()
        result = await asyncio.to_thread(agent, user_text)
        finished = time.time()
        text = ""
        in_tok = out_tok = None
        try:
            content = result.message.get("content", []) if isinstance(result.message, dict) else []
            text = "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and "text" in block
            )
        except Exception:
            pass
        try:
            usage = getattr(result.metrics, "accumulated_usage", {}) or {}
            in_tok = usage.get("inputTokens")
            out_tok = usage.get("outputTokens")
        except Exception:
            pass
        if text.strip() != FIXED_REPLY.strip():
            log("model_deviated_from_fixed_reply",
                model_text=text[:200], input_tokens=in_tok, output_tokens=out_tok)
        return text, started, finished, in_tok, out_tok

    # -- A2A plumbing ------------------------------------------------------
    def _session(self, context: RequestContext) -> SpikeSession:
        context_id = context.context_id or uuid.uuid4().hex
        session = self.sessions.get(context_id)
        if session is None:
            session = SpikeSession(context_id=context_id)
            self.sessions[context_id] = session
        return session

    @staticmethod
    def _headers(context: RequestContext) -> dict:
        """Inbound HTTP headers, via the SDK's DefaultCallContextBuilder
        (it copies every request header into call_context.state)."""
        call_context = getattr(context, "call_context", None)
        state = getattr(call_context, "state", None) or {}
        headers = state.get("headers", {}) or {}
        return {str(k).lower(): str(v) for k, v in headers.items()}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        message = context.message
        event_type = _event_type(message)
        session = self._session(context)
        headers = self._headers(context)

        if event_type == EV_INIT_SESSION:
            await self._handle_init_session(context, event_queue, session, headers)
        elif event_type == EV_CHANNEL_STATE:
            await self._handle_channel_state(context, event_queue, session)
        elif event_type == EV_INTERRUPTION:
            # Text channel: nothing is streaming, so there is nothing
            # to stop. Logged; the turn in flight (if any) is short and
            # completes. Production audio handling must discard buffered
            # output and open a fresh artifactId — out of spike scope.
            log("interruption_received", context_id=session.context_id,
                note="spike has no in-flight output to discard")
        elif event_type == EV_ERROR:
            # Informational only per the contract — no state change.
            log("connect_error_event", context_id=session.context_id,
                metadata=(message.metadata if message else None))
        elif event_type == EV_DTMF_INPUT_COMPLETE:
            dtmf = _data_part(message, "dtmfInputComplete")
            digit_string = str(dtmf.get("inputString", ""))
            await self._handle_turn(
                context, event_queue, session, headers,
                caller_text=digit_string, via="dtmf",
            )
        elif event_type in (None,):
            await self._handle_turn(
                context, event_queue, session, headers,
                caller_text=context.get_user_input(), via="text",
            )
        else:
            log("unknown_event_type", context_id=session.context_id,
                event_type=event_type)
            await self._fail_turn(
                context, event_queue, session,
                error_code=400, error_category="BAD_REQUEST",
                reason=f"Unsupported Connect event type: {event_type}",
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or ""
        if task_id:
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context.context_id or "",
                status=TaskStatus(state=TaskState.canceled, timestamp=_now_iso()),
                final=True,
            ))
        if context.context_id in self.sessions:
            del self.sessions[context.context_id]
        log("session_cancelled", context_id=context.context_id, task_id=task_id)

    # -- Event handlers ----------------------------------------------------
    async def _handle_init_session(
        self, context: RequestContext, event_queue: EventQueue,
        session: SpikeSession, headers: dict,
    ) -> None:
        init = _data_part(context.message, "initSession")
        is_reinit = session.turns > 0 or session.contact_arn != ""
        if not is_reinit:
            session.contact_arn = str(init.get("contactArn", ""))
            session.instance_arn = str(init.get("instanceArn", ""))
            session.supported_finish_types = list(
                init.get("supportedFinishTypes", ["COMPLETE", "ESCALATE"])
            )
            session.subscribe_to_tracing = bool(
                init.get("subscribeToTracingEvents", True)
            )
            contact_context = init.get("contactContext", {}) or {}
            session.contact_channel = str(contact_context.get("channel", ""))
            # Evidence for the two UNVERIFIED header questions: log WHAT
            # actually arrived (presence only — never values).
            log("init_session",
                context_id=session.context_id,
                reinit=False,
                contact_arn=session.contact_arn,
                channel=session.contact_channel,
                supported_finish_types=session.supported_finish_types,
                subscribe_to_tracing=session.subscribe_to_tracing,
                history_turns=len(init.get("history", []) or []),
                headers_seen={
                    "authorization": "authorization" in headers,
                    "traceparent": "traceparent" in headers,
                    "tracestate": "tracestate" in headers,
                    "a2a-extensions": "a2a-extensions" in headers,
                },
                tracestate_connect=headers.get("tracestate", "")[:80])
        else:
            # Chat re-sends INIT_SESSION on every message, and a voice
            # reconnect re-sends it with the same contextId. Keep the
            # turn counter and session state — only refresh contact info.
            log("init_session_reinit", context_id=session.context_id,
                turns_so_far=session.turns)

        response = Message(
            role=Role.agent,
            message_id=uuid.uuid4().hex,
            context_id=session.context_id,
            parts=[DataPart(data={"initSessionResponse": {"statusCode": "200"}})],
            metadata={EVENT_TYPE_KEY: EV_INIT_SESSION_RESPONSE},
            extensions=[EXTENSION_URI],
        )
        await event_queue.enqueue_event(response)
        log("init_session_response_sent", context_id=session.context_id)

    async def _handle_channel_state(
        self, context: RequestContext, event_queue: EventQueue,
        session: SpikeSession,
    ) -> None:
        # The contract's sample shape is {"channelState": {"state": ...}},
        # but the exact data-part key is UNVERIFIED against a live
        # Connect send — so scan every data part for a "state" value
        # (nested under "channelState", or top-level) and log what was
        # actually received. A shape mismatch shows up in the log as
        # state="" instead of silently gating the channel forever.
        channel_state = ""
        if context.message is not None:
            for part in context.message.parts or []:
                part = _unwrap_part(part)
                if isinstance(part, DataPart) and isinstance(part.data, dict):
                    nested = part.data.get("channelState")
                    if isinstance(nested, dict) and "state" in nested:
                        channel_state = str(nested["state"])
                    elif "state" in part.data:
                        channel_state = str(part.data["state"])
                    if channel_state:
                        break
        if channel_state == "READY":
            session.channel_ready = True
            log("channel_ready", context_id=session.context_id)
        else:
            log("channel_state_other", context_id=session.context_id,
                state=channel_state)
        # UNVERIFIED: the AWS docs publish no sample response for
        # CHANNEL_STATE. A non-final "working" status update is the
        # conservative answer — it acknowledges receipt without
        # closing the task Connect will poll for the turn.
        await event_queue.enqueue_event(TaskStatusUpdateEvent(
            task_id=context.task_id or uuid.uuid4().hex,
            context_id=session.context_id,
            status=TaskStatus(state=TaskState.working, timestamp=_now_iso()),
            final=False,
        ))

    async def _handle_turn(
        self, context: RequestContext, event_queue: EventQueue,
        session: SpikeSession, headers: dict,
        *, caller_text: str, via: str,
    ) -> None:
        turn_started = time.time()
        task_id = context.task_id or uuid.uuid4().hex
        session.last_task_id = task_id
        session.turns += 1
        turn_no = session.turns

        if not session.channel_ready:
            # Contract: gate output on CHANNEL_STATE READY. The spike
            # logs the violation and answers anyway (leniency keeps a
            # sequencing quirk from failing the whole live test); the
            # log line is the evidence for the verification table.
            log("turn_before_channel_ready", context_id=session.context_id,
                turn=turn_no, via=via)

        if _has_audio_part(context.message):
            await self._fail_turn(
                context, event_queue, session, task_id=task_id,
                error_code=400, error_category="BAD_REQUEST",
                reason="Spike agent accepts text turns only (audioStreamingEnabled=false).",
            )
            return
        if not caller_text.strip():
            await self._fail_turn(
                context, event_queue, session, task_id=task_id,
                error_code=400, error_category="BAD_REQUEST",
                reason="Empty turn: no text input received.",
            )
            return

        # Trace context: adopt Connect's propagated traceparent when the
        # Runtime proxy forwarded it; otherwise start a fresh trace.
        trace_id, parent_span_id, trace_flags = _parse_traceparent(
            headers.get("traceparent")
        )

        model_text, model_started, model_finished, in_tok, out_tok = (
            await self._invoke_model(caller_text)
        )
        turn_finished = time.time()
        latency_ms = round((turn_finished - turn_started) * 1000, 1)

        # 1. Response artifact — one partial but complete message, closed.
        await event_queue.enqueue_event(TaskArtifactUpdateEvent(
            task_id=task_id,
            context_id=session.context_id,
            artifact=Artifact(
                artifact_id=f"spike-reply-{turn_no}",
                name="spike-reply",
                parts=[TextPart(text=FIXED_REPLY)],
                metadata={EVENT_TYPE_KEY: EV_TEXT_RESPONSE_CHUNK},
            ),
            append=False,
            last_chunk=True,
        ))

        # 2. TRACING_SPAN — mandatory, after the response, before the
        #    terminal status update.
        if session.subscribe_to_tracing:
            tracing = _build_tracing_span(
                session=session, task_id=task_id,
                trace_id=trace_id, parent_span_id=parent_span_id,
                trace_flags=trace_flags, caller_text=caller_text,
                turn_started=turn_started, model_started=model_started,
                model_finished=model_finished, turn_finished=turn_finished,
                input_tokens=in_tok, output_tokens=out_tok,
            )
            await event_queue.enqueue_event(TaskArtifactUpdateEvent(
                task_id=task_id,
                context_id=session.context_id,
                artifact=Artifact(
                    artifact_id=f"trace-{turn_no}",
                    name="spike-trace",
                    parts=[DataPart(data=tracing)],
                    metadata={EVENT_TYPE_KEY: EV_TRACING_SPAN},
                ),
                append=False,
                last_chunk=True,
            ))

        # 3. Terminal status update. FINISH is NOT per-turn (contract:
        #    "Send FINISH only when your agent is done with the
        #    conversation"). The spike's script: turn 1 completes
        #    without FINISH; turn 2 ends the collaboration with FINISH
        #    ESCALATE (only if ESCALATE is in supportedFinishTypes).
        finish_type = None
        if turn_no >= 2 and "ESCALATE" in session.supported_finish_types:
            finish_type = "ESCALATE"
        elif turn_no >= 2 and "COMPLETE" in session.supported_finish_types:
            finish_type = "COMPLETE"

        status_message = None
        if finish_type:
            status_message = Message(
                role=Role.agent,
                message_id=uuid.uuid4().hex,
                context_id=session.context_id,
                parts=[DataPart(data={
                    "finish": {"type": finish_type, "reason": FINISH_REASON}
                })],
                metadata={EVENT_TYPE_KEY: EV_FINISH},
                extensions=[EXTENSION_URI],
            )
        await event_queue.enqueue_event(TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=session.context_id,
            status=TaskStatus(
                state=TaskState.completed,
                timestamp=_now_iso(),
                message=status_message,
            ),
            final=True,
        ))

        log("turn_complete", context_id=session.context_id, task_id=task_id,
            turn=turn_no, via=via, latency_ms=latency_ms,
            finish=finish_type, trace_id=trace_id,
            model_input_tokens=in_tok, model_output_tokens=out_tok)

        if finish_type:
            # After FINISH, no further messages on the session.
            self.sessions.pop(session.context_id, None)

    async def _fail_turn(
        self, context: RequestContext, event_queue: EventQueue,
        session: SpikeSession, *, task_id: str = "",
        error_code: int, error_category: str, reason: str,
    ) -> None:
        """Terminal TASK_STATE_FAILED with the structured error Connect
        consumes. Per the contract this ends the COLLABORATION (not
        just the turn) and the contact returns to the flow's Error
        branch — which is the correct, safe failure for a spike."""
        task_id = task_id or context.task_id or uuid.uuid4().hex
        error_message = Message(
            role=Role.agent,
            message_id=uuid.uuid4().hex,
            context_id=session.context_id,
            parts=[DataPart(data={
                "error": {
                    "errorCode": error_code,
                    "errorReason": reason,
                    "errorCategory": error_category,
                }
            })],
        )
        await event_queue.enqueue_event(TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=session.context_id,
            status=TaskStatus(
                state=TaskState.failed,
                timestamp=_now_iso(),
                message=error_message,
            ),
            final=True,
        ))
        log("turn_failed", context_id=session.context_id, task_id=task_id,
            error_code=error_code, error_category=error_category,
            reason=reason)


# ---------------------------------------------------------------------------
# Agent Card + app assembly.
# ---------------------------------------------------------------------------
def build_agent_card() -> AgentCard:
    return AgentCard(
        name=AGENT_NAME,
        description=(
            "Gate 0 spike agent for Project #3 (agentic-connect): proves "
            "the Connect Customer / AgentCore Runtime A2A seam with one "
            "fixed reply. No tools, no case lookup, no memory."
        ),
        url=AGENTCORE_RUNTIME_URL,
        version=AGENT_VERSION,
        provider={
            "organization": "Steven Gray — Project #3 portfolio demo",
            "url": "https://github.com/steveawsgray-gif/agentic-connect",
        },
        protocol_version="1.0",
        preferred_transport="JSONRPC",
        capabilities=AgentCapabilities(
            streaming=True,
            push_notifications=False,
            state_transition_history=False,
            # a2a-sdk models extensions as AgentExtension objects
            # (uri is the required field); the URI is the Connect
            # extension URI from the contract page.
            extensions=[
                AgentExtension(
                    uri=EXTENSION_URI,
                    description=(
                        "Amazon Connect Customer A2A extensions: "
                        "INIT_SESSION / CHANNEL_STATE / FINISH / "
                        "TRACING_SPAN event types."
                    ),
                    required=True,
                )
            ],
        ),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="gate0-spike",
                name="Gate 0 spike — fixed reply",
                description=(
                    "Answers any text turn with one fixed, controlled "
                    "reply, then hands the caller to a human on the "
                    "second turn. Exists only to prove the A2A seam."
                ),
                tags=["spike", "connect", "a2a", "gate-0"],
                examples=["Hello", "I need a human agent"],
            )
        ],
        security_schemes={
            "apiKey": {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
                "description": (
                    "Connect Customer sends the API key stored in AWS "
                    "Secrets Manager as 'Authorization: Bearer <apiKey>'."
                ),
            }
        },
        security=[{"apiKey": []}],
    )


def create_app():
    card = build_agent_card()
    handler = DefaultRequestHandler(
        agent_executor=SpikeExecutor(),
        task_store=InMemoryTaskStore(),
    )
    app = A2AStarletteApplication(
        agent_card=card,
        http_handler=handler,
    ).build()
    # /ping — the health endpoint AgentCore Runtime expects. (serve_a2a
    # provides this in the SDK sample; the raw A2AStarletteApplication
    # does not, so it is added here.)
    async def ping(request):
        return JSONResponse({"status": "healthy", "agent": AGENT_NAME,
                             "version": AGENT_VERSION})

    app.add_route("/ping", ping, methods=["GET"])
    # Bearer check + ROLE_* normalisation, in front of the SDK app.
    app.add_middleware(ConnectCompatMiddleware)
    log("spike_starting", agent_card_url=AGENTCORE_RUNTIME_URL,
        model=BEDROCK_MODEL_ID, api_key_sha256_prefix=API_KEY_SHA256,
        no_model_mode=SPIKE_NO_MODEL)
    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
