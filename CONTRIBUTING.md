# Contributing to OpenSmelt

Thanks for your interest in contributing! This guide covers setup, testing, and how to add new backends.

## Development Setup

```bash
git clone https://github.com/agentmcmillan/OpenSmelt.git
cd OpenSmelt
./setup.sh                    # or: cp .env.example .env && edit
docker compose up -d
./scripts/test-gateway.sh     # verify everything works
```

## Running Tests

```bash
# Smoke test — checks health + tool enumeration
./scripts/test-gateway.sh

# End-to-end — calls one read-only tool per backend
./scripts/test-e2e.sh
```

Both scripts default to `http://localhost:9000`. Override with `GATEWAY_URL=http://other-host:9000`.

## Adding a New Backend

OpenSmelt wraps stdio MCP servers using [supergateway](https://github.com/nicholasgriffintn/supergateway) to expose them over HTTP. To add a new one:

### 1. Create a Dockerfile

```bash
mkdir mcp-wrappers/my-tool
```

Create `mcp-wrappers/my-tool/Dockerfile`:

```dockerfile
FROM node:22-slim
RUN npm i -g supergateway @your-org/your-mcp-server
EXPOSE 3000
CMD ["supergateway", "--stdio", "npx @your-org/your-mcp-server", \
     "--port", "3000", "--outputTransport", "streamableHttp", "--stateful"]
```

### 2. Add to docker-compose.yml

```yaml
  my-tool-mcp:
    build:
      context: ./mcp-wrappers/my-tool
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:3000/health 2>/dev/null | grep -q ok"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: 256M
```

### 3. Register in the gateway

In `mcp-gateway/server.py`, add to the `wrapper_backends` dict in `_build_mcp_config()`:

```python
"my-tool": _env("MY_TOOL_MCP_URL", "http://my-tool-mcp:3000"),
```

### 4. Build and test

```bash
docker compose up -d --build
./scripts/test-gateway.sh
```

## Code Style

- Python: follow existing patterns (FastMCP tools, env-based config)
- Dockerfiles: use `node:22-slim` for Node wrappers, `python:3.12-slim` for Python
- Keep resource limits in docker-compose (256M default for wrappers)

## Pull Requests

- Keep PRs focused — one feature or fix per PR
- Include a brief description of what changed and why
- Make sure `./scripts/test-gateway.sh` passes
- If adding a backend, include the Dockerfile + compose entry + gateway registration

## Reporting Issues

Open an issue on GitHub with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Output of `docker compose ps` and `curl localhost:9000/health`
