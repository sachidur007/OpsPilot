const MCP_URL = `${process.env.NEXT_PUBLIC_MCP_URL || "/mcp"}/protocol/`;

type JsonRpc = {
  result?: {
    protocolVersion?: string;
    tools?: { name: string }[];
    content?: { text?: string }[];
    isError?: boolean;
  };
  error?: { message?: string };
};

async function rpc(id: number, method: string, params: object): Promise<JsonRpc> {
  const response = await fetch(MCP_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
      "MCP-Protocol-Version": "2025-11-25",
    },
    body: JSON.stringify({ jsonrpc: "2.0", id, method, params }),
  });
  const raw = await response.text();
  const line = raw.split("\n").find((item) => item.startsWith("data: "));
  const body = line ? line.slice(6) : raw;
  return JSON.parse(body) as JsonRpc;
}

export async function investigateOverMcp(serviceId: string): Promise<string[]> {
  const notes: string[] = [];
  const opened = await rpc(1, "initialize", {
    protocolVersion: "2025-11-25",
    capabilities: {},
    clientInfo: { name: "fleetops-board", version: "1" },
  });
  const version = opened.result?.protocolVersion || opened.error?.message || "no version";
  notes.push(`MCP initialize ${version}.`);
  const listed = await rpc(2, "tools/list", {});
  const names = (listed.result?.tools || []).map((tool) => tool.name);
  notes.push(`MCP tools/list ${names.join(", ") || "none"}.`);
  const calls: { name: string; arguments: Record<string, string> }[] = [
    { name: "get_service_status", arguments: { service_id: serviceId } },
    { name: "list_incidents", arguments: {} },
    { name: "get_timeline", arguments: { service_id: serviceId } },
    { name: "get_alert", arguments: { service_id: serviceId } },
  ];
  for (let index = 0; index < calls.length; index += 1) {
    const call = calls[index];
    const called = await rpc(3 + index, "tools/call", call);
    const target = call.arguments.service_id ? ` ${call.arguments.service_id}` : "";
    if (called.error || called.result?.isError) {
      notes.push(`MCP tools/call ${call.name}${target} failed.`);
    } else {
      notes.push(`MCP tools/call ${call.name}${target}.`);
    }
  }
  return notes;
}
