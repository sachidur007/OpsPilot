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
    clientInfo: { name: "opspilot-board", version: "1" },
  });
  const version = opened.result?.protocolVersion || opened.error?.message || "no version";
  notes.push(`MCP initialize ${version}.`);
  const listed = await rpc(2, "tools/list", {});
  const names = (listed.result?.tools || []).map((tool) => tool.name);
  notes.push(`MCP tools/list ${names.join(", ") || "none"}.`);
  const called = await rpc(3, "tools/call", {
    name: "get_service_status",
    arguments: { service_id: serviceId },
  });
  if (called.error || called.result?.isError) {
    notes.push(`MCP tools/call get_service_status ${serviceId} failed.`);
  } else {
    notes.push(`MCP tools/call get_service_status ${serviceId}.`);
  }
  return notes;
}
