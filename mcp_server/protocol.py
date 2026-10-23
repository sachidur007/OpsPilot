"""Model Context Protocol tool surface over the same simulator functions the REST API uses."""

from mcp.server.mcpserver import MCPServer

from mcp_server.tools.ops_tools import (
    tool_get_alert,
    tool_get_fleet,
    tool_get_service_status,
    tool_get_timeline,
    tool_list_incidents,
    tool_verify_recovery,
)

ops_mcp = MCPServer(
    "FleetOps",
    instructions=(
        "Fleet Commander incident connector. Read incidents, alerts, and timelines. "
        "Remediation stays on the agent approve path."
    ),
)


@ops_mcp.tool(description="Return the fleet split into active incidents and healthy services.")
def get_fleet() -> dict:
    return tool_get_fleet()


@ops_mcp.tool(description="Return raw telemetry for one service: metrics, logs, and deploy history.")
def get_service_status(service_id: str) -> dict:
    return tool_get_service_status(service_id)


@ops_mcp.tool(description="Read the service back from simulator state and report whether it is healthy.")
def verify_recovery(service_id: str) -> dict:
    return tool_verify_recovery(service_id)


@ops_mcp.tool(description="List open incidents from the fleet record.")
def list_incidents() -> dict:
    return tool_list_incidents()


@ops_mcp.tool(description="Return timeline events, optionally for one service.")
def get_timeline(service_id: str = "") -> dict:
    return tool_get_timeline(service_id)


@ops_mcp.tool(description="Return one alert: service, severity, error rate, and suggested action.")
def get_alert(service_id: str) -> dict:
    return tool_get_alert(service_id)
