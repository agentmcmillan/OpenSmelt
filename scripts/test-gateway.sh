#!/bin/bash
# Test MCP Gateway — tool enumeration smoke test
# Verifies gateway is running and all backends are mounted
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:9000}"

echo "=== OpenSmelt Gateway Smoke Test ==="
echo "Target: ${GATEWAY_URL}"
echo ""

# 1. Health check
echo "--- Health Check ---"
HEALTH=$(curl -sf "${GATEWAY_URL}/health" 2>/dev/null)
if [ $? -ne 0 ]; then
    echo "FAIL: Gateway health endpoint unreachable"
    exit 1
fi

STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))")
CONNECTED=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('connected',0))")
TOTAL=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_backends',0))")
echo "Status: ${STATUS} (${CONNECTED}/${TOTAL} backends)"

# Show per-backend status
echo ""
echo "--- Backend Status ---"
echo "$HEALTH" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for name, info in d.get('backends', {}).items():
    status = info.get('status', 'unknown')
    err = info.get('error', '')
    icon = 'PASS' if status == 'connected' else 'FAIL'
    msg = f'  {icon}: {name} — {status}'
    if err:
        msg += f' ({err})'
    print(msg)
"

# 2. MCP Initialize
echo ""
echo "--- MCP Protocol Test ---"
INIT_RESP=$(curl -sf -X POST "${GATEWAY_URL}/mcp" \
    -H "Content-Type: application/json" \
    -d '{
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-script", "version": "1.0.0"}
        }
    }' 2>/dev/null)

if [ $? -ne 0 ]; then
    echo "FAIL: MCP initialize failed"
    exit 1
fi

SESSION_ID=$(echo "$INIT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',{}).get('serverInfo',{}).get('name','unknown'))" 2>/dev/null)
echo "Server: ${SESSION_ID}"

# 3. List tools
TOOLS_RESP=$(curl -sf -X POST "${GATEWAY_URL}/mcp" \
    -H "Content-Type: application/json" \
    -d '{
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }' 2>/dev/null)

if [ $? -ne 0 ]; then
    echo "FAIL: tools/list failed"
    exit 1
fi

# Count tools per namespace
echo ""
echo "--- Tool Namespaces ---"
echo "$TOOLS_RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
tools = d.get('result', {}).get('tools', [])
namespaces = {}
for t in tools:
    name = t.get('name', '')
    ns = name.split('_')[0] if '_' in name else 'root'
    namespaces[ns] = namespaces.get(ns, 0) + 1

print(f'Total tools: {len(tools)}')
for ns, count in sorted(namespaces.items()):
    print(f'  {ns}: {count} tools')
"

echo ""
echo "=== Test Complete ==="
