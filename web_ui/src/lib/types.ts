export type FleetService = {
  service_id: string;
  layer: string;
  layer_label: string;
  status: string;
  severity: "SEV-1" | "SEV-2" | "SEV-3" | null;
  version: string;
  fault_version: string;
  stable_version: string;
  error_rate: number;
  log_level: string;
  issue_type: string | null;
  impact_summary: string;
  log_message: string;
  log_timestamp: string;
  recommended_action: string;
  target: string;
  root_cause: string | null;
  proposal_source: string | null;
  updated_at: string;
};

export type CommandEntry = {
  timestamp: string;
  service_id: string | null;
  channel: "voice" | "text" | "action";
  role: "user" | "agent";
  text: string;
};

export type TimelineEvent = {
  timestamp: string;
  service_id: string | null;
  kind: string;
  message: string;
};

export type FleetSnapshot = {
  generated_at: string;
  summary: {
    healthy: number;
    active: number;
    critical: number;
    sev2: number;
    sev3: number;
    triage: number;
    layers: { id: string; label: string; active: number; healthy: number }[];
  };
  active_incidents: FleetService[];
  healthy_fleet: FleetService[];
  timeline: TimelineEvent[];
  record: CommandEntry[];
  chaos_remaining: number;
};

export type AnalyzeResult = {
  service_id: string;
  analysis: {
    root_cause: string;
    recommended_action: string;
    target_version_or_value: string;
    source: string;
    fallback_reason?: string;
  };
};

export type RemediateResult = {
  status: string;
  service_id: string;
  action: string;
  target: string;
  verified: boolean;
  error_rate: number;
  health: string;
};
