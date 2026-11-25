#!/usr/bin/env bash
# Gate 0 spike — Connect-side registration (steps 2–6 of the README).
#
# What this does, in order (all commands from the AWS Connect setup
# guide, "Set up an external AI agent integration", read 2026-11-24):
#   0. Confirm the Runtime really has NO authorizer configured.
#   1. THE DECISIVE AUTH TEST: curl the Runtime invocations URL with
#      ONLY the API-key bearer (no SigV4). If this 403s, STOP — Gate 0
#      fails on auth (see README risk #1). Nothing after this step
#      can work, and the fallback goes back to Steven.
#   2. Register the A2A server application (AppIntegrations, A2A_SERVER).
#   3. Associate the application with the Connect instance.
#   4. Add the external collaborator (qconnect orchestrator AI agent,
#      handoff mode, text, immediate handoff).
#   5. Update the security profile (allow the application + Access
#      Contact Control Panel) and associate it with the AI agent.
#   6. Publish the new AI agent version.
#
# The API key value is NEVER printed by this script.
#
# Required inputs (environment or terraform outputs):
#   AWS_REGION            default us-east-1
#   CONNECT_INSTANCE_ID   default 71134274-3650-457c-b614-5f198db32f65
#   TF_DIR                terraform directory (default: ../terraform,
#                         relative to this script) — read for outputs.
#   ASSISTANT_ID          qconnect assistant ID (list-assistants if unknown)
#   PROMPT_ID             (optional) orchestration prompt ID — the text
#                         handoff example in the guide does not use one.
#   SECURITY_PROFILE_ID   Connect security profile for the AI agent.
#                         (list-security-profiles if unknown)
#
# If ASSISTANT_ID or SECURITY_PROFILE_ID are unset, the script lists
# what exists and stops with instructions instead of guessing.
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
INSTANCE_ID="${CONNECT_INSTANCE_ID:-71134274-3650-457c-b614-5f198db32f65}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="${TF_DIR:-$SCRIPT_DIR/../terraform}"
OUT_FILE="$SCRIPT_DIR/register-outputs.env"

tfout() { (cd "$TF_DIR" && terraform output -raw "$1"); }

echo "== Gate 0 spike: Connect registration =="
echo "Region: $REGION | Instance: $INSTANCE_ID"

RUNTIME_ARN="$(tfout agent_runtime_arn)"
RUNTIME_ID="$(tfout agent_runtime_id)"
RUNTIME_URL="$(tfout agent_runtime_url)"
SECRET_ARN="$(tfout api_key_secret_arn)"
echo "Runtime ARN: $RUNTIME_ARN"
echo "Runtime URL: $RUNTIME_URL"
echo "Secret ARN:  $SECRET_ARN"

# --- Step 0: authorizer must be null -------------------------------------
echo
echo "-- Step 0: confirm the Runtime has no authorizer configured --"
AUTHZ="$(aws bedrock-agentcore-control get-agent-runtime \
  --agent-runtime-id "$RUNTIME_ID" --region "$REGION" \
  --query 'authorizerConfiguration' --output text)"
echo "authorizerConfiguration: $AUTHZ"
if [ "$AUTHZ" != "None" ] && [ "$AUTHZ" != "null" ] && [ -n "$AUTHZ" ]; then
  echo "STOP: the Runtime has an authorizer configured ($AUTHZ)."
  echo "Connect cannot mint a JWT or SigV4-sign, so this runtime cannot"
  echo "host the spike as a Connect external agent. See README risk #1."
  exit 1
fi

# --- Step 1: decisive auth test ------------------------------------------
echo
echo "-- Step 1: auth test — bearer key only, no SigV4 --"
API_KEY="$(aws secretsmanager get-secret-value --secret-id "$SECRET_ARN" \
  --region "$REGION" --query 'SecretString' --output text)"
CARD_URL="${RUNTIME_URL}.well-known/agent-card.json"
HTTP_CODE="$(curl -s -o /tmp/spike-card.json -w '%{http_code}' \
  -H "Authorization: Bearer $API_KEY" "$CARD_URL")"
echo "GET $CARD_URL -> HTTP $HTTP_CODE"
if [ "$HTTP_CODE" != "200" ]; then
  echo "STOP: the Runtime rejected a bearer-only request (HTTP $HTTP_CODE)."
  echo "Gate 0 FAILS on auth: the Runtime requires SigV4 or a JWT, and"
  echo "Connect Customer sends only an API key. Do not proceed — the"
  echo "fallback (host the A2A server outside Runtime) goes to Steven."
  echo "Response saved to /tmp/spike-card.json for inspection."
  exit 1
fi
python3 -c "import json; c=json.load(open('/tmp/spike-card.json')); print('Agent card:', c.get('name'), c.get('version'), '| url:', c.get('url'))"

# --- Step 2: register the A2A server application --------------------------
echo
echo "-- Step 2: register the A2A_SERVER application --"
APP_JSON="$(aws appintegrations create-application \
  --name general-1-spike \
  --namespace general-1-spike \
  --description "Gate 0 spike: General-1 fixed-reply agent (Project #3)" \
  --application-source-config "{\"ExternalUrlConfig\":{\"AccessUrl\":\"$RUNTIME_URL\"}}" \
  --application-type A2A_SERVER \
  --auth-config "{\"AuthType\":\"API_KEY\",\"CredentialProviderIdentifier\":\"$SECRET_ARN\"}" \
  --region "$REGION")"
APP_ID="$(echo "$APP_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["Id"])')"
APP_ARN="$(echo "$APP_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["Arn"])')"
echo "Application Id:  $APP_ID"
echo "Application Arn: $APP_ARN"

# --- Step 3: associate with the Connect instance -------------------------
echo
echo "-- Step 3: associate the application with the instance --"
ASSOC_JSON="$(aws connect create-integration-association \
  --instance-id "$INSTANCE_ID" \
  --integration-type APPLICATION \
  --integration-arn "$APP_ARN" \
  --region "$REGION")"
echo "$ASSOC_JSON" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("IntegrationAssociationId:", d.get("IntegrationAssociationId"))'

# --- Prerequisites for step 4 --------------------------------------------
echo
echo "-- Prerequisites: Lex bot + assistant --"
echo "Checking the Lex V2 bot association (AMAZON.QInConnectIntent bot is"
echo "required for self-service — our test has the caller talking to the"
echo "spike before any human):"
aws connect list-bots --instance-id "$INSTANCE_ID" --lex-version V2 --region "$REGION" \
  --query 'LexBots[*].Name' --output text || true
if [ -z "${ASSISTANT_ID:-}" ]; then
  echo
  echo "ASSISTANT_ID is not set. Available qconnect assistants:"
  aws qconnect list-assistants --region "$REGION" \
    --query 'assistantSummaries[*].[assistantId,name]' --output text || true
  echo
  echo "Re-run with ASSISTANT_ID=<id> (and SECURITY_PROFILE_ID=<id>) to continue."
  echo "Progress so far is saved in $OUT_FILE."
  {
    echo "APP_ID=$APP_ID"
    echo "APP_ARN=$APP_ARN"
    echo "RUNTIME_URL=$RUNTIME_URL"
    echo "SECRET_ARN=$SECRET_ARN"
  } > "$OUT_FILE"
  exit 0
fi
if [ -z "${SECURITY_PROFILE_ID:-}" ]; then
  echo
  echo "SECURITY_PROFILE_ID is not set. Available security profiles:"
  aws connect list-security-profiles --instance-id "$INSTANCE_ID" --region "$REGION" \
    --query 'SecurityProfileSummaryList[*].[Id,Name]' --output text || true
  echo
  echo "Re-run with SECURITY_PROFILE_ID=<id> to continue."
  {
    echo "APP_ID=$APP_ID"
    echo "APP_ARN=$APP_ARN"
    echo "RUNTIME_URL=$RUNTIME_URL"
    echo "SECRET_ARN=$SECRET_ARN"
    echo "ASSISTANT_ID=$ASSISTANT_ID"
  } > "$OUT_FILE"
  exit 0
fi

# --- Step 4: add the external collaborator --------------------------------
# Handoff mode, text only (audioStreamingEnabled false), immediate
# handoff true: the caller goes straight to the spike agent on the first
# turn, so the test does not depend on the orchestrator's judgement.
# This matches the guide's text-handoff example (no orchestration prompt).
# UNVERIFIED: whether the no-prompt/no-guardrail + Complete-tool-only
# restriction documented for audio immediate handoff also applies to
# text immediate handoff. If creation fails on validation, retry with
# immediateHandoff false and an orchestration prompt (see README).
echo
echo "-- Step 4: create the orchestrator AI agent (handoff collaborator) --"
cat > /tmp/spike-ai-agent.json <<EOF
{
  "assistantId": "$ASSISTANT_ID",
  "name": "general-1-spike-orchestrator",
  "type": "ORCHESTRATION",
  "visibilityStatus": "PUBLISHED",
  "configuration": {
    "orchestrationAIAgentConfiguration": {
      "connectInstanceArn": "arn:aws:connect:$REGION:$(aws sts get-caller-identity --query Account --output text):instance/$INSTANCE_ID",
      "multiAgentConfigurations": [
        {
          "handoffAgentConfiguration": {
            "agentTarget": { "applicationId": "$APP_ID" },
            "instruction": {
              "instruction": "Transfer the conversation to this agent for the Gate 0 spike test. The agent answers every turn with one fixed test reply and then hands the caller back with FINISH ESCALATE. Do not ask it anything else."
            },
            "audioStreamingEnabled": false,
            "immediateHandoff": true
          }
        }
      ]
    }
  }
}
EOF
AGENT_JSON="$(aws qconnect create-ai-agent \
  --cli-input-json file:///tmp/spike-ai-agent.json --region "$REGION")"
AI_AGENT_ID="$(echo "$AGENT_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["aiAgent"]["aiAgentId"])')"
AI_AGENT_ARN="$(echo "$AGENT_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["aiAgent"]["aiAgentArn"])')"
echo "AI agent Id:  $AI_AGENT_ID"
echo "AI agent Arn: $AI_AGENT_ARN"

# --- Step 5: security profile ---------------------------------------------
echo
echo "-- Step 5: security profile (allow the app + contact context) --"
aws connect update-security-profile \
  --instance-id "$INSTANCE_ID" \
  --security-profile-id "$SECURITY_PROFILE_ID" \
  --allowed-ai-agents "[{\"Arn\":\"$APP_ARN\",\"Type\":\"THIRD_PARTY\"}]" \
  --region "$REGION"
echo "NOTE: add the 'Access Contact Control Panel' permission to this"
echo "security profile in the console if the spike should receive"
echo "contact context (channel, addresses). Without it, Connect sends"
echo "no contact context — the spike still works, it just cannot prove"
echo "Gate 0 point 3 (context) in full."
# Associate once per agent ARN: unversioned, then versioned (the
# versioned ARN exists only after step 6 publishes a version, so the
# second association runs after publishing — see below).
aws connect associate-security-profiles \
  --instance-id "$INSTANCE_ID" \
  --entity-arn "$AI_AGENT_ARN" \
  --entity-type AI_AGENT \
  --security-profiles "Id=$SECURITY_PROFILE_ID" \
  --region "$REGION"

# --- Step 6: publish -------------------------------------------------------
echo
echo "-- Step 6: publish the AI agent version --"
VERSION_JSON="$(aws qconnect create-ai-agent-version \
  --assistant-id "$ASSISTANT_ID" \
  --ai-agent-id "$AI_AGENT_ID" \
  --region "$REGION")"
VERSION_ARN="$(echo "$VERSION_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["aiAgentVersion"]["aiAgentVersionArn"])')"
echo "Published version ARN: $VERSION_ARN"
echo "Associating the security profile with the VERSIONED agent ARN:"
aws connect associate-security-profiles \
  --instance-id "$INSTANCE_ID" \
  --entity-arn "$VERSION_ARN" \
  --entity-type AI_AGENT \
  --security-profiles "Id=$SECURITY_PROFILE_ID" \
  --region "$REGION"

{
  echo "APP_ID=$APP_ID"
  echo "APP_ARN=$APP_ARN"
  echo "RUNTIME_URL=$RUNTIME_URL"
  echo "SECRET_ARN=$SECRET_ARN"
  echo "ASSISTANT_ID=$ASSISTANT_ID"
  echo "AI_AGENT_ID=$AI_AGENT_ID"
  echo "AI_AGENT_ARN=$AI_AGENT_ARN"
  echo "AI_AGENT_VERSION_ARN=$VERSION_ARN"
  echo "SECURITY_PROFILE_ID=$SECURITY_PROFILE_ID"
} > "$OUT_FILE"

echo
echo "== Registration complete =="
echo "IDs saved to $OUT_FILE"
echo "NEXT: console work (README step 5) — add the Connect assistant"
echo "block (Agent Assistance AI agent = the version ARN above) to the"
echo "separate Gen-1 TEST flow, then make the test call and work the"
echo "Gate 0 verification table in the README."
