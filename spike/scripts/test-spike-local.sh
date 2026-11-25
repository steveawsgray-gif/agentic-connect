#!/usr/bin/env bash
# Local smoke test for the Gate 0 spike agent — no AWS, no model.
# Starts the server with SPIKE_NO_MODEL=1 (the Bedrock call is skipped)
# and a throwaway dev API key, then runs scripts/smoke_test.py, which
# replays the Connect HTTPS request flow from the AWS sample events.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$SCRIPT_DIR/../agent"
VENV="${SPIKE_VENV:-/tmp/spike-venv}"

if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating venv at $VENV ..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet -r "$AGENT_DIR/requirements.txt"
fi

export SPIKE_NO_MODEL=1
export SPIKE_DEV_API_KEY=test-key-123
export AGENTCORE_RUNTIME_URL=http://localhost:9000

"$VENV/bin/python" "$AGENT_DIR/main.py" > /tmp/spike-server.log 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT

echo "Waiting for the server on :9000 ..."
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null http://localhost:9000/ping 2>/dev/null; then
    break
  fi
  sleep 1
done

python3 "$SCRIPT_DIR/smoke_test.py" http://localhost:9000
TEST_RC=$?

echo
echo "--- server log (last 30 lines) ---"
tail -30 /tmp/spike-server.log
exit $TEST_RC
