"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ACTIONS, agentClient } from "@/lib/api";
import { investigateOverMcp } from "@/lib/mcp";
import type { AwsStatus, CommandEntry, FleetService, FleetSnapshot, RepoFinding } from "@/lib/types";
import { speakHyderabad, stopSpeaking } from "@/lib/voice";

type SpeechRec = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
};

function pct(rate: number) {
  if (!rate) return "0.00%";
  return `${(rate * 100).toFixed(1)}%`;
}

function clockLabel(date: Date) {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

function shortTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(11, 19);
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

const SCOPE_LINE =
  "This reply reads the fleet record and the repository you handed over. It does not query live metrics, logs, or traces.";

const ACTION_EFFECT: Record<string, string> = {
  rollback: "puts the earlier release named in Target back into service",
  unseal: "opens the sealed vault so secrets can be read again",
  cert_rotation: "replaces the expired certificate with the Target build",
  dns_flush: "clears the bad DNS answer named in Target",
  scale_pods: "adds capacity so this service can keep up",
  failover: "moves traffic to the standby named in Target",
};

function RepoPane({
  finding,
  busy,
  onApprove,
  onReject,
  onTalk,
}: {
  finding: RepoFinding;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
  onTalk: () => void;
}) {
  const work = finding.work;
  const decided = finding.decision === "approved" || finding.decision === "rejected";
  const badge = finding.decision === "approved" ? "CLEARED" : finding.decision === "rejected" ? "DECLINED" : "PLAN";
  return (
    <>
      <div className="work-scroll">
        <div className="identity">
          <div className="row-top">
            <p className="kicker">Side worker</p>
            <span className={`badge ${finding.decision === "approved" ? "sev2" : "sev3"}`}>{badge}</span>
          </div>
          <h2>{work?.project || finding.repo}</h2>
          <p>{finding.repo}</p>
        </div>
        <p className="impact">{work?.summary || finding.brief || finding.summary}</p>
        {work && (
          <ol className="bom">
            {work.steps.map((step) => (
              <li key={step.id}>
                <b>{step.state === "done" ? "Done" : "Waiting"}</b> {step.text}
              </li>
            ))}
          </ol>
        )}
        {finding.decision === "approved" && (
          <p className="triage-note">Cleared to work. The repository was not changed. Tell me to install when you want that command run.</p>
        )}
        {finding.decision === "rejected" && (
          <p className="triage-note">Declined. The repository was not changed.</p>
        )}
      </div>
      <footer className="decision">
        <div className="actions">
          <button className="ghost" type="button" disabled={busy} onClick={onTalk}>
            Talk about this
          </button>
          <button className="danger" type="button" disabled={busy || decided} onClick={onReject}>
            Decline
          </button>
          <button className="ok" type="button" disabled={busy || !finding.approve_enabled || decided} onClick={onApprove}>
            Approve start
          </button>
        </div>
      </footer>
    </>
  );
}

type DeclareDraft = {
  title: string;
  severity: "" | "SEV-1" | "SEV-2" | "SEV-3";
  details: string;
  notes: string;
  links: string;
  attributes: { name: string; value: string }[];
};

function emptyDeclaration(): DeclareDraft {
  return {
    title: "",
    severity: "",
    details: "",
    notes: "",
    links: "",
    attributes: [{ name: "", value: "" }],
  };
}

function reasonFromCommand(said: string): string {
  return said.replace(/^(please\s+)?(approve|reject|decline)\b[:\s,.-]*/i, "").trim();
}

function sourceLabel(source: string | null) {
  if (source === "bedrock") return "Bedrock";
  if (source === "chaos") return "Chaos catalog";
  if (source === "opening-scene") return "Opening scene";
  if (source === "declared") return "Declared";
  return "Scenario fallback";
}

export default function Home() {
  const [fleet, setFleet] = useState<FleetSnapshot | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [showOverride, setShowOverride] = useState(false);
  const [overrideAction, setOverrideAction] = useState("rollback");
  const [overrideTarget, setOverrideTarget] = useState("");
  const [listening, setListening] = useState(false);
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const [now, setNow] = useState<Date | null>(null);
  const [query, setQuery] = useState("");
  const [record, setRecord] = useState<CommandEntry[]>([]);
  const [draft, setDraft] = useState("");
  const [queue, setQueue] = useState<"open" | "alerts" | "fleet">("open");
  const [aws, setAws] = useState<AwsStatus | null>(null);
  const [awsFailed, setAwsFailed] = useState(false);
  const [muteUntil, setMuteUntil] = useState("");
  const [declareDraft, setDeclareDraft] = useState<DeclareDraft>(emptyDeclaration);
  const [decisionReason, setDecisionReason] = useState("");
  const [rail, setRail] = useState<"record" | "activity">("record");
  const [view, setView] = useState<"overview" | "timeline" | "layers">("overview");
  const [scope, setScope] = useState<"service" | "all">("service");
  const [repoInput, setRepoInput] = useState("");
  const [repoTask, setRepoTask] = useState("");
  const [repoFinding, setRepoFinding] = useState<RepoFinding | null>(null);
  const [repoBusy, setRepoBusy] = useState(false);
  const recognition = useRef<SpeechRec | null>(null);
  const micArmed = useRef(false);
  const analyzeToken = useRef(0);
  const recordEnd = useRef<HTMLDivElement | null>(null);
  const recordStamp = useRef(0);

  const loadFleet = useCallback(async (prefer?: string) => {
    const stamp = recordStamp.current;
    const data = await agentClient.getFleet();
    setFleet(data);
    if (stamp === recordStamp.current) setRecord(data.record ?? []);
    setError(null);
    setOffline(false);
    setSelected((current) => {
      const names = [
        ...data.active_incidents.map((item) => item.service_id),
        ...data.healthy_fleet.map((item) => item.service_id),
      ];
      if (prefer && names.includes(prefer)) return prefer;
      if (current && names.includes(current)) return current;
      return data.active_incidents[0]?.service_id ?? null;
    });
    return data;
  }, []);

  const loadAws = useCallback(async () => {
    try {
      setAws(await agentClient.aws());
      setAwsFailed(false);
    } catch {
      setAwsFailed(true);
    }
  }, []);

  useEffect(() => {
    loadFleet().catch(() => {
      setOffline(true);
      setError("FleetOps agent is not reachable on port 8000.");
    });
    void loadAws();
  }, [loadFleet, loadAws]);

  useEffect(() => {
    setDeclareDraft(emptyDeclaration());
    setDecisionReason("");
  }, [selected]);

  useEffect(() => {
    setNow(new Date());
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const focus =
    fleet?.active_incidents.find((item) => item.service_id === selected) ??
    fleet?.healthy_fleet.find((item) => item.service_id === selected) ??
    null;
  const incident = focus && focus.status !== "HEALTHY" ? focus : null;
  const healthyFocus = focus && focus.status === "HEALTHY" ? focus : null;

  useEffect(() => {
    if (!incident) return;
    setOverrideAction(incident.recommended_action);
    setOverrideTarget(incident.target);
    setShowOverride(false);
    // Reset the drawer only when the commander opens a different target.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incident?.service_id]);

  const fleetRef = useRef(fleet);
  fleetRef.current = fleet;

  useEffect(() => {
    if (!selected) return;
    const current = fleetRef.current;
    const active = current?.active_incidents.some((item) => item.service_id === selected);
    if (current && !active) return;
    const token = ++analyzeToken.current;
    const serviceId = selected;
    setAnalyzing(true);
    void (async () => {
      try {
        const notes = await investigateOverMcp(serviceId);
        for (const note of notes) {
          const saved = await agentClient.note(serviceId, "action", "agent", note);
          if (analyzeToken.current === token) setRecord(saved.record);
        }
      } catch {
        if (analyzeToken.current === token) setError("The MCP tool call did not finish.");
      }
      try {
        await agentClient.analyze(serviceId);
        if (analyzeToken.current !== token) return;
        await loadFleet(serviceId);
      } catch {
        if (analyzeToken.current === token) setAnalyzing(false);
      } finally {
        if (analyzeToken.current === token) setAnalyzing(false);
        void loadAws();
      }
    })();
  }, [selected, loadFleet, loadAws]);

  const healthyGroups = useMemo(() => {
    const items = fleet?.healthy_fleet ?? [];
    const buckets = new Map<string, FleetService[]>();
    for (const layer of fleet?.summary.layers ?? []) buckets.set(layer.label, []);
    for (const item of items) {
      const key = item.layer_label || "Fleet";
      const list = buckets.get(key) ?? [];
      list.push(item);
      buckets.set(key, list);
    }
    return [...buckets.entries()].filter(([, list]) => list.length > 0);
  }, [fleet]);

  const dashboardGroups = useMemo(() => {
    const items = [...(fleet?.active_incidents ?? []), ...(fleet?.healthy_fleet ?? [])];
    const buckets = new Map<string, FleetService[]>();
    for (const layer of fleet?.summary.layers ?? []) buckets.set(layer.label, []);
    for (const item of items) {
      const key = item.layer_label || "Fleet";
      const list = buckets.get(key) ?? [];
      list.push(item);
      buckets.set(key, list);
    }
    return [...buckets.entries()].map(([label, list]) => {
      const ordered = [...list].sort((left, right) => left.service_id.localeCompare(right.service_id));
      return [label, ordered] as const;
    });
  }, [fleet]);

  const visible = fleet?.active_incidents ?? [];

  const mute = async (serviceId: string) => {
    if (!muteUntil) return;
    const until = new Date(muteUntil);
    if (Number.isNaN(until.getTime())) return;
    setBusy(true);
    try {
      await agentClient.silence(serviceId, until.toISOString());
      await loadFleet(serviceId);
    } catch {
      setError("The silence did not reach the agent.");
    } finally {
      setBusy(false);
    }
  };

  const execute = useCallback(
    async (action: string, target: string, reason: string) => {
      if (!incident) return null;
      setBusy(true);
      try {
        const result = await agentClient.remediate(incident.service_id, action, target, reason);
        if (result.status === "NEEDS_REASON") {
          setError("Say why before you approve or override.");
          return null;
        }
        await loadFleet();
        return result;
      } catch {
        setError("Remediation did not reach the agent.");
        return null;
      } finally {
        setBusy(false);
      }
    },
    [incident, loadFleet],
  );

  const approve = useCallback((channel: "voice" | "text" | "action" = "action", userText?: string) => {
    if (!incident || busy) return;
    const action = showOverride ? overrideAction : incident.recommended_action;
    const target = showOverride ? overrideTarget.trim() : incident.target;
    if (showOverride && !target) {
      setError("Name the target before you override.");
      return;
    }
    const reason = (userText ? reasonFromCommand(userText) : decisionReason).trim();
    if (!reason) {
      setError(showOverride ? "Say why you are overriding the suggested action." : "Say why you are approving this.");
      return;
    }
    const serviceId = incident.service_id;
    const said = userText || `${showOverride ? "Override" : "Approve"} ${action} to ${target}: ${reason}`;
    void (async () => {
      try {
        const noted = await agentClient.note(serviceId, channel, "user", said);
        setRecord(noted.record);
      } catch {
        setError("The command record did not save.");
      }
      const result = await execute(action, target, reason);
      if (!result || result.status !== "SUCCESS") return;
      setDecisionReason("");
      try {
        const noted = await agentClient.note(
          serviceId,
          channel,
          "agent",
          `${showOverride ? "Overrode" : "Approved"} ${action} on ${serviceId} to ${target}: ${reason} The service is marked healthy.`,
        );
        setRecord(noted.record);
      } catch {
        setError("The command record did not save.");
      }
    })();
  }, [busy, decisionReason, execute, incident, overrideAction, overrideTarget, showOverride]);

  const reject = useCallback(async (channel: "voice" | "text" | "action" = "action", userText?: string) => {
    if (!incident || busy) return;
    const reason = (userText ? reasonFromCommand(userText) : decisionReason).trim();
    if (!reason) {
      setError("Say why you are rejecting this.");
      return;
    }
    const serviceId = incident.service_id;
    const said = userText || `Reject ${serviceId}: ${reason}`;
    setBusy(true);
    try {
      const noted = await agentClient.note(serviceId, channel, "user", said);
      setRecord(noted.record);
      const result = await agentClient.reject(serviceId, reason);
      if (result.status === "NEEDS_REASON") {
        setError("Say why you are rejecting this.");
        return;
      }
      setDecisionReason("");
      await loadFleet(serviceId);
      const saved = await agentClient.note(
        serviceId,
        channel,
        "agent",
        `Rejected the proposal for ${serviceId}: ${reason} It stays open as triage and is not marked healthy.`,
      );
      setRecord(saved.record);
    } catch {
      setError("Rejection did not reach the agent.");
    } finally {
      setBusy(false);
    }
  }, [busy, decisionReason, incident, loadFleet]);

  const declarationReady = Boolean(declareDraft.title.trim() && declareDraft.severity && declareDraft.details.trim());

  const declare = async (serviceId: string) => {
    if (!declarationReady || !declareDraft.severity) {
      setError("Title, security level, and incident details are required.");
      return;
    }
    const links = declareDraft.links.split(/[\s,]+/).map((item) => item.trim()).filter(Boolean);
    if (links.some((link) => !/^https?:\/\//i.test(link))) {
      setError("Links need to start with http:// or https://.");
      return;
    }
    const attributes = declareDraft.attributes
      .map((row) => ({ name: row.name.trim(), value: row.value.trim() }))
      .filter((row) => row.name || row.value);
    if (attributes.some((row) => !row.name || !row.value)) {
      setError("Each attribute needs a name and a value.");
      return;
    }
    setBusy(true);
    try {
      const result = await agentClient.declare(serviceId, {
        title: declareDraft.title.trim(),
        severity: declareDraft.severity,
        details: declareDraft.details.trim(),
        notes: declareDraft.notes.trim(),
        links,
        attributes,
      });
      if (result.status === "DECLARED") {
        setDeclareDraft(emptyDeclaration());
        setView("overview");
        await loadFleet(result.service?.service_id ?? serviceId);
        setError(null);
      } else if (result.status === "NEEDS_FIELDS") {
        setError("Title, security level, and incident details are required.");
      } else if (result.status === "ALREADY_OPEN") {
        setError(`${serviceId} is already an open incident.`);
      } else {
        setError(`${serviceId} is not in this fleet.`);
      }
    } catch {
      setError("The declaration did not reach the agent.");
    } finally {
      setBusy(false);
    }
  };

  const chaos = async () => {
    setBusy(true);
    try {
      const result = await agentClient.chaos();
      await loadFleet(result.service?.service_id);
    } catch {
      setError("Chaos trigger did not reach the agent.");
    } finally {
      setBusy(false);
    }
  };

  const inspectRepo = async () => {
    const repo = repoInput.trim();
    if (!repo) return;
    setRepoBusy(true);
    try {
      const finding = await agentClient.analyzeRepo(repo, repoTask.trim());
      setRepoFinding(finding);
      if (finding.record) setRecord(finding.record);
      setError(null);
    } catch {
      setError("The repository could not be read.");
    } finally {
      setRepoBusy(false);
    }
  };

  const approveRepo = async () => {
    if (!repoFinding || repoBusy) return;
    setRepoBusy(true);
    try {
      const result = await agentClient.approveRepo(repoFinding.repo);
      setRepoFinding(result.finding);
      if (result.finding.record) setRecord(result.finding.record);
      setError(null);
    } catch {
      setError("The work was not cleared.");
    } finally {
      setRepoBusy(false);
    }
  };

  const rejectRepo = async () => {
    if (!repoFinding || repoBusy) return;
    setRepoBusy(true);
    try {
      const result = await agentClient.rejectRepo(repoFinding.repo);
      setRepoFinding(result.finding);
      if (result.finding.record) setRecord(result.finding.record);
      setError(null);
    } catch {
      setError("The decline was not recorded.");
    } finally {
      setRepoBusy(false);
    }
  };

  const restore = async () => {
    setBusy(true);
    try {
      const data = await agentClient.reset();
      setFleet(data);
      setRecord(data.record ?? []);
      setOffline(false);
      setError(null);
      setSelected(data.active_incidents[0]?.service_id ?? null);
    } catch {
      setError("Opening scene could not be restored.");
    } finally {
      setBusy(false);
    }
  };

  const stopListening = () => {
    micArmed.current = false;
    const rec = recognition.current;
    recognition.current = null;
    if (rec) {
      rec.onresult = null;
      rec.onerror = null;
      rec.onend = null;
      try {
        rec.abort();
      } catch {
        try {
          rec.stop();
        } catch {
          /* already stopped */
        }
      }
    }
    setListening(false);
  };

  const speak = (text: string) => {
    stopListening();
    setVoiceNote("Speaking in your voice");
    void speakHyderabad(text).catch((err: unknown) => {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setVoiceNote("Your voice did not start. Wait for the clone, then press Talk about this.");
    });
  };

  const talkAbout = async (channel: "voice" | "text" = "voice") => {
    if (repoFinding) {
      try {
        recordStamp.current += 1;
        const result = await agentClient.discuss(null, "What would you do next?", channel, repoFinding.repo);
        setRecord(result.record);
        if (channel === "voice") speak(result.reply);
      } catch {
        setError("The command record did not save.");
      }
      return;
    }
    if (!incident) {
      setVoiceNote("Open an incident, then ask about that service.");
      return;
    }
    try {
      recordStamp.current += 1;
      const result = await agentClient.discuss(incident.service_id, "Talk about this service.", channel);
      setRecord(result.record);
      if (channel === "voice") speak(result.reply);
    } catch {
      setError("The command record did not save.");
    }
  };

  const sendChat = async () => {
    const said = draft.trim();
    if (!said) return;
    setDraft("");
    const command = said.toLowerCase().replace(/[.!]+$/, "").trim();
    if (repoFinding && scope !== "all") {
      const question = command.includes("?") || command.startsWith("what ") || command.startsWith("how ");
      if (!question && /^(please\s+)?approve\b/.test(command) && repoFinding.approve_enabled) {
        void approveRepo();
        return;
      }
      if (!question && /^(please\s+)?(reject|decline)\b/.test(command)) {
        void rejectRepo();
        return;
      }
      try {
        recordStamp.current += 1;
        const result = await agentClient.discuss(null, said, "text", repoFinding.repo);
        setRecord(result.record);
      } catch {
        setError("The message was not saved.");
      }
      return;
    }
    if (incident && /^(please\s+)?approve\b/.test(command) && !command.includes("?")) {
      approve("text", said);
      return;
    }
    if (incident && /^(please\s+)?reject\b/.test(command) && !command.includes("?")) {
      void reject("text", said);
      return;
    }
    try {
      const serviceId = incident?.service_id ?? null;
      recordStamp.current += 1;
      const result = await agentClient.discuss(serviceId, said, "text");
      setRecord(result.record);
      if (result.scope === "all") setScope("all");
    } catch {
      setError("The message was not saved.");
    }
  };

  const askByVoice = async (said: string) => {
    stopSpeaking();
    try {
      const serviceId = repoFinding && scope !== "all" ? null : incident?.service_id ?? null;
      const repo = repoFinding && scope !== "all" ? repoFinding.repo : null;
      recordStamp.current += 1;
      const result = await agentClient.discuss(serviceId, said, "voice", repo);
      setRecord(result.record);
      if (result.scope === "all") setScope("all");
      setVoiceNote("Saved in the command record.");
    } catch {
      setError("The message was not saved.");
    }
  };

  const toggleVoice = () => {
    if (listening || recognition.current) {
      stopListening();
      setVoiceNote("Microphone off");
      return;
    }
    stopSpeaking();
    const ctor = (
      window as Window & {
        SpeechRecognition?: new () => SpeechRec;
        webkitSpeechRecognition?: new () => SpeechRec;
      }
    ).SpeechRecognition || (
      window as Window & { webkitSpeechRecognition?: new () => SpeechRec }
    ).webkitSpeechRecognition;
    if (!ctor) {
      setVoiceNote("This browser has no Web Speech API.");
      return;
    }
    const rec = new ctor();
    rec.lang = "en-IN";
    rec.continuous = false;
    rec.interimResults = false;
    rec.onresult = (event) => {
      if (!micArmed.current) return;
      micArmed.current = false;
      const said = event.results[0][0].transcript.toLowerCase();
      stopListening();
      setVoiceNote(said);
      if (said.includes("approve")) approve("voice", said);
      else if (said.includes("reject")) void reject("voice", said);
      else void askByVoice(said);
    };
    rec.onend = () => {
      if (recognition.current === rec) stopListening();
    };
    rec.onerror = () => {
      if (recognition.current === rec) {
        stopListening();
        setVoiceNote("Did not catch that. Press the microphone and say one word.");
      }
    };
    recognition.current = rec;
    micArmed.current = true;
    setListening(true);
    setVoiceNote("Listening… say one word");
    try {
      rec.start();
    } catch {
      stopListening();
      setVoiceNote("Microphone did not start.");
    }
  };

  useEffect(() => {
    return () => {
      micArmed.current = false;
      const rec = recognition.current;
      recognition.current = null;
      if (rec) {
        rec.onresult = null;
        rec.onend = null;
        rec.onerror = null;
        try {
          rec.abort();
        } catch {
          /* already stopped */
        }
      }
      stopSpeaking();
    };
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.code !== "Space" || event.repeat) return;
      const tag = (event.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || tag === "BUTTON") return;
      if (!decisionReason.trim()) return;
      event.preventDefault();
      approve("action");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [approve, decisionReason]);

  const summary = fleet?.summary;
  const shownRecord = useMemo(() => {
    if (scope === "all") return record;
    if (repoFinding?.record_id) return record.filter((entry) => entry.service_id === repoFinding.record_id);
    if (!incident) return record;
    return record.filter((entry) => entry.service_id === incident.service_id);
  }, [incident, record, repoFinding, scope]);
  const serviceTimeline = useMemo(() => {
    const events = fleet?.timeline ?? [];
    if (scope === "all" || !incident) return events;
    return events.filter((event) => event.service_id === incident.service_id);
  }, [fleet, incident, scope]);

  useEffect(() => {
    recordEnd.current?.scrollIntoView({ block: "end" });
  }, [shownRecord]);

  const fleetGroups = healthyGroups
    .map(([label, items]) => {
      const needle = query.trim().toLowerCase();
      const matched = needle
        ? items.filter((item) => `${item.service_id} ${item.version} ${item.layer_label}`.toLowerCase().includes(needle))
        : items;
      return [label, matched] as const;
    })
    .filter(([, items]) => items.length > 0);

  return (
    <div className="cc">
      <header className="appbar">
        <div className="brand">
          <img className="mark" src="/fleetops-logo.png" alt="" />
          <div>
            <p className="kicker">Fleet Commander</p>
            <h1>FleetOps</h1>
          </div>
        </div>
        <div className="kpis" aria-label="Fleet summary">
          <div className="kpi sev1">
            <span>SEV-1</span>
            <b>{summary?.critical ?? "—"}</b>
          </div>
          <div className="kpi">
            <span>Open</span>
            <b>{summary?.active ?? "—"}</b>
          </div>
          <div className="kpi">
            <span>SEV-2 / 3</span>
            <b>{summary ? summary.sev2 + summary.sev3 : "—"}</b>
          </div>
          <div className="kpi ok">
            <span>Healthy</span>
            <b>{summary?.healthy ?? "—"}</b>
          </div>
        </div>
        <div className="app-tools">
          <span className={offline ? "status off" : "status"}>
            <i />
            {offline ? "Agent offline" : "Agent live"}
          </span>
          <span className="clock">{now ? clockLabel(now) : "—"}</span>
          {voiceNote && <span className="voice-status">{voiceNote}</span>}
          <button className="ghost" type="button" onClick={chaos} disabled={busy}>
            Simulate chaos
          </button>
          <button className="ghost" type="button" onClick={() => void restore()} disabled={busy}>
            Reset scene
          </button>
        </div>
      </header>
      {error && <p className="banner">{error}</p>}

      <main className="workspace">
        <section className="panel queue">
          <div className="seg" role="tablist" aria-label="Fleet lists">
            <button type="button" className={queue === "open" ? "on" : ""} onClick={() => setQueue("open")}>
              Open <em>{summary?.active ?? 0}</em>
            </button>
            <button type="button" className={queue === "alerts" ? "on" : ""} onClick={() => setQueue("alerts")}>
              Alerts <em>{summary?.active ?? 0}</em>
            </button>
            <button type="button" className={queue === "fleet" ? "on" : ""} onClick={() => setQueue("fleet")}>
              Fleet <em>{summary?.healthy ?? 0}</em>
            </button>
          </div>
          {queue === "alerts" && (
            <ul className="rules">
              {(fleet?.rules ?? [
                "Error rate at or above 20%, or a CRITICAL log, is SEV-1.",
                "Error rate at or above 5% is SEV-2.",
                "Otherwise the alert is SEV-3.",
              ]).map((rule) => (
                <li key={rule}>{rule}</li>
              ))}
            </ul>
          )}
          {queue === "fleet" && (
            <input
              className="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter healthy services"
              aria-label="Filter healthy services"
            />
          )}
          <div className="list">
            {queue === "open" && !fleet && <p className="empty">Loading the fleet…</p>}
            {queue === "open" && fleet && visible.length === 0 && (
              <p className="empty">No open incidents. Fixed services are on the Fleet tab.</p>
            )}
            {queue === "open" &&
              visible.map((item) => (
                <IncidentRow
                  key={item.service_id}
                  item={item}
                  selected={selected === item.service_id}
                  onSelect={() => {
                    setRepoFinding(null);
                    setView("overview");
                    setSelected(item.service_id);
                  }}
                />
              ))}
            {queue === "alerts" && visible.length === 0 && <p className="empty">No alerts. Open incidents are the alerts.</p>}
            {queue === "alerts" &&
              visible.map((item) => (
                <button
                  key={item.service_id}
                  type="button"
                  className={selected === item.service_id ? "alert-row on" : "alert-row"}
                  onClick={() => {
                    setRepoFinding(null);
                    setView("overview");
                    setSelected(item.service_id);
                  }}
                >
                  <b>{item.service_id}</b>
                  <span className={`badge ${item.severity === "SEV-1" ? "sev1" : item.severity === "SEV-3" ? "sev3" : "sev2"}`}>
                    {item.severity}
                  </span>
                  <span>{pct(item.error_rate)}</span>
                  <small>{item.recommended_action}</small>
                </button>
              ))}
            {queue === "fleet" && fleetGroups.length === 0 && <p className="empty">No healthy services match that filter.</p>}
            {queue === "fleet" &&
              fleetGroups.map(([label, items]) => (
                <div className="layer" key={label}>
                  <p>{label}</p>
                  {items.map((item) => (
                    <button
                      className={selected === item.service_id ? "fleet-row on" : "fleet-row"}
                      key={item.service_id}
                      type="button"
                      onClick={() => {
                        setRepoFinding(null);
                        setView("overview");
                        setSelected(item.service_id);
                      }}
                    >
                      <i />
                      <b>{item.service_id}</b>
                      <small>{pct(item.observed_rate ?? 0)} · {item.version}</small>
                      {item.forecast && <span className="badge forecast">{item.forecast}</span>}
                    </button>
                  ))}
                </div>
              ))}
          </div>
        </section>

        <section className="panel work">
          <div className="viewbar" role="tablist" aria-label="Incident">
            <button type="button" className={view === "overview" ? "on" : ""} onClick={() => setView("overview")}>Overview</button>
            <button type="button" className={view === "timeline" ? "on" : ""} onClick={() => setView("timeline")}>Timeline</button>
            <button type="button" className={view === "layers" ? "on" : ""} onClick={() => setView("layers")}>Dashboard</button>
          </div>
          <div className="stage">
          {view === "layers" ? (
            <Dashboard
              groups={dashboardGroups}
              selected={selected}
              onSelect={(serviceId) => {
                setRepoFinding(null);
                setView("overview");
                setSelected(serviceId);
              }}
            />
          ) : view === "timeline" ? (
            <div className="work-scroll timeline">
              <h2>{incident?.service_id ?? healthyFocus?.service_id ?? "Fleet"}</h2>
              {serviceTimeline.length === 0 && <p className="empty">No steps recorded for this service yet.</p>}
              {serviceTimeline.map((event, index) => (
                <div className="step" key={`${event.timestamp}-${index}`}>
                  <time>{shortTime(event.timestamp)}</time>
                  <p>{event.message}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="detail">
          {repoFinding ? (
            <RepoPane
              finding={repoFinding}
              busy={repoBusy}
              onApprove={() => void approveRepo()}
              onReject={() => void rejectRepo()}
              onTalk={() => void talkAbout("text")}
            />
          ) : healthyFocus ? (
            <>
            <div className="work-scroll doc">
              <div className="identity">
                <p className="kicker">{healthyFocus.layer_label}</p>
                <h2>{healthyFocus.service_id}</h2>
                {healthyFocus.forecast && <p className="badge forecast">{healthyFocus.forecast}</p>}
              </div>
              <h3>Status</h3>
              <p className="lead">{healthyFocus.forecast ? "The error rate is climbing and is still under 5%." : "Healthy. No fix is waiting."}</p>
              <label className="report">
                <span>Title</span>
                <input
                  value={declareDraft.title}
                  maxLength={120}
                  placeholder="Name this incident"
                  onChange={(event) => setDeclareDraft({ ...declareDraft, title: event.target.value })}
                />
              </label>
              <div className="report">
                <span>Security level</span>
                <div className="levels">
                  {(["SEV-1", "SEV-2", "SEV-3"] as const).map((level) => (
                    <button
                      key={level}
                      type="button"
                      className={declareDraft.severity === level ? `on ${level === "SEV-1" ? "sev1" : level === "SEV-3" ? "sev3" : "sev2"}` : ""}
                      onClick={() => setDeclareDraft({ ...declareDraft, severity: level })}
                    >
                      {level}
                    </button>
                  ))}
                </div>
              </div>
              <label className="report">
                <span>Incident details</span>
                <textarea
                  value={declareDraft.details}
                  maxLength={1000}
                  placeholder="What happened, who is affected, and what you have already seen."
                  onChange={(event) => setDeclareDraft({ ...declareDraft, details: event.target.value })}
                />
              </label>
              <div className="report">
                <span>Attributes</span>
                {declareDraft.attributes.map((row, index) => (
                  <div className="attr-row" key={index}>
                    <input
                      value={row.name}
                      maxLength={80}
                      placeholder="Name"
                      aria-label={`Attribute ${index + 1} name`}
                      onChange={(event) => {
                        const attributes = declareDraft.attributes.map((item, itemIndex) =>
                          itemIndex === index ? { ...item, name: event.target.value } : item,
                        );
                        setDeclareDraft({ ...declareDraft, attributes });
                      }}
                    />
                    <input
                      value={row.value}
                      maxLength={160}
                      placeholder="Value"
                      aria-label={`Attribute ${index + 1} value`}
                      onChange={(event) => {
                        const attributes = declareDraft.attributes.map((item, itemIndex) =>
                          itemIndex === index ? { ...item, value: event.target.value } : item,
                        );
                        setDeclareDraft({ ...declareDraft, attributes });
                      }}
                    />
                  </div>
                ))}
                {declareDraft.attributes.length < 8 && (
                  <button
                    className="ghost"
                    type="button"
                    onClick={() => setDeclareDraft({ ...declareDraft, attributes: [...declareDraft.attributes, { name: "", value: "" }] })}
                  >
                    Add attribute
                  </button>
                )}
              </div>
              <label className="report">
                <span>Notes</span>
                <textarea
                  value={declareDraft.notes}
                  maxLength={1000}
                  placeholder="Anything else the next person should know."
                  onChange={(event) => setDeclareDraft({ ...declareDraft, notes: event.target.value })}
                />
              </label>
              <label className="report">
                <span>Links</span>
                <textarea
                  value={declareDraft.links}
                  placeholder="One http:// or https:// link per line."
                  onChange={(event) => setDeclareDraft({ ...declareDraft, links: event.target.value })}
                />
              </label>
              <p className="hint">Title, security level, and incident details are required. Attributes, notes, and links are kept when you add them.</p>
              <div className="facts">
                <div>
                  <span>Error rate</span>
                  <b>{pct(healthyFocus.observed_rate ?? 0)}</b>
                </div>
                <div>
                  <span>Live version</span>
                  <b>{healthyFocus.version}</b>
                </div>
                <div>
                  <span>Status</span>
                  <b>{healthyFocus.status}</b>
                </div>
              </div>
              <MuteControl
                until={muteUntil}
                silenced={healthyFocus.silenced_until}
                busy={busy}
                onUntil={setMuteUntil}
                onMute={() => void mute(healthyFocus.service_id)}
              />
            </div>
            <footer className="decision">
              <div className="actions">
                <button className="ok" type="button" disabled={busy || !declarationReady} onClick={() => void declare(healthyFocus.service_id)}>
                  Declare incident
                </button>
              </div>
            </footer>
            </>
          ) : !incident ? (
            <div className="blank">
              <p className="kicker">Fleet</p>
              <h2>Choose a service</h2>
              <ol>
                <li>Open is the decision list. Alerts is the same incident with the rule and the suggested action.</li>
                <li>Fleet groups the healthy services by layer. A rising rate shows approaching SEV-2.</li>
                <li>The page that opens here is the investigation. Approve or reject stays at the bottom.</li>
              </ol>
            </div>
          ) : (
            <>
              <div className="work-scroll doc">
                <div className="identity">
                  <p className="kicker">
                    {incident.declaration ? `${incident.layer_label} · ${incident.service_id}` : incident.layer_label}
                    {" · "}
                    <span className={incident.status === "TRIAGE" ? "badge triage" : incident.severity === "SEV-1" ? "badge sev1" : incident.severity === "SEV-3" ? "badge sev3" : "badge sev2"}>
                      {incident.status === "TRIAGE" ? "TRIAGE" : incident.severity}
                    </span>
                  </p>
                  <h2>{incident.declaration?.title ?? incident.service_id}</h2>
                  {incident.jira_key && <p className="jira">Jira {incident.jira_key}</p>}
                </div>
                {incident.declaration && (
                  <>
                    <h3>Incident details</h3>
                    <p className="lead">{incident.declaration.details}</p>
                    {incident.declaration.attributes.length > 0 && (
                      <>
                        <h3>Attributes</h3>
                        <table className="attrs">
                          <tbody>
                            {incident.declaration.attributes.map((row) => (
                              <tr key={`${row.name}-${row.value}`}>
                                <th>{row.name}</th>
                                <td>{row.value}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </>
                    )}
                    {incident.declaration.notes && (
                      <>
                        <h3>Notes</h3>
                        <p className="lead">{incident.declaration.notes}</p>
                      </>
                    )}
                    {incident.declaration.links.length > 0 && (
                      <>
                        <h3>Links</h3>
                        <ul className="links">
                          {incident.declaration.links.map((link) => (
                            <li key={link}>
                              <a href={link} target="_blank" rel="noreferrer">{link}</a>
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                  </>
                )}
                <h3>What failed</h3>
                <p className="lead">
                  {pct(incident.error_rate)} errors on {incident.version}. {incident.issue_type}.
                </p>
                <h3>Cause</h3>
                <p className="lead">
                  {incident.root_cause ?? incident.impact_summary}. Source: {analyzing ? "Consulting Bedrock" : sourceLabel(incident.proposal_source)}.
                  {incident.fallback_reason ? ` ${shortAwsError(incident.fallback_reason)}` : ""}
                </p>
                <h3>What to do</h3>
                <p className="lead">
                  {(incident.recommended_action.slice(0, 1).toUpperCase() + incident.recommended_action.slice(1))} to {incident.target}. {ACTION_EFFECT[incident.recommended_action] ?? "Runs the suggested action"}.
                </p>
                <div className="facts">
                  <div>
                    <span>Error rate</span>
                    <b className={incident.error_rate >= 0.2 ? "bad" : ""}>{pct(incident.error_rate)}</b>
                  </div>
                  <div>
                    <span>Live version</span>
                    <b>{incident.version}</b>
                  </div>
                  <div>
                    <span>Fault release</span>
                    <b className="bad">{incident.fault_version}</b>
                  </div>
                  <div>
                    <span>Suggested target</span>
                    <b className="good">{incident.target}</b>
                  </div>
                </div>
                <h3>Log</h3>
                <p className="logs">
                  <span className="ts">[{incident.log_level}] {shortTime(incident.log_timestamp)} </span>
                  {incident.log_message}
                </p>
                {incident.status === "TRIAGE" && (
                  <p className="triage-note">This proposal was rejected. It is still broken until you approve a fix.</p>
                )}
                {incident.decision?.reason && (
                  <>
                    <h3>Why it was rejected</h3>
                    <p className="lead">{incident.decision.reason}</p>
                  </>
                )}
                <MuteControl
                  until={muteUntil}
                  silenced={incident.silenced_until}
                  busy={busy}
                  onUntil={setMuteUntil}
                  onMute={() => void mute(incident.service_id)}
                />
                <StatusStrip
                  status={aws}
                  failed={awsFailed}
                  calls={fleet?.model_calls ?? 0}
                  cap={fleet?.model_cap ?? 40}
                />
              </div>
              <footer className="decision">
                <label className="report decision-why">
                  <span>Why</span>
                  <textarea
                    value={decisionReason}
                    maxLength={1000}
                    placeholder={showOverride ? "Why this action instead of the suggested one." : "Why you are approving or rejecting this."}
                    onChange={(event) => setDecisionReason(event.target.value)}
                  />
                </label>
                {showOverride && (
                  <div className="override">
                    <label>
                      Action
                      <select value={overrideAction} onChange={(event) => setOverrideAction(event.target.value)}>
                        {ACTIONS.map((action) => (
                          <option key={action} value={action}>{action}</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Target
                      <input value={overrideTarget} onChange={(event) => setOverrideTarget(event.target.value)} />
                    </label>
                  </div>
                )}
                <div className="actions">
                  <button className="ghost" type="button" onClick={() => void talkAbout("voice")}>
                    Talk about this
                  </button>
                  <button
                    className="ghost"
                    type="button"
                    onClick={() => {
                      setShowOverride((open) => {
                        if (!open) {
                          setOverrideAction(incident.recommended_action);
                          setOverrideTarget(incident.target);
                        }
                        return !open;
                      });
                    }}
                  >
                    {showOverride ? "Close override" : "Override"}
                  </button>
                  <button className="danger" type="button" disabled={busy || incident.status === "TRIAGE" || !decisionReason.trim()} onClick={() => void reject("action")}>
                    Reject
                  </button>
                  <button className="ok" type="button" disabled={busy || !decisionReason.trim() || (showOverride && !overrideTarget.trim())} onClick={() => approve("action")}>
                    {showOverride ? `Execute ${overrideAction}` : `Approve ${incident.recommended_action}`}
                  </button>
                </div>
              </footer>
            </>
          )}
            </div>
          )}
          </div>
        </section>

        <section className="panel chatter">
          <form
            className="repo-ask"
            onSubmit={(event) => {
              event.preventDefault();
              void inspectRepo();
            }}
          >
            <input
              value={repoInput}
              onChange={(event) => setRepoInput(event.target.value)}
              placeholder="Repository path or git URL"
              aria-label="Repository path or git URL"
            />
            <input
              value={repoTask}
              onChange={(event) => setRepoTask(event.target.value)}
              placeholder="Task, optional"
              aria-label="Task"
            />
            <button type="submit" disabled={repoBusy || !repoInput.trim()}>{repoBusy ? "Reading…" : "Start"}</button>
          </form>
          {repoBusy && <p className="empty">Reading the project instructions and dependency files.</p>}
          <div className="seg" role="tablist" aria-label="Knowledge">
            <button type="button" className={rail === "record" ? "on" : ""} onClick={() => setRail("record")}>
              Record <em>{shownRecord.length}</em>
            </button>
            <button type="button" className={rail === "activity" ? "on" : ""} onClick={() => setRail("activity")}>
              Activity <em>{serviceTimeline.length}</em>
            </button>
          </div>
          {rail === "record" ? (
            <>
              <div className="scope">
                <button type="button" className={scope === "service" ? "on" : ""} onClick={() => setScope("service")}>
                  {repoFinding ? "This repository" : "This service"}
                </button>
                <button type="button" className={scope === "all" ? "on" : ""} onClick={() => setScope("all")}>
                  Entire fleet
                </button>
              </div>
              <div className="thread" aria-live="polite">
                {shownRecord.length === 0 && (
                  <p className="empty">
                    {repoFinding
                      ? "Give FleetOps the task, or ask what it would do next. It will not install or edit until you approve."
                      : incident
                      ? `Nothing saved yet for ${incident.service_id}. Ask below, or press Talk about this. Voice and text are both kept.`
                      : "Open a service, then ask. Every question and answer is kept."}
                  </p>
                )}
                {shownRecord.map((entry, index) => (
                  <article className={`bubble ${entry.role}`} key={`${entry.timestamp}-${index}`}>
                    <p className="who">
                      <span>{entry.role === "user" ? "Operator" : "FleetOps"}</span>
                      <span>{entry.channel}</span>
                      <time>{shortTime(entry.timestamp)}</time>
                    </p>
                    {entry.coworker ? (
                      <div className="coworker">
                        <p><b>Situation</b> {entry.coworker.situation}</p>
                        <p><b>Insight</b> {entry.coworker.insight}</p>
                        <p><b>Knowledge</b> {entry.coworker.knowledge}</p>
                        <p>
                          <b>Token budget</b> {entry.coworker.token_budget.calls} model calls, {entry.coworker.token_budget.remaining} remaining of {entry.coworker.token_budget.cap}.
                        </p>
                        <p className="scope-note">{entry.coworker.scope}</p>
                      </div>
                    ) : (
                      <p>{entry.text}</p>
                    )}
                  </article>
                ))}
                <div ref={recordEnd} />
              </div>
              <form
                className="composer"
                onSubmit={(event) => {
                  event.preventDefault();
                  void sendChat();
                }}
              >
                <input
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder={
                    repoFinding && scope !== "all"
                      ? "Tell FleetOps the task, or ask what it would do next"
                      : scope === "all"
                      ? "Ask about the fleet or a service"
                      : incident
                      ? `Ask about ${incident.service_id}, or how this board works`
                      : "Ask what's open, or how this board works"
                  }
                  aria-label="Message FleetOps"
                />
                <button
                  className={`mic ${listening ? "on" : ""}`}
                  type="button"
                  onClick={toggleVoice}
                  aria-label={listening ? "Stop microphone" : "Microphone"}
                  title={listening ? "Listening" : "Speak a question"}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M12 15a3 3 0 0 0 3-3V7a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3z" />
                    <path d="M6 11a1 1 0 0 0-2 0 8 8 0 0 0 7 7.93V21H9a1 1 0 0 0 0 2h6a1 1 0 0 0 0-2h-2v-2.07A8 8 0 0 0 20 11a1 1 0 0 0-2 0 6 6 0 0 1-12 0z" />
                  </svg>
                </button>
                <button className="ok" type="submit" disabled={!draft.trim()}>
                  Send
                </button>
              </form>
            </>
          ) : (
            <div className="thread activity">
              {serviceTimeline.length === 0 && <p className="empty">No steps recorded for this view yet.</p>}
              {serviceTimeline.map((event, index) => (
                <div className="step" key={`${event.timestamp}-${index}`}>
                  <time>{shortTime(event.timestamp)}</time>
                  <p>{event.message}</p>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function StatusStrip({
  status,
  failed,
  calls,
  cap,
}: {
  status: AwsStatus | null;
  failed: boolean;
  calls: number;
  cap: number;
}) {
  if (failed || !status) {
    return (
      <aside className="aws">
        <p>{failed ? "AWS status is not reachable." : "Reading AWS status…"} · {calls}/{cap} model calls</p>
        <p className="scope-note">{SCOPE_LINE}</p>
      </aside>
    );
  }
  const last = status.last_bedrock;
  const source =
    last?.source === "bedrock"
      ? "Bedrock answered"
      : last?.source === "scenario-fallback"
        ? "Scenario fallback"
        : last?.source === "pending"
          ? "InvokeModel in progress"
          : "No InvokeModel attempt yet";
  const group = status.log_group_status.exists
    ? `${status.log_group} exists`
    : status.log_group_status.error
      ? `${status.log_group}: ${shortAwsError(status.log_group_status.error)}`
      : `${status.log_group} was not returned by DescribeLogGroups`;
  return (
    <aside className="aws">
      <p>
        {group} · {status.app_runner_url.replace("https://", "")} · {source}
        {last?.fallback_reason ? ` · ${shortAwsError(last.fallback_reason)}` : ""} · {calls}/{cap}
      </p>
      <p className="scope-note">{SCOPE_LINE}</p>
    </aside>
  );
}

function shortAwsError(reason: string) {
  if (reason.includes("002")) return "Error 002: this account is not allowed to call Bedrock models.";
  if (reason.includes("AccessDenied") || reason.includes("not authorized")) return "DescribeLogGroups is not allowed for this user.";
  const compact = reason.replace(/\s+/g, " ").trim();
  return compact.length > 140 ? `${compact.slice(0, 137)}…` : compact;
}

function MuteControl({
  until,
  silenced,
  busy,
  onUntil,
  onMute,
}: {
  until: string;
  silenced?: string | null;
  busy: boolean;
  onUntil: (value: string) => void;
  onMute: () => void;
}) {
  return (
    <div className="mute">
      <label>
        Mute until
        <input type="datetime-local" value={until} onChange={(event) => onUntil(event.target.value)} />
      </label>
      <button className="ghost" type="button" disabled={busy || !until} onClick={onMute}>
        Mute
      </button>
      {silenced && <p>Muted until {silenced}</p>}
    </div>
  );
}

function Dashboard({
  groups,
  selected,
  onSelect,
}: {
  groups: (readonly [string, FleetService[]])[];
  selected: string | null;
  onSelect: (serviceId: string) => void;
}) {
  return (
    <div className="dashboard">
      {groups.map(([label, items]) => {
        const open = items.filter((item) => item.status !== "HEALTHY").length;
        return (
          <section key={label}>
            <h3>{label} <em>{open} open</em></h3>
            <div className="cells">
              {items.map((item) => {
                const broken = item.status !== "HEALTHY";
                const rate = broken ? item.error_rate : item.observed_rate ?? 0;
                return (
                  <button
                    key={item.service_id}
                    type="button"
                    className={`cell ${broken ? "open" : "healthy"} ${selected === item.service_id ? "on" : ""}`}
                    onClick={() => onSelect(item.service_id)}
                  >
                    <b>{item.service_id}</b>
                    <span>{pct(rate)}</span>
                    <small>{broken ? "Open" : "Healthy"}</small>
                    {item.forecast && <span className="badge forecast">{item.forecast}</span>}
                  </button>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function IncidentRow({
  item,
  selected,
  onSelect,
}: {
  item: FleetService;
  selected: boolean;
  onSelect: () => void;
}) {
  const badge =
    item.status === "TRIAGE" ? "triage" : item.severity === "SEV-1" ? "sev1" : item.severity === "SEV-3" ? "sev3" : "sev2";
  return (
    <button type="button" className={`target ${selected ? "selected" : ""} ${badge}`} onClick={onSelect}>
      <span className="rail-mark" aria-hidden />
      <span className="svc">{item.service_id}</span>
      <span className={`badge ${badge}`}>{item.status === "TRIAGE" ? "TRIAGE" : item.severity}</span>
      <span className="issue">{item.declaration?.title ?? item.issue_type}</span>
      <span className="path">
        {pct(item.error_rate)} · {item.recommended_action} → {item.target}
      </span>
    </button>
  );
}
