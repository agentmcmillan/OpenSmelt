#!/bin/bash
# Deploy OpenSmelt to a remote host via SSH
set -e

DEPLOY_HOST="${DEPLOY_HOST:-your-server-ip}"
DEPLOY_USER="${DEPLOY_USER:-your-username}"
DEPLOY_DIR="${DEPLOY_DIR:-~/opensmelt}"

if [ "$DEPLOY_HOST" = "your-server-ip" ]; then
    echo "ERROR: Set DEPLOY_HOST before deploying."
    echo "  DEPLOY_HOST=192.168.1.100 DEPLOY_USER=myuser ./deploy.sh"
    exit 1
fi

echo "=== OpenSmelt Deployment ==="
echo "Target: ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_DIR}"

# Create deploy tarball (exclude secrets, certs, git)
echo "Creating deployment archive..."
tar czf /tmp/opensmelt-deploy.tar.gz \
    --exclude='.git' \
    --exclude='.env' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='.DS_Store' \
    --exclude='caddy/client-certs/*.key' \
    --exclude='caddy/client-certs/*.p12' \
    --exclude='caddy/client-certs/*.csr' \
    --exclude='caddy/client-certs/ca.key' \
    --exclude='caddy/client-certs/ca.srl' \
    -C "$(dirname "$0")" .

# Copy to remote host
echo "Copying to ${DEPLOY_HOST}..."
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p ${DEPLOY_DIR}"
scp /tmp/opensmelt-deploy.tar.gz "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_DIR}/deploy.tar.gz"

# Extract and deploy
echo "Extracting and deploying..."
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" << 'REMOTE'
cd "${DEPLOY_DIR:-~/opensmelt}"
# Atomic extraction: unpack to temp dir, then overlay (prevents partial state on failure)
TMPDIR=$(mktemp -d ./deploy-XXXXXX)
tar xzf deploy.tar.gz -C "$TMPDIR"
rm deploy.tar.gz
cp -a "$TMPDIR"/. .
rm -rf "$TMPDIR"

# Ensure .env exists with required vars
if [ ! -f .env ]; then
    cp .env.example .env
    echo "WARNING: Created .env from template — edit with real values before starting"
    echo "Required: POSTGRES_PASSWORD, MEMENTO_ACCESS_KEY, GITHUB_PERSONAL_ACCESS_TOKEN"
    exit 1
fi

# Verify required env vars are set
source .env
if [ -z "$POSTGRES_PASSWORD" ] || [ -z "$MEMENTO_ACCESS_KEY" ]; then
    echo "ERROR: POSTGRES_PASSWORD and MEMENTO_ACCESS_KEY must be set in .env"
    exit 1
fi

if [ -z "$GITHUB_PERSONAL_ACCESS_TOKEN" ] || [ "$GITHUB_PERSONAL_ACCESS_TOKEN" = "ghp_your_token_here" ]; then
    echo "WARNING: GITHUB_PERSONAL_ACCESS_TOKEN not set — github-mcp will not work"
fi

# Build and start
docker compose down 2>/dev/null || true
docker compose build
docker compose up -d

echo ""
echo "=== Waiting for gateway to become healthy ==="
for i in $(seq 1 30); do
  STATUS=$(curl -sf --max-time 10 http://localhost:9000/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
  if [ "$STATUS" = "ok" ] || [ "$STATUS" = "degraded" ]; then
    echo "Gateway ready (${STATUS}) after $((i*4))s"
    break
  fi
  sleep 4
done

echo ""
echo "=== Service Status ==="
docker compose ps

echo ""
echo "=== Health Check ==="
curl -sf --max-time 10 http://localhost:9000/health | python3 -m json.tool 2>/dev/null || echo "Gateway not ready yet"

echo ""
echo "=== Deployment Complete ==="
echo "MCP Gateway: http://localhost:9000/mcp"
echo "Health:      http://localhost:9000/health"
REMOTE

# Cleanup
rm -f /tmp/opensmelt-deploy.tar.gz
echo "Done!"
