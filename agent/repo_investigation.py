"""Repository findings and provision notes. They never change the fleet."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from agent.playbooks import match_playbooks
from agent.repo_coworker import answer as coworker_answer
from agent.repo_reader import RepoReadError, read_repository
from agent.work_order import build_work_order

DATA_DIR = Path(__file__).resolve().parents[1] / "simulator" / "data"
FINDINGS_NAME = "repo_findings.json"
WORK_NAME = "work"


class RepoDecisionError(Exception):
    """Approve or reject could not be recorded."""


def investigate_repository(
    source: str,
    data_dir: Path | None = None,
    record: bool = True,
    ask: str = "",
) -> dict:
    read = read_repository(source)
    finding = match_playbooks(read["bom"])
    finding["target_type"] = "repo"
    finding["repo"] = read["source"]
    finding["record_id"] = f"repo:{_slug(read['source'])}"
    finding["work"] = build_work_order(read, ask, finding)
    finding["brief"] = finding["work"]["summary"]
    finding["approve_enabled"] = True
    finding["decision"] = None
    finding["work_path"] = None
    _write_finding(finding, _root(data_dir))
    if record:
        from simulator.main import append_record

        text = _finding_text(finding)
        finding["record"] = append_record(finding["record_id"], "action", "agent", text)
    return finding


def discuss_repository(
    source: str,
    question: str,
    data_dir: Path | None = None,
    record: bool = True,
    channel: str = "text",
) -> dict:
    root = _root(data_dir)
    finding = _load_finding(source, root)
    reply = coworker_answer(finding, question)
    spoken = channel if channel in {"voice", "text"} else "text"
    if record:
        from simulator.main import append_record

        append_record(finding.get("record_id"), spoken, "user", question)
        finding["record"] = append_record(finding.get("record_id"), spoken, "agent", reply)
    return {"reply": reply, "repo": finding.get("repo"), "record_id": finding.get("record_id"), "finding": finding}


def approve_repository(source: str, data_dir: Path | None = None, record: bool = True) -> dict:
    root = _root(data_dir)
    finding = _load_finding(source, root)
    if finding.get("decision") == "approved":
        raise RepoDecisionError("This work was already approved.")
    if finding.get("decision") == "rejected":
        raise RepoDecisionError("This work was declined.")
    note = _work_note(finding)
    work_dir = root / WORK_NAME
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / f"{_slug(source)}.md"
    path.write_text(note, encoding="utf-8")
    finding["decision"] = "approved"
    finding["work_path"] = str(path)
    finding["approve_enabled"] = False
    work = finding.get("work")
    if isinstance(work, dict):
        for step in work.get("steps") or []:
            if isinstance(step, dict) and step.get("id") == "permission":
                step["state"] = "done"
                step["text"] = "Permission granted. I will not install or edit anything until you tell me to."
    _write_finding(finding, root)
    if record:
        from simulator.main import append_record

        text = f"Approved the plan for {source}. The repository was not modified."
        finding["record"] = append_record(finding.get("record_id"), "action", "user", text)
    return {"status": "CLEARED", "repo": source, "work_path": str(path), "finding": finding}


def reject_repository(source: str, data_dir: Path | None = None, record: bool = True) -> dict:
    root = _root(data_dir)
    finding = _load_finding(source, root)
    if finding.get("decision") == "rejected":
        raise RepoDecisionError("This finding was already rejected.")
    finding["decision"] = "rejected"
    finding["approve_enabled"] = False
    _write_finding(finding, root)
    if record:
        from simulator.main import append_record

        text = f"Declined the work for {source}. The repository was not modified."
        finding["record"] = append_record(finding.get("record_id"), "action", "user", text)
    return {"status": "REJECTED", "repo": source, "finding": finding}


def _root(data_dir: Path | None) -> Path:
    root = data_dir or DATA_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def _findings_file(root: Path) -> Path:
    return root / FINDINGS_NAME


def _load_all(root: Path) -> dict:
    path = _findings_file(root)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    findings = data.get("findings") if isinstance(data, dict) else None
    return findings if isinstance(findings, dict) else {}


def _load_finding(source: str, root: Path) -> dict:
    finding = _load_all(root).get(_slug(source))
    if not isinstance(finding, dict):
        raise RepoDecisionError("Investigate that repository before deciding.")
    return finding


def _write_finding(finding: dict, root: Path) -> None:
    findings = _load_all(root)
    findings[_slug(str(finding.get("repo") or ""))] = finding
    _findings_file(root).write_text(json.dumps({"findings": findings}, indent=2), encoding="utf-8")


def _slug(source: str) -> str:
    digest = hashlib.sha256(source.strip().encode()).hexdigest()[:16]
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", source.strip()).strip("-").lower()[:24]
    return f"{stem or 'repo'}-{digest}"


def _finding_text(finding: dict) -> str:
    repo = finding.get("repo")
    brief = finding.get("brief")
    if brief:
        return f"Repository {repo}. {brief}"
    if finding.get("status") != "verified":
        return f"Repository {repo}. Nothing verified in the bill of materials. No fix is proposed."
    advisories = ", ".join(finding.get("advisories") or [])
    return (
        f"Repository {repo}. {finding.get('summary')} "
        f"Provision: {finding.get('provision')} to {finding.get('target')}. Advisories: {advisories}."
    )


def _work_note(finding: dict) -> str:
    work = finding.get("work") if isinstance(finding.get("work"), dict) else {}
    lines = [
        "# Work",
        "",
        f"Repository: {finding.get('repo')}",
        f"Project: {work.get('project')}",
        f"Mission: {work.get('mission')}",
        "",
        "Permission granted.",
        "",
        "Plan:",
    ]
    for step in work.get("steps") or []:
        if isinstance(step, dict):
            lines.append(f"- {step.get('text')}")
    lines.extend(["", "This note does not modify the repository.", ""])
    return "\n".join(lines)
