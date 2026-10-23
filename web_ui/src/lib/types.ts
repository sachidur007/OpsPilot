export type IncidentAttribute = {
  name: string;
  value: string;
};

export type IncidentDecision = {
  kind: "reject";
  reason: string;
};

export type IncidentDeclaration = {
  title: string;
  severity: "SEV-1" | "SEV-2" | "SEV-3";
  details: string;
  notes?: string | null;
  links: string[];
  attributes: IncidentAttribute[];
};

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
  declaration?: IncidentDeclaration | null;
  decision?: IncidentDecision | null;
  fallback_reason?: string | null;
  silenced_until?: string | null;
  jira_key?: string | null;
  forecast?: string | null;
  observed_rate?: number;
  updated_at: string;
};

export type TokenBudget = {
  calls: number;
  cap: number;
  remaining: number;
};

export type CoworkerParts = {
  situation: string;
  insight: string;
  knowledge: string;
  token_budget: TokenBudget;
  scope: string;
};

export type CommandEntry = {
  timestamp: string;
  service_id: string | null;
  channel: "voice" | "text" | "action";
  role: "user" | "agent";
  text: string;
  coworker?: CoworkerParts;
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
  rules?: string[];
  model_calls?: number;
  model_cap?: number;
  last_bedrock?: {
    model_id?: string;
    source?: string;
    fallback_reason?: string | null;
  } | null;
};

export type AwsStatus = {
  model_id: string;
  last_bedrock: {
    model_id?: string;
    source?: string;
    fallback_reason?: string | null;
  } | null;
  log_group: string;
  log_group_status: { exists: boolean; error: string | null };
  app_runner_url: string;
};

export type BomEntry = {
  path: string;
  ecosystem: string;
  name: string;
  version: string | null;
};

export type RepoFinding = {
  target_type: "repo";
  repo: string;
  status: "verified" | "unverified";
  source: "playbook" | "unverified";
  summary: string;
  advisories: string[];
  provision: string | null;
  target: string | null;
  evidence: BomEntry[];
  bom: BomEntry[];
  approve_enabled: boolean;
  decision: "approved" | "rejected" | null;
  provision_path?: string | null;
  work_path?: string | null;
  brief?: string;
  record_id?: string;
  work?: WorkOrder;
  record?: CommandEntry[];
};

export type WorkOrder = {
  mission: string;
  project: string;
  summary: string;
  instructions: { path: string; title: string; excerpt: string }[];
  depends_on: string;
  install: string[] | null;
  steps: { id: string; state: "done" | "waiting"; text: string }[];
  permission: string;
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
