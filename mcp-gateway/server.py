"""
MCP Gateway — Single-endpoint aggregation layer with tool discovery.

Proxies backend MCP servers through one FastMCP endpoint.
Uses BM25SearchTransform to reduce token footprint: clients see ~12 tools
instead of 100+ and discover more via search_tools/call_tool.
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
from fastmcp.server.transforms.search import BM25SearchTransform

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mcp-gateway")


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


GATEWAY_VERSION = _env("GATEWAY_VERSION", "1.3.0")

# --- Tool discovery configuration ---
TOOL_DISCOVERY = _env("TOOL_DISCOVERY", "true").lower() == "true"

# Tools pinned in tools/list even when discovery is enabled.
# These are the most commonly needed tools across all sessions.
ALWAYS_VISIBLE = [
    "list_tool_categories",
    "memento_remember",
    "memento_recall",
    "tools_fleet_status",
    "tools_network_info",
    "tools_signal_send",
    "tools_config_get",
    "docker_list_containers",
]

# Category map for the list_tool_categories meta-tool
TOOL_CATEGORIES = {
    "memory": "Semantic memory — remember, recall, reflect, link, amend, consolidate (memento, 11 tools)",
    "infrastructure": "Fleet monitoring, device status, shared config store (tools, 9 tools)",
    "github": "GitHub API — repos, issues, PRs, commits, search, code (github, 26 tools)",
    "docker": "Container management — list, start, stop, logs (docker, 4 tools)",
    "ssh": "SSH to fleet devices — exec commands, file transfer, tunnels (ssh, 37 tools)",
    "ollama": "Local LLMs via Ollama — chat, generate, embeddings, models (ollama, 13 tools)",
    "communication": "Signal messaging and cross-device notifications (signal, 3 tools)",
    "web": "RSS feed reader and Cloudflare DNS/workers (rss + cloudflare, varies)",
}


# --- Backend configuration ---
def _build_mcp_config() -> dict:
    """Build MCPConfig dict for create_proxy."""
    servers = {}

    memento_url = _env("MEMENTO_URL", "http://memento:56332")
    memento_key = _env("MEMENTO_ACCESS_KEY", "")
    if memento_url:
        memento_cfg = {"url": f"{memento_url}/mcp"}
        if memento_key:
            memento_cfg["headers"] = {"Authorization": f"Bearer {memento_key}"}
        servers["memento"] = memento_cfg

    tools_url = _env("NETWORK_TOOLS_URL", "http://fastmcp-tools:8090")
    if tools_url:
        servers["tools"] = {"url": f"{tools_url}/mcp"}

    context7_url = _env("CONTEXT7_URL", "")
    if context7_url:
        servers["context7"] = {"url": context7_url}

    # Core wrappers (always started)
    wrapper_backends = {
        "docker": _env("DOCKER_MCP_URL", "http://docker-mcp:3000"),
        "rss": _env("RSS_MCP_URL", "http://rss-mcp:3000"),
    }

    # Profile-based wrappers (only include if profile is active)
    profile_backends = {
        "github": _env("GITHUB_MCP_URL", "http://github-mcp:3000"),
        "signal": _env("SIGNAL_MCP_URL", "http://signal-mcp:3000"),
        "ollama": _env("OLLAMA_MCP_URL", "http://ollama-mcp:3000"),
        "ssh": _env("SSH_MCP_URL", "http://ssh-mcp:3000"),
        "cloudflare": _env("CLOUDFLARE_MCP_URL", "http://cloudflare-mcp:3000"),
    }

    active_profiles = {p.strip() for p in _env("COMPOSE_PROFILES", "").split(",") if p.strip()}
    for name, url in profile_backends.items():
        if name in active_profiles:
            wrapper_backends[name] = url

    for name, base_url in wrapper_backends.items():
        if base_url:
            servers[name] = {"url": f"{base_url}/mcp"}

    return {"mcpServers": servers}


# --- Build the gateway proxy ---
MCP_CONFIG = _build_mcp_config()
BACKEND_URLS = {name: srv["url"] for name, srv in MCP_CONFIG["mcpServers"].items()}
BACKEND_URLS_SAFE = {}
for _name, _url in BACKEND_URLS.items():
    _parsed = urlparse(_url)
    BACKEND_URLS_SAFE[_name] = _parsed._replace(query="").geturl() if _parsed.query else _url

logger.info(f"Configuring gateway with {len(BACKEND_URLS)} backends: {', '.join(BACKEND_URLS.keys())}")

DISCOVERY_INSTRUCTIONS = (
    "Unified MCP gateway with tool discovery.\n\n"
    "ALWAYS AVAILABLE:\n"
    "- memento_remember / memento_recall (semantic memory)\n"
    "- tools_fleet_status / tools_network_info (infrastructure)\n"
    "- tools_signal_send (notifications)\n"
    "- tools_config_get (shared config)\n"
    "- docker_list_containers\n"
    "- list_tool_categories (see all available categories)\n\n"
    "TO FIND MORE TOOLS:\n"
    "1. Call list_tool_categories() for an overview\n"
    "2. Call search_tools(query='your need') to find specific tools\n"
    "3. Call call_tool(name='tool_name', arguments={...}) to execute\n\n"
    "Example: search_tools(query='create github issue') finds github_create_issue"
)

FULL_INSTRUCTIONS = (
    "Unified MCP gateway aggregating tools from memento, network-tools, "
    "github, signal, docker, ollama, cloudflare, ssh-manager, "
    "and rss-reader. Tools are namespaced by backend."
)

gateway = create_proxy(
    MCP_CONFIG,
    name="mcp-gateway",
    instructions=DISCOVERY_INSTRUCTIONS if TOOL_DISCOVERY else FULL_INSTRUCTIONS,
)


# --- Custom tools ---
@gateway.tool()
def list_tool_categories() -> dict:
    """List available tool categories in the gateway.
    Call search_tools(query='category name') to find tools in a category."""
    return TOOL_CATEGORIES


# --- Apply tool discovery transform (after custom tools are registered) ---
if TOOL_DISCOVERY:
    gateway.add_transform(BM25SearchTransform(
        max_results=10,
        always_visible=ALWAYS_VISIBLE,
    ))
    logger.info("Tool discovery enabled: BM25SearchTransform active, %d tools pinned", len(ALWAYS_VISIBLE))
else:
    logger.info("Tool discovery disabled: all tools visible in tools/list")


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
            result["url"] = BACKEND_URLS_SAFE.get(name, result.get("url", ""))
            backends_health[name] = result

    connected = sum(1 for b in backends_health.values() if b.get("status") == "connected")
    total = len(backends_health)
    overall = "ok" if connected == total else ("failed" if connected == 0 else "degraded")

    return JSONResponse({
        "status": overall,
        "gateway_version": GATEWAY_VERSION,
        "tool_discovery": TOOL_DISCOVERY,
        "backends": backends_health,
        "total_backends": total,
        "connected": connected,
    })


if __name__ == "__main__":
    host = _env("GATEWAY_HOST", "0.0.0.0")
    port = int(_env("GATEWAY_PORT", "9000"))
    logger.info(f"Starting MCP Gateway {GATEWAY_VERSION} on {host}:{port}")
    gateway.run(transport="http", host=host, port=port)
