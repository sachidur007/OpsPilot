import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from simulator.scenarios import ACTIONS, LAYERS, OPENING_INCIDENTS, SCENARIOS, SCENARIO_BY_SERVICE

DATA_DIR = Path(__file__).parent / "data"
STATE_FILE = DATA_DIR / "fleet_state.json"
RECORD_FILE = DATA_DIR / "command_record.json"
METRICS_FILE = DATA_DIR / "metrics.json"
LOGS_FILE = DATA_DIR / "logs.json"
DEPLOYMENTS_FILE = DATA_DIR / "deployments.json"
STATE_VERSION = 1
MODEL_CAP = 40
SLOPE_WAIT_SECONDS = 30
SLOPE_STEP = 0.008
RULES = (
    "Error rate at or above 20%, or a CRITICAL log, is SEV-1.",
    "Error rate at or above 5% is SEV-2.",
    "Otherwise the alert is SEV-3.",
)

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def severity_for(status: str, error_rate: float, log_level: str) -> str | None:
    if status == "HEALTHY":
        return None
    if log_level == "CRITICAL" or error_rate >= 0.20:
        return "SEV-1"
    if error_rate >= 0.05:
        return "SEV-2"
    return "SEV-3"


def _healthy_service(scenario: dict, opened_at: str) -> dict:
    service = {
        "service_id": scenario["service"],
        "layer": scenario["layer"],
        "layer_label": LAYERS[scenario["layer"]],
        "status": "HEALTHY",
        "version": scenario["target"],
        "fault_version": scenario["fault_version"],
        "stable_version": scenario["target"],
        "error_rate": 0.0,
        "log_level": "INFO",
        "issue_type": None,
        "impact_summary": "Within baseline.",
        "log_message": f"{scenario['service']} steady on {scenario['target']}",
        "log_timestamp": opened_at,
        "recommended_action": scenario["action"],
        "target": scenario["target"],
        "scenario_action": scenario["action"],
        "scenario_target": scenario["target"],
        "scenario_issue": scenario["issue_type"],
        "scenario_impact": scenario["impact"],
        "scenario_error": scenario["error"],
        "scenario_error_rate": scenario["error_rate"],
        "scenario_log_level": scenario["log_level"],
        "proposal": None,
        "updated_at": opened_at,
        "silenced_until": None,
        "jira_key": None,
        "error_history": [],
    }
    service["error_history"] = _seed_history(service)
    return service


def _activate(service: dict, at: str) -> None:
    service["status"] = "DEGRADED"
    service["version"] = service["fault_version"]
    service["error_rate"] = service["scenario_error_rate"]
    service["log_level"] = service["scenario_log_level"]
    service["issue_type"] = service["scenario_issue"]
    service["impact_summary"] = service["scenario_impact"]
    service["log_message"] = f"[{service['scenario_issue']}] {service['scenario_error']}"
    service["log_timestamp"] = at
    service["recommended_action"] = service["scenario_action"]
    service["target"] = service["scenario_target"]
    service["proposal"] = {
        "root_cause": f"{service['scenario_issue']} on {service['fault_version']}. {service['scenario_impact']}",
        "recommended_action": service["scenario_action"],
        "target_version_or_value": service["scenario_target"],
        "source": "scenario-fallback",
    }
    service["error_history"] = [round(float(service["error_rate"]), 4)]
    service["updated_at"] = at


def _opening_state() -> dict:
    opened_at = _now()
    services = {}
    order = []
    chaos_queue = []
    for index, scenario in enumerate(SCENARIOS):
        service = _healthy_service(scenario, opened_at)
        services[scenario["service"]] = service
        if scenario["service"] in OPENING_INCIDENTS:
            _activate(service, opened_at)
            service["proposal"]["source"] = "opening-scene"
            order.append(scenario["service"])
        else:
            chaos_queue.append(scenario["service"])
        service["queue_order"] = index
    # Commander-facing order: payment, vault, ingress.
    rank = {name: position for position, name in enumerate(OPENING_INCIDENTS)}
    for name in OPENING_INCIDENTS:
        services[name]["queue_order"] = rank[name]
    return {
        "version": STATE_VERSION,
        "services": services,
        "chaos_queue": chaos_queue,
        "deployments": [
            {
                "deployment_id": f"dep-base-{service['service_id']}",
                "service": service["service_id"],
                "version": service["version"],
                "timestamp": opened_at,
                "status": "SUCCESS",
                "changes": f"Baseline release {service['version']}",
            }
            for service in services.values()
        ],
        "timeline": [
            {
                "timestamp": opened_at,
                "service_id": None,
                "kind": "scene",
                "message": "Opening scene armed. payment-service, vault-secrets-manager, and ingress-nginx-controller are in incident. 21 services are healthy.",
            }
        ],
        "model_calls": 0,
        "model_cap": MODEL_CAP,
        "slope_advanced_at": opened_at,
        "last_bedrock": None,
    }


def _declaration(service: dict) -> dict | None:
    raw = service.get("declaration")
    if isinstance(raw, dict) and raw.get("title") and raw.get("details"):
        return raw
    if isinstance(raw, str) and raw.strip():
        return {
            "title": service["service_id"],
            "severity": severity_for(service["status"], service["error_rate"], service["log_level"]),
            "details": " ".join(raw.split()),
            "notes": None,
            "links": [],
            "attributes": [],
        }
    return None


def _present(service: dict) -> dict:
    declaration = _declaration(service)
    severity = severity_for(service["status"], service["error_rate"], service["log_level"])
    chosen = (declaration or {}).get("severity")
    if service["status"] != "HEALTHY" and chosen in ("SEV-1", "SEV-2", "SEV-3"):
        severity = chosen
    proposal = service.get("proposal")
    return {
        "service_id": service["service_id"],
        "layer": service["layer"],
        "layer_label": service["layer_label"],
        "status": service["status"],
        "severity": severity,
        "version": service["version"],
        "fault_version": service["fault_version"],
        "stable_version": service["stable_version"],
        "error_rate": service["error_rate"],
        "log_level": service["log_level"],
        "issue_type": service["issue_type"],
        "impact_summary": service["impact_summary"],
        "log_message": service["log_message"],
        "log_timestamp": service["log_timestamp"],
        "recommended_action": (proposal or {}).get("recommended_action", service["recommended_action"]),
        "target": (proposal or {}).get("target_version_or_value", service["target"]),
        "root_cause": (proposal or {}).get("root_cause"),
        "proposal_source": (proposal or {}).get("source"),
        "fallback_reason": (proposal or {}).get("fallback_reason"),
        "declaration": declaration,
        "decision": service.get("decision") if isinstance(service.get("decision"), dict) else None,
        "silenced_until": service.get("silenced_until"),
        "jira_key": service.get("jira_key"),
        "forecast": _forecast(service),
        "observed_rate": _observed(service),
        "updated_at": service["updated_at"],
    }


def _summary(services: list[dict]) -> dict:
    active = [item for item in services if item["status"] != "HEALTHY"]
    healthy = [item for item in services if item["status"] == "HEALTHY"]
    layers = []
    for layer_id, label in LAYERS.items():
        layers.append({
            "id": layer_id,
            "label": label,
            "active": sum(1 for item in active if item["layer"] == layer_id),
            "healthy": sum(1 for item in healthy if item["layer"] == layer_id),
        })
    return {
        "healthy": len(healthy),
        "active": len(active),
        "critical": sum(1 for item in active if item["severity"] == "SEV-1"),
        "sev2": sum(1 for item in active if item["severity"] == "SEV-2"),
        "sev3": sum(1 for item in active if item["severity"] == "SEV-3"),
        "triage": sum(1 for item in active if item["status"] == "TRIAGE"),
        "layers": layers,
    }


def _mirror(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    metrics = {}
    logs = []
    for service in state["services"].values():
        metrics[service["service_id"]] = {
            "status": service["status"],
            "error_rate": service["error_rate"],
            "version": service["version"],
            "log_level": service["log_level"],
            "issue_type": service["issue_type"],
            "impact_summary": service["impact_summary"],
            "recommended_action": service["recommended_action"],
            "target": service["target"],
        }
        if service["status"] != "HEALTHY":
            logs.append({
                "timestamp": service["log_timestamp"],
                "service": service["service_id"],
                "level": service["log_level"],
                "message": service["log_message"],
            })
    METRICS_FILE.write_text(json.dumps(metrics, indent=2))
    LOGS_FILE.write_text(json.dumps(logs, indent=2))
    DEPLOYMENTS_FILE.write_text(json.dumps(state["deployments"], indent=2))


def _read() -> dict:
    if not STATE_FILE.exists():
        state = _opening_state()
        _write(state)
        return state
    state = json.loads(STATE_FILE.read_text())
    if state.get("version") != STATE_VERSION:
        state = _opening_state()
        _write(state)
        return state
    _backfill(state)
    return state


def _write(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state.pop("_backfill_dirty", None)
    state.pop("_notices", None)
    STATE_FILE.write_text(json.dumps(state, indent=2))
    _mirror(state)


def _backfill(state: dict) -> None:
    dirty = False
    if "model_calls" not in state:
        state["model_calls"] = 0
        dirty = True
    if "model_cap" not in state:
        state["model_cap"] = MODEL_CAP
        dirty = True
    if "slope_advanced_at" not in state:
        state["slope_advanced_at"] = _now()
        dirty = True
    if "last_bedrock" not in state:
        state["last_bedrock"] = None
        dirty = True
    for service in state["services"].values():
        if "silenced_until" not in service:
            service["silenced_until"] = None
            dirty = True
        if "jira_key" not in service:
            service["jira_key"] = None
            dirty = True
        if not service.get("error_history"):
            service["error_history"] = _seed_history(service)
            dirty = True
    if dirty:
        state["_backfill_dirty"] = True


def _seed_history(service: dict) -> list[float]:
    if service.get("status") != "HEALTHY":
        return [round(float(service.get("error_rate") or 0), 4)]
    if float(service.get("scenario_error_rate") or 0) < 0.05:
        return [0.0]
    return [0.012, 0.021, 0.029, 0.036]


def _forecast(service: dict) -> str | None:
    if service.get("status") != "HEALTHY" or _silenced(service):
        return None
    if float(service.get("scenario_error_rate") or 0) < 0.05:
        return None
    history = [float(item) for item in service.get("error_history") or []]
    if len(history) < 2:
        return None
    if history[-1] <= history[-2] or history[-1] >= 0.05 or history[-1] <= history[0]:
        return None
    return "approaching SEV-2"


def _observed(service: dict) -> float:
    if service.get("status") != "HEALTHY":
        return float(service.get("error_rate") or 0)
    history = service.get("error_history") or []
    if not history:
        return 0.0
    return float(history[-1])


def _silenced(service: dict, moment: datetime | None = None) -> bool:
    raw = service.get("silenced_until")
    if not raw:
        return False
    try:
        until = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    moment = moment or datetime.now(timezone.utc)
    return until > moment


def _parse_until(raw: str) -> str | None:
    text = " ".join((raw or "").split())
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _degrade(state: dict, service: dict, source: str, actor: str) -> None:
    at = _now()
    _activate(service, at)
    service["proposal"]["source"] = source
    service_id = service["service_id"]
    queue = state["chaos_queue"]
    if service_id in queue:
        queue.remove(service_id)
    service["queue_order"] = 50 + (24 - len(queue))
    presented = _present(service)
    state.setdefault("_notices", []).append({
        "kind": "open",
        "service_id": service_id,
        "severity": presented.get("severity"),
        "action": presented["recommended_action"],
        "actor": actor,
    })
    if source == "chaos":
        message = (
            f"Simulate Chaos degraded {service_id}: {service['issue_type']} on {service['version']}. "
            f"Proposed {service['recommended_action']} -> {service['target']}."
        )
        kind = "chaos"
    elif source == "declared":
        declared = service.get("declaration") if isinstance(service.get("declaration"), dict) else {}
        title = declared.get("title") or service_id
        level = declared.get("severity") or ""
        details = declared.get("details") or ""
        message = (
            f"Operator declared {title} ({level}) on {service_id}: {details} "
            f"Catalog fault is {service['issue_type']} on {service['version']}. "
            f"Proposed {service['recommended_action']} -> {service['target']}."
        )
        kind = "alert"
    else:
        message = (
            f"Error rate crossed 5% on {service_id}. Opened {presented.get('severity')} alert. "
            f"Proposed {service['recommended_action']} -> {service['target']}."
        )
        kind = "alert"
    _append_timeline(state, service_id, kind, message)


def advance_slope(state: dict, *, force: bool = False) -> bool:
    moment = datetime.now(timezone.utc)
    previous = state.get("slope_advanced_at")
    if not force and previous:
        try:
            then = datetime.fromisoformat(previous)
        except ValueError:
            then = None
        if then is not None:
            if then.tzinfo is None:
                then = then.replace(tzinfo=timezone.utc)
            if (moment - then).total_seconds() < SLOPE_WAIT_SECONDS:
                return False
    state["slope_advanced_at"] = moment.isoformat()
    ranked = []
    for service in state["services"].values():
        if service.get("status") != "HEALTHY" or _silenced(service, moment):
            continue
        if float(service.get("scenario_error_rate") or 0) < 0.05:
            continue
        history = [float(item) for item in (service.get("error_history") or _seed_history(service))]
        last = history[-1] if history else 0.0
        nxt = round(last + SLOPE_STEP, 4)
        ranked.append((nxt, service["service_id"], service, history))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    crossed = False
    changed = False
    for nxt, _service_id, service, history in ranked:
        if nxt >= 0.05 and not crossed:
            _degrade(state, service, "slope", "slope")
            crossed = True
            changed = True
            continue
        capped = round(min(nxt, 0.049), 4)
        service["error_history"] = (history + [capped])[-8:]
        changed = True
    return changed


def _emit_notices(notices: list) -> bool:
    from agent.outbound import comment_jira, create_jira_issue, post_slack

    keys = []
    for notice in notices:
        kind = notice.get("kind")
        service_id = notice.get("service_id")
        severity = notice.get("severity")
        action = notice.get("action") or ""
        if kind == "open":
            post_slack(service_id, severity, action, notice.get("actor") or "operator")
            key = create_jira_issue(service_id, severity, action)
            if key:
                keys.append((service_id, key))
        elif kind == "approve":
            post_slack(service_id, severity, action, "operator")
            comment_jira(notice.get("jira_key"), f"Approved {action} to {notice.get('target')} on {service_id}.")
        elif kind == "reject":
            post_slack(service_id, severity, "reject", "operator")
    if not keys:
        return False
    with _lock:
        state = _read()
        for service_id, key in keys:
            service = state["services"].get(service_id)
            if service is not None:
                service["jira_key"] = key
        _write(state)
    return True


def silence_service(service_id: str, until: str) -> dict:
    with _lock:
        state = _read()
        service = state["services"].get(service_id)
        if not service:
            return {"status": "MISSING", "service_id": service_id}
        parsed = _parse_until(until)
        if not parsed:
            return {"status": "INVALID_TIME", "service_id": service_id}
        service["silenced_until"] = parsed
        service["updated_at"] = _now()
        _append_timeline(state, service_id, "silence", f"Muted {service_id} until {parsed}.")
        _write(state)
        return {"status": "SILENCED", "service": _present(service)}


def budget_view(state: dict | None = None) -> dict:
    owned = state is None
    if owned:
        _lock.acquire()
    try:
        if state is None:
            state = _read()
        calls = int(state.get("model_calls") or 0)
        cap = int(state.get("model_cap") or MODEL_CAP)
        return {"calls": calls, "cap": cap, "remaining": max(0, cap - calls)}
    finally:
        if owned:
            _lock.release()


def begin_model_call(model_id: str) -> dict:
    with _lock:
        state = _read()
        state["model_calls"] = int(state.get("model_calls") or 0) + 1
        state["last_bedrock"] = {
            "model_id": model_id,
            "source": "pending",
            "fallback_reason": None,
        }
        _write(state)
        return budget_view(state)


def finish_model_call(model_id: str, source: str, fallback_reason: str | None) -> dict:
    with _lock:
        state = _read()
        state["last_bedrock"] = {
            "model_id": model_id,
            "source": source,
            "fallback_reason": (str(fallback_reason)[:240] if fallback_reason else None),
        }
        _write(state)
        return budget_view(state)


def bedrock_view() -> dict:
    with _lock:
        state = _read()
        last = state.get("last_bedrock")
        model_id = (last or {}).get("model_id")
        return {"model_id": model_id, "last_bedrock": last}


def stamp_coworker(entries: list, coworker: dict, reply: str) -> list:
    with _lock:
        updated = list(entries)
        spoken = " ".join(reply.split())[:2200]
        for entry in reversed(updated):
            if entry.get("role") == "agent":
                entry["text"] = spoken
                entry["coworker"] = coworker
                break
        return _write_record(updated)


def _read_record() -> list:
    if not RECORD_FILE.exists():
        return []
    try:
        data = json.loads(RECORD_FILE.read_text())
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _write_record(entries: list) -> list:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    kept = entries[-500:]
    RECORD_FILE.write_text(json.dumps(kept, indent=2))
    return kept


def append_record(service_id: str | None, channel: str, role: str, text: str) -> list:
    spoken = " ".join(text.split())[:2200]
    if not spoken:
        return _read_record()
    with _lock:
        entries = _read_record()
        entries.append({
            "timestamp": _now(),
            "service_id": service_id,
            "channel": channel,
            "role": role,
            "text": spoken,
        })
        return _write_record(entries)


def route_question(service_id: str | None, text: str) -> dict:
    """Decide which service a question is about, without writing the record."""
    asked = " ".join(text.split())[:600] or "Talk about this service."
    with _lock:
        state = _read()
        from agent.conversation import is_decision_talk, is_open_incident_talk, is_product_aside, is_small_talk
        from agent.project_knowledge import is_incident_question, is_project_question

        named = _named_service(asked, state["services"])
        detail = _wants_detail(asked)
        incident = is_incident_question(asked)
        on_open = bool(service_id and service_id in state["services"] and is_open_incident_talk(asked))
        if is_decision_talk(asked):
            anchor = named if named in state["services"] else None
            if anchor is None and service_id in state["services"]:
                anchor = service_id
            if anchor is None:
                anchor = _recent_service(state["services"])
            if anchor:
                return {"kind": "decision", "asked": asked, "service_id": anchor, "moved": False}
        if is_product_aside(asked) and not named:
            return {"kind": "chat", "asked": asked, "service_id": service_id}
        if is_small_talk(asked) and not named and not incident and not on_open:
            return {"kind": "chat", "asked": asked, "service_id": service_id}
        if is_project_question(asked) and not (named and incident) and not on_open:
            return {"kind": "project", "asked": asked, "service_id": service_id, "detail": detail}
        if named and named in state["services"]:
            return {
                "kind": "service",
                "asked": asked,
                "service_id": named,
                "moved": bool(service_id and named != service_id),
                "detail": detail,
            }
        if _about_fleet(asked) or (not service_id and (incident or is_open_incident_talk(asked))):
            return {"kind": "fleet", "asked": asked}
        if service_id and _asks_about_something_else(asked, service_id):
            return {"kind": "guide", "asked": asked, "service_id": service_id}
        if on_open:
            return {
                "kind": "service",
                "asked": asked,
                "service_id": service_id,
                "moved": False,
                "detail": detail,
            }
        return {"kind": "chat", "asked": asked, "service_id": service_id}


def discuss(service_id: str | None, text: str, channel: str) -> dict:
    asked = " ".join(text.split())[:600] or "Talk about this service."
    with _lock:
        state = _read()
        from agent.conversation import is_decision_talk, is_open_incident_talk, is_product_aside, reply as chat_reply

        named = _named_service(asked, state["services"])
        moved = False
        decision_anchor = None
        if is_decision_talk(asked):
            decision_anchor = named if named in state["services"] else None
            if decision_anchor is None and service_id in state["services"]:
                decision_anchor = service_id
            if decision_anchor is None:
                decision_anchor = _recent_service(state["services"])
        if decision_anchor:
            target_id = decision_anchor
            reply = _decision_reply(state["services"][decision_anchor], asked)
        elif named and service_id and named != service_id:
            target_id = named
            reply = (
                f"That question is about {named}, so I moved it to Entire fleet. "
                + _knowledge(state["services"][named], asked, state)
            )
            moved = True
        elif named:
            target_id = named
            reply = _knowledge(state["services"][named], asked, state)
        elif is_product_aside(asked):
            target_id = service_id
            reply = chat_reply(asked, service_id if service_id in state["services"] else None)
        elif _about_fleet(asked) or (not service_id and is_open_incident_talk(asked)):
            target_id = None
            reply = _fleet_brief(state)
        elif service_id and _asks_about_something_else(asked, service_id):
            target_id = None
            reply = (
                f"This record only answers {service_id}. I moved you to Entire fleet. "
                "Ask again with the service name, for example notification-service."
            )
            moved = True
        elif service_id and service_id in state["services"] and is_open_incident_talk(asked):
            target_id = service_id
            reply = _knowledge(state["services"][service_id], asked, state)
        else:
            target_id = service_id
            reply = chat_reply(asked, service_id if service_id in state["services"] else None)
        entries = _read_record()
        entries.append({
            "timestamp": _now(),
            "service_id": target_id,
            "channel": channel,
            "role": "user",
            "text": asked,
        })
        entries.append({
            "timestamp": _now(),
            "service_id": target_id,
            "channel": channel,
            "role": "agent",
            "text": reply,
        })
        return {
            "reply": reply,
            "record": _write_record(entries),
            "service_id": target_id,
            "scope": "all" if moved else "service",
        }


def _named_service(text: str, services: dict) -> str | None:
    lowered = text.lower()
    compact = "".join(ch for ch in lowered if ch.isalnum())
    for service_id in sorted(services, key=len, reverse=True):
        token = "".join(ch for ch in service_id.lower() if ch.isalnum())
        if token and token in compact:
            return service_id
        slug = token.removesuffix("service")
        if len(slug) < 4:
            continue
        for word in lowered.replace("-", " ").split():
            plain = "".join(ch for ch in word if ch.isalnum())
            if plain.startswith(slug) and len(plain) - len(slug) <= 2:
                return service_id
    words = ["".join(ch for ch in word if ch.isalnum()) for word in lowered.replace("-", " ").split()]
    words = [word for word in words if word and word not in _NAME_STOP]
    candidates = list(words)
    candidates.extend(words[index] + words[index + 1] for index in range(len(words) - 1))
    best_id = None
    best_score = 0.0
    second = 0.0
    for service_id in services:
        slug = "".join(ch for ch in service_id.lower().replace("-service", "") if ch.isalnum())
        if len(slug) < 4:
            continue
        for candidate in candidates:
            if len(candidate) < 4:
                continue
            score = 1 - (_distance(candidate, slug) / max(len(candidate), len(slug)))
            if score > best_score:
                second = best_score
                best_score = score
                best_id = service_id
            elif score > second:
                second = score
    if best_id and best_score >= 0.72 and best_score - second >= 0.08:
        return best_id
    return None


def _distance(left: str, right: str) -> int:
    if abs(len(left) - len(right)) > 3:
        return 99
    previous = list(range(len(right) + 1))
    for index, char in enumerate(left, 1):
        current = [index]
        for other_index, other in enumerate(right, 1):
            current.append(min(
                previous[other_index] + 1,
                current[-1] + 1,
                previous[other_index - 1] + (char != other),
            ))
        previous = current
    return previous[-1]


_NAME_STOP = {
    "about", "tell", "what", "whats", "how", "this", "that", "service", "services",
    "status", "detail", "details", "more", "please", "explain", "everything",
    "from", "with", "your", "have", "does", "into", "open", "fleet", "entire",
}


def _recent_service(services: dict) -> str | None:
    for entry in reversed(_read_record()):
        service_id = entry.get("service_id")
        if service_id in services:
            return service_id
    return None


def _choice(text: str) -> str:
    lowered = text.lower()
    found = []
    for word in ("override", "approve", "reject"):
        at = lowered.find(word)
        if at >= 0:
            found.append((at, word))
    found.sort()
    return found[0][1] if found else "override"


def _decision_reply(service: dict, asked: str) -> str:
    presented = _present(service)
    name = presented["service_id"]
    action = presented["recommended_action"] or "the suggested action"
    target = presented["target"] or "the suggested target"
    effect = _ACTION_EFFECT.get(action, "runs that action")
    if presented["status"] == "HEALTHY":
        return f"{name} is healthy, so override, approve, and reject have nothing to run."
    fault = (presented["issue_type"] or presented["impact_summary"] or "the fault").lower()
    if not fault.startswith("the "):
        fault = f"the {fault}"
    choice = _choice(asked)
    if choice == "approve":
        return (
            f"Approve on {name} runs {action} to {target}. That {effect}, marks {name} healthy, and sets the error rate to 0."
        )
    if choice == "reject":
        return (
            f"Reject on {name} does not run {action}. It stays open as triage, and it is not marked healthy."
        )
    return (
        f"Override on {name} does not run the suggested {action} to {target}. "
        f"You pick a different action and target, then press Execute. Nothing changes until that Execute, so {fault} on {presented['version']} stays. "
        f"Approve would run {action} to {target}, which {effect} and marks {name} healthy. Reject would leave it open as triage."
    )


def explain_decision(service_id: str, text: str) -> str:
    with _lock:
        service = _read()["services"].get(service_id)
        if not service:
            return f"{service_id} is not in this fleet."
        return _decision_reply(service, text)


def _asks_about_something_else(text: str, service_id: str) -> bool:
    from agent.conversation import is_decision_talk, is_open_incident_talk, is_product_aside

    if is_open_incident_talk(text) or is_product_aside(text) or is_decision_talk(text):
        return False
    lowered = text.lower()
    slug = "".join(ch for ch in service_id.lower().split("-")[0] if ch.isalnum())
    compact = "".join(ch for ch in lowered if ch.isalnum())
    if slug and slug in compact:
        return False
    if not any(cue in lowered for cue in ("about ", "what about", "how's ", "how is ", "status of")):
        return False
    filler = _NAME_STOP | {
        "build", "project", "application", "product", "hackathon", "demo", "code",
        "today", "things", "everything", "going", "life", "work", "progress",
        "override", "approve", "reject", "happens", "hows", "whats", "give",
        "okay", "want", "just", "heads", "some", "like", "when", "will", "been",
        "them", "they", "ours", "here", "there", "looking", "doing",
    }
    leftovers = []
    for word in lowered.replace("-", " ").replace("'", "").split():
        plain = "".join(ch for ch in word if ch.isalnum())
        if len(plain) >= 4 and plain not in filler:
            leftovers.append(plain)
    return bool(leftovers)


def _about_fleet(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "entire fleet",
        "whole fleet",
        "all services",
        "the fleet",
        "fleet status",
        "what's open",
        "whats open",
        "what is open",
        "how many",
    )
    return any(marker in lowered for marker in markers)


def _fleet_brief(state: dict) -> str:
    presented = [_present(service) for service in state["services"].values()]
    summary = _summary(presented)
    active = [item for item in presented if item["status"] != "HEALTHY"]
    active.sort(key=lambda item: ({"SEV-1": 0, "SEV-2": 1, "SEV-3": 2}.get(item["severity"], 9), item["service_id"]))
    if not active:
        return f"The fleet is clear. {summary['healthy']} services are healthy."
    lines = [
        f"{item['service_id']} is {item['severity'] or item['status']}, {item['error_rate'] * 100:.1f}% errors, suggested {item['recommended_action']} to {item['target']}."
        for item in active[:6]
    ]
    extra = len(active) - len(lines)
    tail = f" {extra} more are also open." if extra else ""
    return (
        f"{summary['active']} open, {summary['healthy']} healthy, {summary['critical']} SEV-1. "
        + " ".join(lines)
        + tail
    )


_ACTION_EFFECT = {
    "rollback": "puts the earlier release back into service",
    "unseal": "opens the sealed vault so secrets can be read again",
    "cert_rotation": "replaces the expired certificate",
    "dns_flush": "clears the bad DNS answer",
    "scale_pods": "adds capacity so the service can keep up",
    "failover": "moves traffic to the standby",
}


def _wants_detail(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "more detail",
        "more details",
        "go deeper",
        "in detail",
        "everything",
        "explain",
        "tell me more",
        "elaborate",
        "why",
        "what happened",
        "full picture",
        "break it down",
        "the log",
    )
    return any(marker in lowered for marker in markers)


def _knowledge(service: dict, asked: str, state: dict) -> str:
    if _wants_detail(asked):
        return _detailed(service, state)
    return _brief(service)


def _brief(service: dict) -> str:
    presented = _present(service)
    name = presented["service_id"]
    if presented["status"] == "HEALTHY":
        return (
            f"{name} is healthy, live {presented['version']}, error rate 0, in {presented['layer_label']}. "
            "No fix is waiting."
        )
    cause = presented["root_cause"] or presented["impact_summary"] or presented["issue_type"] or "an open fault"
    severity = presented["severity"] or presented["status"]
    rate = f"{presented['error_rate'] * 100:.1f}%"
    return (
        f"{name} is {presented['status']}, {severity}, live {presented['version']}, {rate} errors. "
        f"{cause}. Suggested fix: {presented['recommended_action']} to {presented['target']}."
    )


def _detailed(service: dict, state: dict) -> str:
    presented = _present(service)
    name = presented["service_id"]
    action = presented["recommended_action"]
    effect = _ACTION_EFFECT.get(action, "runs that action")
    steps = [item["message"] for item in state.get("timeline", []) if item.get("service_id") == name]
    last = f" Last step recorded: {steps[-1]}" if steps else ""
    if presented["status"] == "HEALTHY":
        return (
            f"{name} is healthy in {presented['layer_label']}, live {presented['version']}, error rate 0. "
            f"Nothing is waiting on it. If this service breaks, the catalog fault is {service.get('scenario_issue')} "
            f"on {presented['fault_version']}, and the matching fix is {service.get('scenario_action')} to {service.get('scenario_target')}. "
            "It is not in that state now."
        )
    rate = f"{presented['error_rate'] * 100:.1f}%"
    severity = presented["severity"] or presented["status"]
    if severity == "SEV-1":
        why = "SEV-1 because the log is CRITICAL or at least 20% of calls are failing."
    elif severity == "SEV-2":
        why = "SEV-2 because the error rate is at least 5% and under 20%."
    else:
        why = "SEV-3 because the error rate is under 5% and the log is not CRITICAL."
    cause = presented["impact_summary"] or presented["issue_type"] or "an open fault"
    return (
        f"{name} is in {presented['layer_label']}. It is {presented['status']}, {severity}: {rate} of calls are failing. {why} "
        f"The release in production is {presented['version']}, and that release is the fault. "
        f"The suggested return point is {presented['target']}. "
        f"{presented['issue_type'] or 'The fault'}. {cause}. "
        f"The log says: {presented['log_message']}. "
        f"{action} {effect}, using {presented['target']}. "
        f"Approve runs that and marks {name} healthy at error rate 0. "
        f"Reject leaves it open as triage. "
        f"Override picks a different action, and nothing runs until Execute."
        f"{last}"
    )


def dialogue_pack(service_id: str | None) -> dict:
    """Live facts for the dialogue model. No phrase matching."""
    with _lock:
        state = _read()
        presented = [_present(service) for service in state["services"].values()]
        recent = [
            {
                "role": entry.get("role") or "user",
                "text": entry.get("text") or "",
                "service_id": entry.get("service_id"),
            }
            for entry in _read_record()[-8:]
        ]
    summary = _summary(presented)
    selected = None
    open_lines = []
    healthy = []
    for item in sorted(presented, key=lambda row: row["service_id"]):
        if item["service_id"] == service_id:
            selected = item
        if item["status"] == "HEALTHY":
            healthy.append(f"{item['service_id']} ({item['layer_label']}, live {item['version']})")
            continue
        source = "Bedrock" if item.get("proposal_source") == "bedrock" else "Scenario fallback"
        cause = item.get("root_cause") or item.get("impact_summary") or item.get("issue_type") or "an open fault"
        effect = _ACTION_EFFECT.get(item.get("recommended_action") or "", "runs that action")
        open_lines.append(
            f"{item['service_id']} is in {item['layer_label']}. Status {item['status']}, {item['severity']}. "
            f"Live version {item['version']}. {item['error_rate'] * 100:.1f}% of calls are failing. "
            f"What is wrong: {cause}. The log says: {item['log_message']}. "
            f"Suggested fix: {item['recommended_action']} to {item['target']}, which {effect}. "
            f"Source: {source}."
        )
    return {
        "open_count": summary["active"],
        "healthy_count": summary["healthy"],
        "critical_count": summary["critical"],
        "open_lines": open_lines,
        "healthy": healthy,
        "selected": selected,
        "recent": recent,
    }


def reset_fleet() -> dict:
    with _lock:
        state = _opening_state()
        _write(state)
        entries = _read_record()
        entries.append({
            "timestamp": _now(),
            "service_id": None,
            "channel": "action",
            "role": "agent",
            "text": "Opening scene restored. payment-service, vault-secrets-manager, and ingress-nginx-controller are in incident again.",
        })
        _write_record(entries)
        fleet = project_fleet(state)
        return fleet


def project_fleet(state: dict | None = None) -> dict:
    owned = state is None
    if owned:
        _lock.acquire()
    try:
        if state is None:
            state = _read()
        presented = [_present(service) for service in state["services"].values()]
        severity_rank = {"SEV-1": 0, "SEV-2": 1, "SEV-3": 2}
        active = [item for item in presented if item["status"] != "HEALTHY"]
        active.sort(key=lambda item: (severity_rank.get(item["severity"], 9), item["service_id"]))
        # Keep the scripted opening order ahead of later chaos inside the same severity.
        active.sort(key=lambda item: (
            severity_rank.get(item["severity"], 9),
            state["services"][item["service_id"]].get("queue_order", 100),
        ))
        healthy = [item for item in presented if item["status"] == "HEALTHY"]
        healthy.sort(key=lambda item: item["service_id"])
        return {
            "generated_at": _now(),
            "summary": _summary(presented),
            "active_incidents": active,
            "healthy_fleet": healthy,
            "timeline": list(state["timeline"]),
            "record": _read_record(),
            "chaos_remaining": len(state["chaos_queue"]),
            "rules": list(RULES),
            "model_calls": int(state.get("model_calls") or 0),
            "model_cap": int(state.get("model_cap") or MODEL_CAP),
            "last_bedrock": state.get("last_bedrock"),
        }
    finally:
        if owned:
            _lock.release()


def get_fleet() -> dict:
    with _lock:
        state = _read()
        dirty = bool(state.get("_backfill_dirty"))
        moved = advance_slope(state)
        notices = list(state.pop("_notices", []))
        if dirty or moved:
            _write(state)
        fleet = project_fleet(state)
    if _emit_notices(notices):
        with _lock:
            fleet = project_fleet(_read())
    return fleet


def get_service_record(service_id: str) -> dict | None:
    with _lock:
        state = _read()
        service = state["services"].get(service_id)
        if not service:
            return None
        presented = _present(service)
        deployments = [item for item in state["deployments"] if item["service"] == service_id]
        presented["recent_errors"] = []
        if service["status"] != "HEALTHY":
            presented["recent_errors"] = [{
                "timestamp": service["log_timestamp"],
                "service": service_id,
                "level": service["log_level"],
                "message": service["log_message"],
            }]
        presented["deployments"] = deployments
        presented["metrics"] = {
            "error_rate": service["error_rate"],
            "status": service["status"],
            "version": service["version"],
            "log_level": service["log_level"],
            "issue_type": service["issue_type"],
            "impact_summary": service["impact_summary"],
            "recommended_action": service["scenario_action"],
            "target_version": service["scenario_target"],
        }
        return presented


def _append_timeline(state: dict, service_id: str | None, kind: str, message: str) -> None:
    state["timeline"].append({
        "timestamp": _now(),
        "service_id": service_id,
        "kind": kind,
        "message": message,
    })
    state["timeline"] = state["timeline"][-200:]


def store_analysis(service_id: str, analysis: dict) -> dict:
    with _lock:
        state = _read()
        service = state["services"].get(service_id)
        if not service:
            return {"status": "MISSING", "service_id": service_id}
        action = analysis.get("recommended_action")
        if action not in ACTIONS:
            action = service["scenario_action"]
        target = analysis.get("target_version_or_value") or service["scenario_target"]
        service["proposal"] = {
            "root_cause": analysis.get("root_cause") or service["scenario_issue"],
            "recommended_action": action,
            "target_version_or_value": target,
            "source": analysis.get("source", "bedrock"),
        }
        if analysis.get("fallback_reason"):
            service["proposal"]["fallback_reason"] = str(analysis["fallback_reason"])[:240]
        service["recommended_action"] = action
        service["target"] = target
        service["updated_at"] = _now()
        note = f"Analysis ({service['proposal']['source']}): {action} -> {target}. {service['proposal']['root_cause']}"
        if service["proposal"].get("fallback_reason"):
            note += f" Fallback: {service['proposal']['fallback_reason']}"
        _append_timeline(
            state,
            service_id,
            "analysis",
            note[:500],
        )
        _write(state)
        return _present(service)


def _clean_reason(reason: str) -> str | None:
    text = " ".join(str(reason or "").split())[:1000]
    return text or None


def remediate(service_id: str, action: str, target: str, reason: str = "") -> dict:
    why = _clean_reason(reason)
    with _lock:
        state = _read()
        service = state["services"].get(service_id)
        if not service:
            return {"status": "MISSING", "service_id": service_id}
        if service["status"] == "HEALTHY":
            return {"status": "ALREADY_HEALTHY", "service_id": service_id, "verified": True}
        if not why:
            return {"status": "NEEDS_REASON", "service_id": service_id}
        if action not in ACTIONS:
            return {"status": "INVALID_ACTION", "service_id": service_id, "action": action}
        before = _present(service)
        overrode = action != service.get("recommended_action") or target != service.get("target")
        issue_key = service.get("jira_key")
        at = _now()
        service["status"] = "HEALTHY"
        service["version"] = target
        service["stable_version"] = target
        service["error_rate"] = 0.0
        service["log_level"] = "INFO"
        service["issue_type"] = None
        service.pop("declaration", None)
        service.pop("decision", None)
        service["impact_summary"] = "Recovered after approved remediation."
        service["log_message"] = f"{action} applied. {service_id} restored to {target}."
        service["log_timestamp"] = at
        service["updated_at"] = at
        service["proposal"] = None
        service["error_history"] = _seed_history(service)
        state["deployments"].append({
            "deployment_id": f"dep-{action}-{service_id}",
            "service": service_id,
            "version": target,
            "timestamp": at,
            "status": "SUCCESS",
            "changes": f"{action} to {target} executed by FleetOps",
        })
        verb = "overrode" if overrode else "approved"
        _append_timeline(
            state,
            service_id,
            "remediation",
            f"Operator {verb} {action} -> {target} on {service_id}: {why} Status HEALTHY. Error rate 0.00%.",
        )
        state.setdefault("_notices", []).append({
            "kind": "approve",
            "service_id": service_id,
            "severity": before.get("severity"),
            "action": action,
            "target": target,
            "jira_key": issue_key,
        })
        notices = list(state.pop("_notices", []))
        _write(state)
        presented = _present(service)
        outcome = {
            "status": "SUCCESS",
            "service_id": service_id,
            "action": action,
            "target": target,
            "verified": True,
            "error_rate": 0.0,
            "health": "HEALTHY",
            "service": presented,
        }
    _emit_notices(notices)
    return outcome


def reject_incident(service_id: str, reason: str = "") -> dict:
    why = _clean_reason(reason)
    with _lock:
        state = _read()
        service = state["services"].get(service_id)
        if not service or service["status"] == "HEALTHY":
            return {"status": "MISSING", "service_id": service_id}
        if not why:
            return {"status": "NEEDS_REASON", "service_id": service_id}
        before = _present(service)
        service["status"] = "TRIAGE"
        service["decision"] = {"kind": "reject", "reason": why}
        service["updated_at"] = _now()
        _append_timeline(
            state,
            service_id,
            "rejection",
            f"Operator rejected the proposal for {service_id}: {why} Incident returned to triage.",
        )
        notices = [{
            "kind": "reject",
            "service_id": service_id,
            "severity": before.get("severity"),
        }]
        _write(state)
        outcome = {"status": "TRIAGE", "service": _present(service)}
    _emit_notices(notices)
    return outcome


def _clean_declaration(fields: dict | None) -> dict | None:
    payload = fields or {}
    title = " ".join(str(payload.get("title") or "").split())[:120]
    severity = str(payload.get("severity") or "").strip()
    details = " ".join(str(payload.get("details") or "").split())[:1000]
    notes = " ".join(str(payload.get("notes") or "").split())[:1000]
    if not title or severity not in ("SEV-1", "SEV-2", "SEV-3") or not details:
        return None
    links = []
    for raw in payload.get("links") or []:
        link = str(raw).strip()
        if link.startswith("https://") or link.startswith("http://"):
            links.append(link[:300])
        if len(links) == 8:
            break
    attributes = []
    for raw in payload.get("attributes") or []:
        if not isinstance(raw, dict):
            continue
        name = " ".join(str(raw.get("name") or "").split())[:80]
        value = " ".join(str(raw.get("value") or "").split())[:160]
        if name and value:
            attributes.append({"name": name, "value": value})
        if len(attributes) == 8:
            break
    return {
        "title": title,
        "severity": severity,
        "details": details,
        "notes": notes or None,
        "links": links,
        "attributes": attributes,
    }


def declare_incident(service_id: str, fields: dict | None = None) -> dict:
    cleaned = _clean_declaration(fields)
    with _lock:
        state = _read()
        service = state["services"].get(service_id)
        if not service:
            return {"status": "MISSING", "service_id": service_id}
        if service.get("status") != "HEALTHY":
            return {"status": "ALREADY_OPEN", "service_id": service_id, "service": _present(service)}
        if cleaned is None:
            return {"status": "NEEDS_FIELDS", "service_id": service_id}
        service["declaration"] = cleaned
        _degrade(state, service, "declared", "operator")
        notices = list(state.pop("_notices", []))
        _write(state)
        outcome = {"status": "DECLARED", "service": _present(service)}
    if _emit_notices(notices):
        with _lock:
            state = _read()
            current = state["services"].get(service_id)
            if current:
                outcome["service"] = _present(current)
    return outcome


def trigger_chaos() -> dict:
    with _lock:
        state = _read()
        chosen = None
        chosen_index = None
        for index, service_id in enumerate(state["chaos_queue"]):
            service = state["services"].get(service_id)
            if not service or _silenced(service):
                continue
            chosen = service
            chosen_index = index
            break
        if chosen is None:
            return {
                "status": "IDLE",
                "message": "Every catalog scenario is already in incident, recovered, or silenced.",
            }
        state["chaos_queue"].pop(chosen_index)
        _degrade(state, chosen, "chaos", "operator")
        notices = list(state.pop("_notices", []))
        _write(state)
        outcome = {
            "status": "TRIGGERED",
            "service": _present(chosen),
            "chaos_remaining": len(state["chaos_queue"]),
        }
    if _emit_notices(notices):
        with _lock:
            state = _read()
            service = state["services"].get(outcome["service"]["service_id"])
            if service:
                outcome["service"] = _present(service)
    return outcome


def get_logs(service: str | None = None, level: str | None = None):
    with _lock:
        state = _read()
    logs = []
    for item in state["services"].values():
        if item["status"] == "HEALTHY":
            continue
        logs.append({
            "timestamp": item["log_timestamp"],
            "service": item["service_id"],
            "level": item["log_level"],
            "message": item["log_message"],
        })
    if service:
        logs = [item for item in logs if item["service"] == service]
    if level:
        logs = [item for item in logs if item["level"] == level]
    return logs


def get_metrics(service: str | None = None):
    with _lock:
        state = _read()
    metrics = {}
    for item in state["services"].values():
        metrics[item["service_id"]] = {
            "status": item["status"],
            "error_rate": item["error_rate"],
            "version": item["version"],
            "log_level": item["log_level"],
            "issue_type": item["issue_type"],
            "impact_summary": item["impact_summary"],
            "recommended_action": item["scenario_action"],
            "recommended_rollback": item["scenario_target"],
            "target": item["scenario_target"],
        }
    if service:
        return metrics.get(service, {})
    return metrics


def get_deployments(service: str | None = None):
    with _lock:
        state = _read()
    deployments = list(state["deployments"])
    if service:
        deployments = [item for item in deployments if item["service"] == service]
    return deployments


def apply_rollback_state(service: str, target_version: str):
    return remediate(service, "rollback", target_version)


if __name__ == "__main__":
    fleet = reset_fleet()
    print(
        f"Fleet ready. Active {fleet['summary']['active']}, "
        f"healthy {fleet['summary']['healthy']}, "
        f"SEV-1 {fleet['summary']['critical']}."
    )
