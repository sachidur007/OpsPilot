import axios from "axios";
import type { AnalyzeResult, AwsStatus, CommandEntry, CoworkerParts, FleetSnapshot, RemediateResult, RepoFinding } from "./types";

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
  analyzeRepo: async (repo: string, ask = ""): Promise<RepoFinding> => {
    const res = await axios.post(`${API_BASE_URL}/agent/analyze`, { repo, ask });
    return res.data;
  },
  approveRepo: async (repo: string): Promise<{ status: string; finding: RepoFinding }> => {
    const res = await axios.post(`${API_BASE_URL}/agent/repo/approve`, { repo });
    return res.data;
  },
  rejectRepo: async (repo: string): Promise<{ status: string; finding: RepoFinding }> => {
    const res = await axios.post(`${API_BASE_URL}/agent/repo/reject`, { repo });
    return res.data;
  },
  remediate: async (serviceId: string, action: string, target: string, reason: string): Promise<RemediateResult> => {
    const res = await axios.post(`${API_BASE_URL}/agent/remediate`, {
      service_id: serviceId,
      action,
      target,
      reason,
    });
    return res.data;
  },
  reject: async (serviceId: string, reason: string) => {
    const res = await axios.post(`${API_BASE_URL}/agent/reject`, { service_id: serviceId, reason });
    return res.data as { status: string };
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
  discuss: async (serviceId: string | null, text: string, channel: "voice" | "text", repo?: string | null) => {
    const res = await axios.post(`${API_BASE_URL}/agent/discuss`, {
      service_id: repo ? null : serviceId,
      repo: repo || null,
      channel,
      text,
    });
    return res.data as {
      reply: string;
      record: CommandEntry[];
      service_id: string | null;
      repo?: string;
      scope?: "service" | "all" | "repo";
      coworker?: CoworkerParts;
    };
  },
  silence: async (serviceId: string, until: string) => {
    const res = await axios.post(`${API_BASE_URL}/agent/silence`, { service_id: serviceId, until });
    return res.data as { status: string };
  },
  aws: async (): Promise<AwsStatus> => {
    const res = await axios.get(`${API_BASE_URL}/agent/aws`);
    return res.data;
  },
  declare: async (
    serviceId: string,
    fields: {
      title: string;
      severity: string;
      details: string;
      notes: string;
      links: string[];
      attributes: { name: string; value: string }[];
    },
  ) => {
    const res = await axios.post(`${API_BASE_URL}/agent/declare`, { service_id: serviceId, ...fields });
    return res.data as {
      status: string;
      service_id?: string;
      service?: { service_id: string };
    };
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
