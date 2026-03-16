"""
MCP Gateway — Single-endpoint aggregation layer.

Proxies backend MCP servers through one FastMCP endpoint.
Claude Code connects once and gets all tools, namespaced by backend.

Uses create_proxy() with MCPConfig dict to aggregate all backends.
"""

import os
import asyncio
import logging
import socket
from urllib.parse import urlparse

import httpx
from starlette.responses import JSONResponse
from fastmcp import FastMCP
from fastmcp.server import create_proxy

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mcp-gateway")


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


GATEWAY_VERSION = _env("GATEWAY_VERSION", "1.2.0")


# --- Backend configuration ---
def _build_mcp_config() -> dict:
    """Build MCPConfig dict for create_proxy."""
    servers = {}

    memento_url = _env("MEMENTO_URL", "http://memento:56332")
    memento_key = _env("MEMENTO_ACCESS_KEY", "")
    if memento_url:
        servers["memento"] = {"url": f"{memento_url}/sse?accessKey={memento_key}"}

    tools_url = _env("NETWORK_TOOLS_URL", "http://fastmcp-tools:8090")
    if tools_url:
        servers["tools"] = {"url": f"{tools_url}/mcp"}

    context7_url = _env("CONTEXT7_URL", "")
    if context7_url:
        servers["context7"] = {"url": context7_url}

    wrapper_backends = {
        "github": _env("GITHUB_MCP_URL", "http://github-mcp:3000"),
        "signal": _env("SIGNAL_MCP_URL", "http://signal-mcp:3000"),
        "docker": _env("DOCKER_MCP_URL", "http://docker-mcp:3000"),
        "ollama": _env("OLLAMA_MCP_URL", "http://ollama-mcp:3000"),
        "ssh": _env("SSH_MCP_URL", "http://ssh-mcp:3000"),
        "rss": _env("RSS_MCP_URL", "http://rss-mcp:3000"),
    }
    # Only include cloudflare if account ID is configured
    if _env("CLOUDFLARE_ACCOUNT_ID"):
        wrapper_backends["cloudflare"] = _env("CLOUDFLARE_MCP_URL", "http://cloudflare-mcp:3000")

    for name, base_url in wrapper_backends.items():
        if base_url:
            servers[name] = {"url": f"{base_url}/mcp"}

    return {"mcpServers": servers}


# --- Build the gateway proxy ---
MCP_CONFIG = _build_mcp_config()
BACKEND_URLS = {name: srv["url"] for name, srv in MCP_CONFIG["mcpServers"].items()}
# Redacted URLs for health endpoint (strip query params containing credentials)
BACKEND_URLS_SAFE = {}
for _name, _url in BACKEND_URLS.items():
    _parsed = urlparse(_url)
    BACKEND_URLS_SAFE[_name] = _parsed._replace(query="").geturl() if _parsed.query else _url
logger.info(f"Configuring gateway with {len(BACKEND_URLS)} backends: {', '.join(BACKEND_URLS.keys())}")

gateway = create_proxy(
    MCP_CONFIG,
    name="mcp-gateway",
    instructions=(
        "Unified MCP gateway aggregating tools from memento, network-tools, "
        "github, signal, docker, ollama, cloudflare, ssh-manager, "
        "and rss-reader. Tools are namespaced by backend."
    ),
)


# --- Health endpoint ---
def _check_tcp(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, TimeoutError):
        return False


async def _probe_backend(name: str, url: str) -> dict:
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        if parsed.scheme == "https":
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                await client.get(url)
                return {"status": "connected", "url": url}
        reachable = await asyncio.to_thread(_check_tcp, host, port)
        return {"status": "connected" if reachable else "unreachable", "url": url}
    except Exception as e:
        return {"status": "unreachable", "url": url, "error": str(e)}


@gateway.custom_route("/health", methods=["GET"])
async def health_check(request):
    tasks = [_probe_backend(name, url) for name, url in BACKEND_URLS.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    backends_health = {}
    for (name, _), result in zip(BACKEND_URLS.items(), results):
        if isinstance(result, Exception):
            backends_health[name] = {"status": "error", "error": str(result)}
        else:
            # Use redacted URL in health output
            result["url"] = BACKEND_URLS_SAFE.get(name, result.get("url", ""))
            backends_health[name] = result

    connected = sum(1 for b in backends_health.values() if b.get("status") == "connected")
    total = len(backends_health)
    overall = "ok" if connected == total else ("failed" if connected == 0 else "degraded")

    return JSONResponse({
        "status": overall,
        "gateway_version": GATEWAY_VERSION,
        "backends": backends_health,
        "total_backends": total,
        "connected": connected,
    })


if __name__ == "__main__":
    host = _env("GATEWAY_HOST", "0.0.0.0")
    port = int(_env("GATEWAY_PORT", "9000"))
    logger.info(f"Starting MCP Gateway {GATEWAY_VERSION} on {host}:{port}")
    gateway.run(transport="http", host=host, port=port)
