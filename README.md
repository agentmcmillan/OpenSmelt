# OpenSmelt

An MCP gateway that aggregates multiple backend MCP servers into a single endpoint. Connect once, get all tools.

Any MCP-compatible client (Claude Code, Codex CLI, Gemini CLI, Cursor) connects to one URL and gets access to 100+ tools across 9 namespaced backends.

## Architecture

```
MCP Client (Claude Code, Codex CLI, etc.)
    |
    v
MCP Gateway :9000  ──  FastMCP create_proxy() aggregates all backends
    |
    ├── memento      Shared semantic memory (Node.js + pgvector)
    ├── tools        Fleet status, Signal messaging, shared config (Python)
    ├── github       GitHub API tools (supergateway wrapper)
    ├── signal       Signal messaging (supergateway wrapper, optional)
    ├── docker       Docker management (supergateway wrapper)
    ├── ollama       Local LLM via Ollama (supergateway wrapper)
    ├── cloudflare   Cloudflare API (supergateway wrapper, optional)
    ├── ssh          SSH to fleet devices (supergateway wrapper)
    └── rss          RSS feed reader (supergateway wrapper)
```

Tools are namespaced by backend (e.g., `memento_remember`, `github_search_repositories`, `docker_list_containers`).

## Quick Start

### Prerequisites

- Docker + Docker Compose on the target host
- A GitHub personal access token ([create one](https://github.com/settings/tokens))

### Option A: Interactive Setup (recommended)

```bash
git clone https://github.com/agentmcmillan/OpenSmelt.git
cd OpenSmelt
./setup.sh                    # generates .env with secrets
docker compose up -d          # start all services
./scripts/test-gateway.sh     # verify everything works
```

### Option B: Manual Setup

```bash
git clone https://github.com/agentmcmillan/OpenSmelt.git
cd OpenSmelt

# Create .env from template
cp .env.example .env

# Generate secrets (paste into .env)
echo "MEMENTO_ACCESS_KEY=$(openssl rand -hex 32)"
echo "POSTGRES_PASSWORD=$(openssl rand -hex 32)"

# Edit .env — fill in GITHUB_PERSONAL_ACCESS_TOKEN at minimum
# Optional: configure Signal, Ollama, Cloudflare

# Start
docker compose up -d

# Verify
curl http://localhost:9000/health
```

### Remote Deploy

To deploy to a remote server via SSH:

```bash
DEPLOY_HOST=your-server-ip DEPLOY_USER=your-username ./deploy.sh
```

## Client Configuration

Once the gateway is running, configure your MCP client to connect.

### LAN Access

Add to your MCP client config (e.g., `~/.claude.json`, `.mcp.json`):

```json
{
  "mcpServers": {
    "opensmelt": {
      "type": "http",
      "url": "http://YOUR_SERVER_IP:9000/mcp"
    }
  }
}
```

Replace `YOUR_SERVER_IP` with the IP or hostname of the machine running OpenSmelt. If running locally, use `localhost`.

### Remote Access via Cloudflare

See `client-configs/gateway-remote.json` for a template with Cloudflare Access headers.

## Environment Variables

Copy `.env.example` to `.env` and fill in values. The `setup.sh` script automates this.

### Required

| Variable | Description |
|----------|-------------|
| `MEMENTO_ACCESS_KEY` | Auth key for Memento MCP (generate: `openssl rand -hex 32`) |
| `POSTGRES_PASSWORD` | PostgreSQL password (generate: `openssl rand -hex 32`) |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | GitHub PAT for github-mcp ([create one](https://github.com/settings/tokens)) |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `SIGNAL_API_URL` | *(empty)* | Signal REST API endpoint ([setup guide](https://github.com/bbernhard/signal-cli-rest-api)) |
| `SIGNAL_BOT_NUMBER` | *(empty)* | Signal sender phone number |
| `SIGNAL_RECIPIENT` | *(empty)* | Default Signal recipient |
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | Ollama endpoint (auto-detects host) |
| `CLOUDFLARE_ACCOUNT_ID` | *(empty)* | If set, enables Cloudflare MCP backend |
| `DOMAIN` | `localhost` | Domain for Caddy reverse proxy |
| `GATEWAY_PORT` | `9000` | Gateway listen port |

## Backends

| Backend | Tools | Description | Required? |
|---------|-------|-------------|-----------|
| **memento** | 11 | Semantic memory with pgvector — remember, recall, reflect | Always |
| **tools** | 9 | Fleet monitoring, Signal notifications, shared config | Always |
| **github** | 26 | GitHub API — repos, issues, PRs, search | Needs `GITHUB_PERSONAL_ACCESS_TOKEN` |
| **docker** | 4 | Container management — list, start, stop, logs | Needs Docker socket |
| **ollama** | 13 | Local LLMs — chat, generate, models | Needs Ollama running on host |
| **ssh** | 37 | SSH to fleet devices — exec, file transfer | Needs SSH keys in `ssh-keys/` |
| **rss** | 2 | RSS feed reader | Always |
| **signal** | 3 | Signal messaging | Needs Signal REST API |
| **cloudflare** | varies | Cloudflare API | Needs `CLOUDFLARE_ACCOUNT_ID` |

## Running a Subset of Backends

You can start only the services you need:

```bash
# Core only (gateway + memento + tools)
docker compose up -d postgres redis memento fastmcp-tools mcp-gateway

# Core + GitHub + Docker
docker compose up -d postgres redis memento fastmcp-tools github-mcp docker-mcp mcp-gateway
```

The gateway automatically skips unreachable backends and reports their status in `/health`.

## Adding a Custom Backend

1. Create a Dockerfile in `mcp-wrappers/your-tool/Dockerfile` using the supergateway pattern:

```dockerfile
FROM node:22-slim
RUN npm i -g supergateway @your-org/your-mcp-server
EXPOSE 3000
CMD ["supergateway", "--stdio", "npx @your-org/your-mcp-server", \
     "--port", "3000", "--outputTransport", "streamableHttp", "--stateful"]
```

2. Add the service to `docker-compose.yml`
3. Add the backend URL to `mcp-gateway/server.py` in `_build_mcp_config()`
4. Rebuild: `docker compose up -d --build`

## Health Check

```bash
curl http://localhost:9000/health
```

Returns JSON with per-backend status. `"status": "ok"` means all backends connected; `"degraded"` means some are offline but the gateway is functional.

## mTLS (Optional)

For direct HTTPS access with client certificates:

```bash
./caddy/generate-certs.sh              # Create CA (first time only)
./caddy/provision-client.sh my-device "My Device"  # Generate client cert
```

Then uncomment the mTLS block in `caddy/Caddyfile` and set your domain.

## Troubleshooting

**Gateway starts but some backends are unreachable:**
The gateway still works for connected backends. Check `docker compose logs <service>`.

**Gateway hangs at startup:**
`create_proxy()` can hang if a backend is mid-crash-loop. Run `docker compose ps` and restart any unhealthy service.

**rss-mcp OOM:**
Memory limit is set to 256M. Do not reduce below this.

**Missing `caddy/client-certs/` directory:**
Run `mkdir -p caddy/client-certs` or run `./caddy/generate-certs.sh`.

## Project Structure

```
OpenSmelt/
  mcp-gateway/          FastMCP gateway proxy server
  fastmcp-tools/        Python tools server (fleet, Signal, config)
  memento-mcp/          Node.js shared memory server (pgvector)
  mcp-wrappers/         Supergateway Dockerfiles for stdio MCP servers
    github/ signal/ docker/ ollama/ cloudflare/ ssh/ rss/
  caddy/                Caddyfile + mTLS cert scripts
  client-configs/       MCP client JSON configs (copy into your client)
  scripts/              Test and utility scripts
  deploy.sh             Remote SSH deploy script
  setup.sh              Interactive first-time setup
  docker-compose.yml    Service orchestration
  .env.example          Environment variable template
```

## License

[MIT](LICENSE)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on submitting PRs, adding backends, and running tests.
