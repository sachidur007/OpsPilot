"""Alexa+ adapter. It only calls the existing OpsPilot agent."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from simulator.main import _named_service, append_record
from simulator.scenarios import SCENARIOS

_SERVICES = {item["service"]: {} for item in SCENARIOS}
_HELP = (
    "Say what's wrong with payments. "
    "Then say approve to run the suggested fix, or reject to leave it in triage."
)


def handle_alexa(body: dict, agent) -> dict:
    if not isinstance(body, dict):
        return _say("Ask what's wrong with payments.", {}, end=True)
    if not _fresh(body):
        return _say("That request is too old. Ask again.", {}, end=True)
    skill_id = os.environ.get("ALEXA_SKILL_ID", "").strip()
    if skill_id:
        got = ((body.get("session") or {}).get("application") or {}).get("applicationId")
        if got != skill_id:
            return _say("This skill is not recognized.", {}, end=True)

    request = body.get("request") or {}
    attributes = dict((body.get("session") or {}).get("attributes") or {})
    kind = request.get("type")
    if kind == "LaunchRequest":
        return _say("OpsPilot. " + _HELP, attributes, end=False)
    if kind == "SessionEndedRequest":
        return _say("", attributes, end=True)
    if kind != "IntentRequest":
        return _say(_HELP, attributes, end=False)

    intent = request.get("intent") or {}
    name = intent.get("name") or ""
    if name in {"AMAZON.StopIntent", "AMAZON.CancelIntent"}:
        return _say("Standing by.", {}, end=True)
    if name == "AMAZON.HelpIntent":
        return _say(_HELP, attributes, end=False)
    if name == "WhatsWrongIntent":
        return _whats_wrong(agent, _slot(intent, "service"), attributes)
    if name == "ApproveIntent":
        return _approve(agent, attributes)
    if name == "RejectIntent":
        return _reject(agent, attributes)
    return _say(_HELP, attributes, end=False)


def _whats_wrong(agent, spoken: str, attributes: dict) -> dict:
    service_id = _named_service(spoken, _SERVICES) if spoken else None
    if not service_id:
        return _say("Name a service on this board. For example, what's wrong with payments.", attributes, end=False)
    result = agent.analyze_incident(service_id)
    speech = agent.finding_reply(result)
    _remember(service_id, spoken, speech)
    analysis = result.get("analysis") or {}
    service = result.get("service") or {}
    status = service.get("status") or result.get("status")
    action = analysis.get("recommended_action") or service.get("recommended_action") or ""
    target = analysis.get("target_version_or_value") or service.get("target") or ""
    if status in {"HEALTHY", "MISSING"} or not action or not target:
        return _say(speech, {}, end=False)
    return _say(
        speech + " Say approve to run it, or reject to leave it in triage.",
        {
            "pending_service_id": service_id,
            "pending_action": action,
            "pending_target": target,
        },
        end=False,
    )


def _approve(agent, attributes: dict) -> dict:
    service_id = attributes.get("pending_service_id")
    action = attributes.get("pending_action")
    target = attributes.get("pending_target")
    if not service_id or not action or not target:
        return _say("Nothing is waiting. Ask what's wrong with payments first.", attributes, end=False)
    result = agent.execute_remediation(service_id, action, target)
    status = result.get("status")
    if status == "SUCCESS" or result.get("health") == "HEALTHY":
        speech = f"Approved. {action} to {target} is done. {service_id} is healthy, error rate 0."
    elif status == "ALREADY_HEALTHY":
        speech = f"{service_id} is already healthy."
    else:
        speech = f"Approve did not run. {service_id} is still open."
    _remember(service_id, "approve", speech)
    return _say(speech, {}, end=True)


def _reject(agent, attributes: dict) -> dict:
    service_id = attributes.get("pending_service_id")
    if not service_id:
        return _say("Nothing is waiting. Ask what's wrong with payments first.", attributes, end=False)
    result = agent.reject_proposal(service_id)
    if result.get("status") == "TRIAGE":
        speech = f"Rejected. {service_id} stays open as triage."
    else:
        speech = f"Reject did not change {service_id}."
    _remember(service_id, "reject", speech)
    return _say(speech, {}, end=True)


def _slot(intent: dict, name: str) -> str:
    slot = (intent.get("slots") or {}).get(name) or {}
    value = slot.get("value") or ""
    return " ".join(str(value).split())


def _remember(service_id: str, user_text: str, agent_text: str) -> None:
    if user_text:
        append_record(service_id, "voice", "user", user_text[:600])
    if agent_text:
        append_record(service_id, "voice", "agent", agent_text[:2200])


def _fresh(body: dict) -> bool:
    stamp = ((body.get("request") or {}).get("timestamp") or "").strip()
    if not stamp:
        return True
    try:
        seen = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    age = abs((datetime.now(timezone.utc) - seen).total_seconds())
    return age <= 150


def _say(text: str, attributes: dict, end: bool) -> dict:
    speech = {"type": "PlainText", "text": text} if text else None
    response: dict = {"shouldEndSession": end}
    if speech:
        response["outputSpeech"] = speech
    return {"version": "1.0", "sessionAttributes": attributes, "response": response}
