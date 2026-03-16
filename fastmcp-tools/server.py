"""
OpenSmelt — Custom Tools Server

Provides shared tools accessible across all devices on the network:
- Signal notifications
- Fleet/device status
- Shared config store
- Cross-device context bridge to Memento
"""

import os
import json
import socket
import datetime
from pathlib import Path

import httpx
from fastmcp import FastMCP

mcp = FastMCP(
    "network-tools",
    instructions=(
        "Network-wide tools for cross-device communication, "
        "fleet monitoring, and shared configuration. "
        "Available to all devices on the local network."
    ),
)

# --- Configuration ---

SIGNAL_API_URL = os.environ.get("SIGNAL_API_URL", "")
SIGNAL_BOT_NUMBER = os.environ.get("SIGNAL_BOT_NUMBER", "")
SIGNAL_RECIPIENT = os.environ.get("SIGNAL_RECIPIENT", "")
NAS_HOST = os.environ.get("NAS_HOST", "")
MEMENTO_URL = os.environ.get("MEMENTO_URL", "http://memento:56332")
MEMENTO_ACCESS_KEY = os.environ.get("MEMENTO_ACCESS_KEY", "")

# Shared config file (persisted in Docker volume)
CONFIG_DIR = Path("/app/data")
CONFIG_FILE = CONFIG_DIR / "shared_config.json"


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def _save_config(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


# ============================================================
# Signal Notification Tools
# ============================================================


@mcp.tool()
async def signal_send(message: str, recipient: str = "") -> str:
    """Send a message via Signal API. Used for cross-device notifications.
    If no recipient specified, sends to the default recipient.
    Requires SIGNAL_API_URL, SIGNAL_BOT_NUMBER, and SIGNAL_RECIPIENT env vars."""
    if not SIGNAL_API_URL or not SIGNAL_BOT_NUMBER:
        return "Signal not configured. Set SIGNAL_API_URL, SIGNAL_BOT_NUMBER, and SIGNAL_RECIPIENT in .env"
    target = recipient or SIGNAL_RECIPIENT
    if not target:
        return "No recipient specified and SIGNAL_RECIPIENT not set in .env"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{SIGNAL_API_URL}/v2/send",
            json={
                "message": message,
                "number": SIGNAL_BOT_NUMBER,
                "recipients": [target],
            },
        )
        if resp.status_code == 201:
            return f"Message sent to {target}"
        return f"Failed ({resp.status_code}): {resp.text}"


# ============================================================
# Device / Fleet Status Tools
# ============================================================

# Known devices on the network — customize via fleet_register() or edit this dict.
# These are examples; replace with your own devices.
KNOWN_DEVICES = {}


def _load_fleet_registry():
    """Load fleet devices from persistent config on startup."""
    config = _load_config()
    fleet = config.get("fleet_registry", {})
    for did, info in fleet.items():
        KNOWN_DEVICES[did] = {
            "host": info["host"],
            "name": info["name"],
            "ports": info.get("ports", [22]),
        }


# Load persisted devices on import
_load_fleet_registry()


def _check_port(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, TimeoutError):
        return False


@mcp.tool()
def fleet_status(device_id: str = "") -> dict:
    """Check status of network devices. Pass a specific device_id
    or leave empty for all devices. Use fleet_register to add devices first."""
    if not KNOWN_DEVICES:
        return {"message": "No devices registered. Use fleet_register() to add devices."}
    devices = (
        {device_id: KNOWN_DEVICES[device_id]}
        if device_id and device_id in KNOWN_DEVICES
        else KNOWN_DEVICES
    )
    results = {}
    for did, info in devices.items():
        port_status = {}
        for port in info["ports"]:
            port_status[port] = "up" if _check_port(info["host"], port) else "down"
        any_up = any(s == "up" for s in port_status.values())
        results[did] = {
            "name": info["name"],
            "host": info["host"],
            "status": "online" if any_up else "offline",
            "ports": port_status,
            "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    return results


@mcp.tool()
def fleet_register(
    device_id: str, host: str, name: str, ports: list[int] | None = None
) -> str:
    """Register a new device in the fleet registry (persisted in shared config)."""
    config = _load_config()
    fleet = config.get("fleet_registry", {})
    fleet[device_id] = {
        "host": host,
        "name": name,
        "ports": ports or [22],
        "registered_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    config["fleet_registry"] = fleet
    _save_config(config)
    # Also add to runtime known devices
    KNOWN_DEVICES[device_id] = {"host": host, "name": name, "ports": ports or [22]}
    return f"Registered device '{device_id}' ({name}) at {host}"


# ============================================================
# Shared Configuration Tools
# ============================================================


@mcp.tool()
def config_get(key: str = "") -> dict | str:
    """Get a shared config value. If no key specified, returns all config."""
    config = _load_config()
    if not key:
        return config
    return config.get(key, f"Key '{key}' not found")


@mcp.tool()
def config_set(key: str, value: str) -> str:
    """Set a shared config value accessible by all devices on the network."""
    config = _load_config()
    # Try to parse as JSON for complex values
    try:
        config[key] = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        config[key] = value
    _save_config(config)
    return f"Config '{key}' set successfully"


@mcp.tool()
def config_delete(key: str) -> str:
    """Delete a shared config key."""
    config = _load_config()
    if key in config:
        del config[key]
        _save_config(config)
        return f"Config '{key}' deleted"
    return f"Key '{key}' not found"


# ============================================================
# Network Info Tools
# ============================================================


@mcp.tool()
def network_info() -> dict:
    """Get information about this MCP server and the network it's running on."""
    return {
        "server": "network-tools",
        "version": "1.0.0",
        "hostname": socket.gethostname(),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "services": {
            "memento_mcp": f"{MEMENTO_URL}/health",
            "signal_api": SIGNAL_API_URL or "not configured",
        },
        "known_devices": list(KNOWN_DEVICES.keys()),
    }


@mcp.tool()
async def memento_health() -> dict:
    """Check health of the Memento MCP shared memory server."""
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            resp = await client.get(f"{MEMENTO_URL}/health")
            return resp.json()
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}


# ============================================================
# Cross-Device Context Bridge
# ============================================================


@mcp.tool()
async def broadcast_context(
    topic: str, content: str, source_device: str = "unknown"
) -> str:
    """Store a context fragment in Memento AND notify via Signal.
    Use this when a device discovers something other devices should know about."""
    results = []

    # Try to store in Memento
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            init_resp = await client.post(
                f"{MEMENTO_URL}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "network-tools", "version": "1.0.0"},
                    },
                },
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {MEMENTO_ACCESS_KEY}",
                },
            )
            session_id = init_resp.headers.get("mcp-session-id", "")

            remember_resp = await client.post(
                f"{MEMENTO_URL}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "remember",
                        "arguments": {
                            "content": content,
                            "topic": topic,
                            "type": "fact",
                            "keywords": [source_device, "broadcast"],
                        },
                    },
                },
                headers={
                    "Content-Type": "application/json",
                    "MCP-Session-Id": session_id,
                },
            )
            results.append(f"Memento: stored ({remember_resp.status_code})")
        except Exception as e:
            results.append(f"Memento: failed ({e})")

    # Notify via Signal (if configured)
    if SIGNAL_API_URL and SIGNAL_BOT_NUMBER and SIGNAL_RECIPIENT:
        try:
            msg = f"[{source_device}] {topic}: {content[:200]}"
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{SIGNAL_API_URL}/v2/send",
                    json={
                        "message": msg,
                        "number": SIGNAL_BOT_NUMBER,
                        "recipients": [SIGNAL_RECIPIENT],
                    },
                )
                results.append("Signal: notified")
        except Exception as e:
            results.append(f"Signal: failed ({e})")
    else:
        results.append("Signal: not configured (skipped)")

    return " | ".join(results)


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8090"))
    mcp.run(transport="http", host=host, port=port)
