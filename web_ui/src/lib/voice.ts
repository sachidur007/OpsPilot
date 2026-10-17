import type { FleetService } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_MCP_URL || "/mcp";

const ACTIONS: Record<string, string> = {
  rollback: "roll it back",
  unseal: "unseal it",
  cert_rotation: "rotate the certificate",
  dns_flush: "flush DNS",
  scale_pods: "scale the pods",
  failover: "fail it over",
};

const SEVERITY: Record<string, string> = {
  "SEV-1": "severity one",
  "SEV-2": "severity two",
  "SEV-3": "severity three",
};

let current: HTMLAudioElement | null = null;
let speakSeq = 0;
let inflight: AbortController | null = null;

export function stopSpeaking() {
  speakSeq += 1;
  inflight?.abort();
  inflight = null;
  if (current) {
    current.pause();
    current.src = "";
    current = null;
  }
}

export function hyderabadBriefing(incident: FleetService) {
  const service = incident.service_id.replaceAll("-", " ");
  const action = ACTIONS[incident.recommended_action] ?? incident.recommended_action;
  const severity = incident.severity ? SEVERITY[incident.severity] ?? incident.severity : "an incident";
  const found = (incident.root_cause || incident.impact_summary || incident.issue_type || "an anomaly")
    .replaceAll("/", " ");
  const target = incident.target.replaceAll("-", " ");
  const rate = incident.error_rate ? `${(incident.error_rate * 100).toFixed(1)} percent errors` : "a normal error rate";
  return (
    `${service}. Here is what I found. ${found}. ` +
    `The service is ${incident.status}, ${severity}, running ${rate}. ` +
    `I recommend we ${action}, to ${target}. ` +
    `Say approve and I will do it.`
  );
}

export async function speakHyderabad(text: string) {
  const seq = ++speakSeq;
  inflight?.abort();
  const controller = new AbortController();
  inflight = controller;
  if (current) {
    current.pause();
    current.src = "";
    current = null;
  }
  const response = await fetch(`${API_BASE_URL}/agent/speak`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text }),
    signal: controller.signal,
  });
  if (seq !== speakSeq) return;
  if (!response.ok) {
    throw new Error("speak failed");
  }
  const blob = await response.blob();
  if (seq !== speakSeq) return;
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  current = audio;
  audio.onended = () => {
    URL.revokeObjectURL(url);
    if (current === audio) current = null;
  };
  await audio.play();
}
