import axios from "axios";
import type { AnalyzeResult, CommandEntry, FleetSnapshot, RemediateResult } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_MCP_URL || "/mcp";

export const agentClient = {
  getFleet: async (): Promise<FleetSnapshot> => {
    const res = await axios.get(`${API_BASE_URL}/agent/fleet`);
    return res.data;
  },
  analyze: async (serviceId: string): Promise<AnalyzeResult> => {
    const res = await axios.post(`${API_BASE_URL}/agent/analyze`, { service_id: serviceId });
    return res.data;
  },
  remediate: async (serviceId: string, action: string, target: string): Promise<RemediateResult> => {
    const res = await axios.post(`${API_BASE_URL}/agent/remediate`, {
      service_id: serviceId,
      action,
      target,
    });
    return res.data;
  },
  reject: async (serviceId: string) => {
    const res = await axios.post(`${API_BASE_URL}/agent/reject`, { service_id: serviceId });
    return res.data;
  },
  reset: async (): Promise<FleetSnapshot> => {
    const res = await axios.post(`${API_BASE_URL}/agent/reset`);
    return res.data;
  },
  note: async (serviceId: string | null, channel: "voice" | "text" | "action", role: "user" | "agent", text: string) => {
    const res = await axios.post(`${API_BASE_URL}/agent/record`, {
      service_id: serviceId,
      channel,
      role,
      text,
    });
    return res.data as { record: CommandEntry[] };
  },
  discuss: async (serviceId: string | null, text: string, channel: "voice" | "text") => {
    const res = await axios.post(`${API_BASE_URL}/agent/discuss`, {
      service_id: serviceId,
      channel,
      text,
    });
    return res.data as { reply: string; record: CommandEntry[]; service_id: string | null; scope?: "service" | "all" };
  },
  chaos: async () => {
    const res = await axios.post(`${API_BASE_URL}/agent/chaos`);
    return res.data as {
      status: string;
      message?: string;
      service?: { service_id: string };
      chaos_remaining?: number;
    };
  },
};

export const ACTIONS = [
  "rollback",
  "unseal",
  "cert_rotation",
  "dns_flush",
  "scale_pods",
  "failover",
] as const;
