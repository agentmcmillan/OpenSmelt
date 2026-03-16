#!/bin/bash
# End-to-end test — calls one safe read-only tool per backend
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:9000}"
ACCEPT_HEADER="Accept: application/json, text/event-stream"

echo "=== OpenSmelt Gateway E2E Test ==="
echo "Target: ${GATEWAY_URL}"
echo ""

# Helper: initialize an MCP session and return the session ID
init_session() {
    curl -s --max-time 15 -D - -X POST "${GATEWAY_URL}/mcp" \
        -H "Content-Type: application/json" \
        -H "${ACCEPT_HEADER}" \
        -d '{
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "e2e-test", "version": "1.0.0"}
            }
        }' 2>/dev/null | grep -i "^mcp-session-id:" | awk '{print $2}' | tr -d '\r'
}

# Helper: call a tool through MCP using an existing session ID
call_tool() {
    local session_id="$1"
    local tool_name="$2"
    local args="$3"

    curl -s --max-time 60 -X POST "${GATEWAY_URL}/mcp" \
        -H "Content-Type: application/json" \
        -H "${ACCEPT_HEADER}" \
        -H "mcp-session-id: ${session_id}" \
        -d "{
            \"jsonrpc\": \"2.0\",
            \"id\": 2,
            \"method\": \"tools/call\",
            \"params\": {
                \"name\": \"${tool_name}\",
                \"arguments\": ${args}
            }
        }" 2>/dev/null | sed -n 's/^data: //p' | tail -1
}

# Check health first to know which backends are up
HEALTH=$(curl -sf --max-time 10 "${GATEWAY_URL}/health" 2>/dev/null)
BACKENDS=$(echo "$HEALTH" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for name, info in d.get('backends', {}).items():
    if info.get('status') == 'connected':
        print(name)
" 2>/dev/null)

PASS=0
FAIL=0
SKIP=0

test_backend() {
    local name="$1"
    local tool="$2"
    local args="$3"

    if echo "$BACKENDS" | grep -q "^${name}$" 2>/dev/null; then
        SESSION_ID=$(init_session 2>/dev/null || echo "")
        if [ -z "$SESSION_ID" ]; then
            echo "  FAIL: ${name} (could not initialize session)"
            FAIL=$((FAIL + 1))
            return
        fi
        RESULT=$(call_tool "$SESSION_ID" "$tool" "$args" 2>/dev/null)
        if [ -n "$RESULT" ] && echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if 'result' in d else 1)" 2>/dev/null; then
            echo "  PASS: ${name} (${tool})"
            PASS=$((PASS + 1))
        else
            echo "  FAIL: ${name} (${tool})"
            FAIL=$((FAIL + 1))
        fi
    else
        echo "  SKIP: ${name} (backend offline)"
        SKIP=$((SKIP + 1))
    fi
}

echo "--- Testing read-only tools per backend ---"
test_backend "memento" "memento_memory_stats" "{}"
test_backend "tools" "tools_network_info" "{}"
test_backend "github" "github_search_repositories" '{"query": "fastmcp"}'
test_backend "rss" "rss_fetch_feed" '{"url": "https://news.ycombinator.com/rss"}'
test_backend "ollama" "ollama_list_models" "{}"
test_backend "docker" "docker_list_containers" "{}"
test_backend "ssh" "ssh_ssh_list_servers" "{}"
# signal — upstream may be unreachable; cloudflare — not always configured

echo ""
echo "=== Results ==="
echo "PASS: ${PASS}  FAIL: ${FAIL}  SKIP: ${SKIP}"
[ "$FAIL" -eq 0 ] && echo "Overall: PASS" || echo "Overall: FAIL"
exit $FAIL
