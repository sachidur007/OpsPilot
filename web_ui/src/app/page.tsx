"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ACTIONS, agentClient } from "@/lib/api";
import type { CommandEntry, FleetService, FleetSnapshot } from "@/lib/types";
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

const ACTION_EFFECT: Record<string, string> = {
  rollback: "puts the earlier release named in Target back into service",
  unseal: "opens the sealed vault so secrets can be read again",
  cert_rotation: "replaces the expired certificate with the Target build",
  dns_flush: "clears the bad DNS answer named in Target",
  scale_pods: "adds capacity so this service can keep up",
  failover: "moves traffic to the standby named in Target",
};

function sourceLabel(source: string | null) {
  if (source === "bedrock") return "Bedrock";
  if (source === "chaos") return "Chaos catalog";
  if (source === "opening-scene") return "Opening scene";
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
  const [queue, setQueue] = useState<"open" | "fleet">("open");
  const [rail, setRail] = useState<"record" | "activity">("record");
  const [scope, setScope] = useState<"service" | "all">("service");
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
      const names = data.active_incidents.map((item) => item.service_id);
      if (prefer && names.includes(prefer)) return prefer;
      if (current && names.includes(current)) return current;
      return data.active_incidents[0]?.service_id ?? null;
    });
    return data;
  }, []);

  useEffect(() => {
    loadFleet().catch(() => {
      setOffline(true);
      setError("OpsPilot agent is not reachable on port 8000.");
    });
  }, [loadFleet]);

  useEffect(() => {
    setNow(new Date());
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const incident = fleet?.active_incidents.find((item) => item.service_id === selected) ?? null;

  useEffect(() => {
    if (!incident) return;
    setOverrideAction(incident.recommended_action);
    setOverrideTarget(incident.target);
    setShowOverride(false);
    // Reset the drawer only when the commander opens a different target.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incident?.service_id]);

  useEffect(() => {
    if (!selected) return;
    const token = ++analyzeToken.current;
    setAnalyzing(true);
    agentClient
      .analyze(selected)
      .then(async () => {
        if (analyzeToken.current !== token) return;
        const data = await loadFleet(selected);
        if (analyzeToken.current !== token) return;
        void data;
      })
      .catch(() => {
        if (analyzeToken.current === token) {
          setAnalyzing(false);
        }
      })
      .finally(() => {
        if (analyzeToken.current === token) setAnalyzing(false);
      });
  }, [selected, loadFleet]);

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

  const visible = fleet?.active_incidents ?? [];

  const execute = useCallback(
    async (action: string, target: string) => {
      if (!incident) return;
      setBusy(true);
      try {
        await agentClient.remediate(incident.service_id, action, target);
        await loadFleet();
      } catch {
        setError("Remediation did not reach the agent.");
      } finally {
        setBusy(false);
      }
    },
    [incident, loadFleet],
  );

  const approve = useCallback((channel: "voice" | "text" | "action" = "action", userText?: string) => {
    if (!incident || busy) return;
    const action = showOverride ? overrideAction : incident.recommended_action;
    const target = showOverride ? overrideTarget : incident.target;
    const serviceId = incident.service_id;
    const said = userText || (channel === "voice" ? "approve" : `Approve ${action} to ${target}`);
    void (async () => {
      try {
        const noted = await agentClient.note(serviceId, channel, "user", said);
        setRecord(noted.record);
      } catch {
        setError("The command record did not save.");
      }
      await execute(action, target);
      try {
        const noted = await agentClient.note(
          serviceId,
          channel,
          "agent",
          `Approved ${action} on ${serviceId} to ${target}. The service is marked healthy.`,
        );
        setRecord(noted.record);
      } catch {
        setError("The command record did not save.");
      }
    })();
  }, [busy, execute, incident, overrideAction, overrideTarget, showOverride]);

  const reject = useCallback(async (channel: "voice" | "text" | "action" = "action", userText?: string) => {
    if (!incident || busy) return;
    const serviceId = incident.service_id;
    const said = userText || (channel === "voice" ? "reject" : `Reject ${serviceId}`);
    setBusy(true);
    try {
      const noted = await agentClient.note(serviceId, channel, "user", said);
      setRecord(noted.record);
      await agentClient.reject(serviceId);
      await loadFleet(serviceId);
      const saved = await agentClient.note(
        serviceId,
        channel,
        "agent",
        `Rejected the proposal for ${serviceId}. It stays open as triage and is not marked healthy.`,
      );
      setRecord(saved.record);
    } catch {
      setError("Rejection did not reach the agent.");
    } finally {
      setBusy(false);
    }
  }, [busy, incident, loadFleet]);

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
      const serviceId = incident?.service_id ?? null;
      recordStamp.current += 1;
      const result = await agentClient.discuss(serviceId, said, "voice");
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
      event.preventDefault();
      approve("action");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [approve]);

  const summary = fleet?.summary;
  const shownRecord = useMemo(() => {
    if (scope === "all" || !incident) return record;
    return record.filter((entry) => entry.service_id === incident.service_id);
  }, [incident, record, scope]);
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
          <div className="mark">OP</div>
          <div>
            <p className="kicker">Fleet command</p>
            <h1>OpsPilot</h1>
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
            <button type="button" className={queue === "fleet" ? "on" : ""} onClick={() => setQueue("fleet")}>
              Fleet <em>{summary?.healthy ?? 0}</em>
            </button>
          </div>
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
                  onSelect={() => setSelected(item.service_id)}
                />
              ))}
            {queue === "fleet" && fleetGroups.length === 0 && <p className="empty">No healthy services match that filter.</p>}
            {queue === "fleet" &&
              fleetGroups.map(([label, items]) => (
                <div className="layer" key={label}>
                  <p>{label}</p>
                  {items.map((item) => (
                    <div className="fleet-row" key={item.service_id}>
                      <i />
                      <b>{item.service_id}</b>
                      <small>{item.version}</small>
                    </div>
                  ))}
                </div>
              ))}
          </div>
        </section>

        <section className="panel work">
          {!incident ? (
            <div className="blank">
              <p className="kicker">No incident open</p>
              <h2>Choose a service from Open</h2>
              <ol>
                <li>Open holds the services that still need a decision.</li>
                <li>Approve runs the suggested fix and marks that service healthy.</li>
                <li>The record on the right keeps every question and every decision.</li>
              </ol>
            </div>
          ) : (
            <>
              <div className="work-scroll">
                <div className="identity">
                  <div className="row-top">
                    <p className="kicker">{incident.layer_label}</p>
                    <span className={`badge ${incident.status === "TRIAGE" ? "triage" : incident.severity === "SEV-1" ? "sev1" : incident.severity === "SEV-3" ? "sev3" : "sev2"}`}>
                      {incident.status === "TRIAGE" ? "TRIAGE" : incident.severity}
                    </span>
                  </div>
                  <h2>{incident.service_id}</h2>
                  <p>{analyzing ? "Consulting Bedrock" : sourceLabel(incident.proposal_source)}</p>
                </div>
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
                <p className="impact">{incident.root_cause ?? incident.impact_summary}</p>
                <p className="logs">
                  <span className="ts">[{incident.log_level}] {shortTime(incident.log_timestamp)} </span>
                  {incident.log_message}
                </p>
                <table className="outcomes">
                  <caption>What each choice does</caption>
                  <tbody>
                    <tr>
                      <th>Approve</th>
                      <td>
                        {ACTION_EFFECT[incident.recommended_action] ?? "Runs the suggested action"} using {incident.target}. The service leaves Open and joins Fleet at error rate 0.
                      </td>
                    </tr>
                    <tr>
                      <th>Override</th>
                      <td>
                        {showOverride
                          ? `${ACTION_EFFECT[overrideAction] ?? "Runs that action"} using ${overrideTarget || "the target you type"}. Nothing runs until Execute.`
                          : "Pick a different action and target. Nothing changes until Execute."}
                      </td>
                    </tr>
                    <tr>
                      <th>Reject</th>
                      <td>Stays in Open as triage. It is not marked healthy.</td>
                    </tr>
                  </tbody>
                </table>
                {incident.status === "TRIAGE" && (
                  <p className="triage-note">This proposal was rejected. It is still broken until you approve a fix.</p>
                )}
              </div>
              <footer className="decision">
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
                  <button className="danger" type="button" disabled={busy || incident.status === "TRIAGE"} onClick={() => void reject("action")}>
                    Reject
                  </button>
                  <button className="ok" type="button" disabled={busy} onClick={() => approve("action")}>
                    {showOverride ? `Execute ${overrideAction}` : `Approve ${incident.recommended_action}`}
                  </button>
                </div>
              </footer>
            </>
          )}
        </section>

        <section className="panel chatter">
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
                  This service
                </button>
                <button type="button" className={scope === "all" ? "on" : ""} onClick={() => setScope("all")}>
                  Entire fleet
                </button>
              </div>
              <div className="thread" aria-live="polite">
                {shownRecord.length === 0 && (
                  <p className="empty">
                    {incident
                      ? `Nothing saved yet for ${incident.service_id}. Ask below, or press Talk about this. Voice and text are both kept.`
                      : "Open a service, then ask. Every question and answer is kept."}
                  </p>
                )}
                {shownRecord.map((entry, index) => (
                  <article className={`bubble ${entry.role}`} key={`${entry.timestamp}-${index}`}>
                    <p className="who">
                      <span>{entry.role === "user" ? "Operator" : "OpsPilot"}</span>
                      <span>{entry.channel}</span>
                      <time>{shortTime(entry.timestamp)}</time>
                    </p>
                    <p>{entry.text}</p>
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
                  placeholder={scope === "all" ? "Ask about the fleet or a service" : incident ? `Ask about ${incident.service_id}, or how this board works` : "Ask what's open, or how this board works"}
                  aria-label="Message OpsPilot"
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
      <span className="issue">{item.issue_type}</span>
      <span className="path">
        {pct(item.error_rate)} · {item.recommended_action} → {item.target}
      </span>
    </button>
  );
}
