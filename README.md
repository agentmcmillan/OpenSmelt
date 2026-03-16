# OpenSmelt

An MCP gateway that aggregates multiple backend MCP servers into a single endpoint. Connect once, get all tools.

Any MCP-compatible client (Claude Code, Codex CLI, Gemini CLI, Cursor) connects to one URL and gets access to 100+ tools across namespaced backends.

## Architecture

```
MCP Client (Claude Code, Codex CLI, etc.)
    |
    v
MCP Gateway :9000  ──  FastMCP create_proxy() aggregates all backends
    |
    ├── memento      Shared semantic memory (Node.js + pgvector)     [core]
    ├── tools        Fleet status, Signal messaging, shared config   [core]
    ├── docker       Docker management (supergateway wrapper)        [core]
    ├── rss          RSS feed reader (supergateway wrapper)          [core]
    ├── github       GitHub API tools (supergateway wrapper)         [profile: github]
    ├── ollama       Local LLM via Ollama (supergateway wrapper)     [profile: ollama]
    ├── ssh          SSH to fleet devices (supergateway wrapper)     [profile: ssh]
    ├── signal       Signal messaging (supergateway wrapper)         [profile: signal]
    └── cloudflare   Cloudflare API (supergateway wrapper)           [profile: cloudflare]
```

Tools are namespaced by backend (e.g., `memento_remember`, `github_search_repositories`, `docker_list_containers`).

## Prerequisites

- **Docker 20.10+** with Docker Compose v2
- **4 GB RAM** minimum (8 GB recommended if running Ollama)
- **10 GB disk** for Docker images and data volumes
- A **GitHub personal access token** if you want the GitHub backend ([create one](https://github.com/settings/tokens))

## Quick Start

### Option A: Interactive Setup (recommended)

```bash
git clone https://github.com/agentmcmillan/OpenSmelt.git
cd OpenSmelt
./setup.sh                    # generates .env, picks backends
docker compose up -d          # start services
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

# Edit .env:
#   - Set COMPOSE_PROFILES to enable backends (e.g., github,ollama,ssh)
#   - Fill in credentials for each enabled profile
#   - See .env.example for all options

# Start
docker compose up -d

# Verify
curl http://localhost:9000/health
```

### Choosing Backends

Backends are controlled by Docker Compose **profiles** via `COMPOSE_PROFILES` in `.env`:

| Profile | What it enables | Requires |
|---------|----------------|----------|
| `github` | GitHub API tools | `GITHUB_PERSONAL_ACCESS_TOKEN` |
| `ollama` | Local LLM tools | Ollama running on host |
| `ssh` | SSH to fleet devices | SSH keys in `ssh-keys/` |
| `signal` | Signal messaging | Signal REST API + `AI_SIGNALS_PATH` |
| `cloudflare` | Cloudflare API | `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` |

Core services (memento, tools, docker, rss) always start regardless of profiles.

```bash
# Examples:
COMPOSE_PROFILES=github                     # core + GitHub only
COMPOSE_PROFILES=github,ollama,ssh          # core + GitHub + Ollama + SSH
COMPOSE_PROFILES=github,ollama,ssh,signal   # everything except Cloudflare
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

### Profile-Specific

| Variable | Profile | Description |
|----------|---------|-------------|
| `GITHUB_PERSONAL_ACCESS_TOKEN` | `github` | GitHub PAT ([create one](https://github.com/settings/tokens)) |
| `SIGNAL_API_URL` | `signal` | Signal REST API endpoint |
| `SIGNAL_BOT_NUMBER` | `signal` | Signal sender phone number |
| `SIGNAL_RECIPIENT` | `signal` | Default Signal recipient |
| `AI_SIGNALS_PATH` | `signal` | Path to ai-signals dist directory |
| `OLLAMA_HOST` | `ollama` | Ollama endpoint (default: `http://host.docker.internal:11434`) |
| `CLOUDFLARE_API_TOKEN` | `cloudflare` | Cloudflare API token |
| `CLOUDFLARE_ACCOUNT_ID` | `cloudflare` | Cloudflare account ID |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `COMPOSE_PROFILES` | *(empty)* | Comma-separated list of backend profiles to enable |
| `DOMAIN` | `localhost` | Domain for Caddy reverse proxy |
| `GATEWAY_PORT` | `9000` | Gateway listen port |
| `SSH_KEYS_PATH` | `./ssh-keys` | Path to SSH keys directory |

## Backends

| Backend | Tools | Description | Startup |
|---------|-------|-------------|---------|
| **memento** | 11 | Semantic memory with pgvector — remember, recall, reflect | Core (always) |
| **tools** | 9 | Fleet monitoring, Signal notifications, shared config | Core (always) |
| **docker** | 4 | Container management — list, start, stop, logs | Core (always) |
| **rss** | 2 | RSS feed reader | Core (always) |
| **github** | 26 | GitHub API — repos, issues, PRs, search | Profile: `github` |
| **ollama** | 13 | Local LLMs — chat, generate, models | Profile: `ollama` |
| **ssh** | 37 | SSH to fleet devices — exec, file transfer | Profile: `ssh` |
| **signal** | 3 | Signal messaging | Profile: `signal` |
| **cloudflare** | varies | Cloudflare API | Profile: `cloudflare` |

## Adding a Custom Backend

1. Create a Dockerfile in `mcp-wrappers/your-tool/Dockerfile` using the supergateway pattern:

```dockerfile
FROM node:22-slim
RUN npm i -g supergateway @your-org/your-mcp-server
EXPOSE 3000
CMD ["supergateway", "--stdio", "npx @your-org/your-mcp-server", \
     "--port", "3000", "--outputTransport", "streamableHttp", "--stateful", \
     "--healthEndpoint", "/health"]
```

2. Add the service to `docker-compose.yml` (use a profile if it's optional)
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

**Ollama backend can't connect (Linux):**
`host.docker.internal` only works on Docker Desktop (macOS/Windows). On Linux, set `OLLAMA_HOST` to your host's LAN IP (e.g., `http://192.168.1.100:11434`) and ensure Ollama is listening on `0.0.0.0`.

**Missing directories:**
Run `mkdir -p caddy/client-certs ssh-keys` or run `./setup.sh` which creates them automatically.

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
