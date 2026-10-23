"""Four-part coworker reply. It reads the fleet record and a handed-off repository."""

from __future__ import annotations

SCOPE_LINE = (
    "This reply reads the fleet record and the repository you handed over. "
    "It does not query live metrics, logs, or traces."
)


def build_coworker(_reply: str, service_id: str | None = None, repo_finding: dict | None = None) -> dict:
    from simulator.main import budget_view, get_service_record

    situation, insight = _situation(service_id, repo_finding, get_service_record)
    knowledge = _knowledge(repo_finding)
    return {
        "situation": situation,
        "insight": insight,
        "knowledge": knowledge,
        "token_budget": budget_view(),
        "scope": SCOPE_LINE,
    }


def _situation(service_id: str | None, repo_finding: dict | None, get_service_record) -> tuple[str, str]:
    if repo_finding:
        work = repo_finding.get("work") if isinstance(repo_finding.get("work"), dict) else {}
        situation = str(work.get("summary") or repo_finding.get("brief") or repo_finding.get("summary") or "Repository plan.")
        insight = f"{repo_finding.get('summary') or 'Repository finding.'} Source: {repo_finding.get('source') or 'repository'}."
        return " ".join(situation.split()), " ".join(insight.split())

    record = None
    if service_id and not str(service_id).startswith("repo:"):
        record = get_service_record(service_id)
    if not record or record.get("status") == "MISSING":
        return (
            "No open incident is selected on the fleet record.",
            "No finding is stored for this turn. Source: fleet record.",
        )
    name = record["service_id"]
    if record.get("status") == "HEALTHY":
        forecast = record.get("forecast")
        situation = f"{name} is healthy on the fleet record."
        if forecast:
            situation += f" {forecast}."
        return situation, "No open finding. Source: fleet record."

    rate = float(record.get("error_rate") or 0) * 100
    situation = (
        f"{name} is open, {record.get('severity') or record.get('status')}, "
        f"{rate:.1f}% errors. Suggested {record.get('recommended_action')} to {record.get('target')}."
    )
    source = "Bedrock" if record.get("proposal_source") == "bedrock" else "Scenario fallback"
    cause = record.get("root_cause") or record.get("impact_summary") or "Telemetry anomaly detected"
    insight = f"{cause}. Source: {source}."
    reason = record.get("fallback_reason")
    if reason:
        insight += f" {reason}"
    return " ".join(situation.split()), " ".join(insight.split())


def _knowledge(repo_finding: dict | None) -> str:
    parts = [
        "From agent/project_knowledge.py: the board talks to the agent on port 8000, "
        "and the fleet record lives in simulator/main.py."
    ]
    docs = []
    if repo_finding:
        work = repo_finding.get("work") if isinstance(repo_finding.get("work"), dict) else {}
        docs = work.get("instructions") or []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        path = str(doc.get("path") or "")
        if not path.lower().startswith("readme"):
            continue
        excerpt = doc.get("excerpt") or doc.get("title") or ""
        parts.append(f"README {path}: {excerpt}")
        break
    return " ".join(" ".join(part.split()) for part in parts if part)[:900]
