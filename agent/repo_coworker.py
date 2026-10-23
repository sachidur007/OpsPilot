"""Answers about any repository, grounded in the manifests that were read."""

from __future__ import annotations

import re

_LABELS = {
    "java": "Java",
    "node": "Node",
    "python": "Python",
    "go": "Go",
    "ruby": "Ruby",
    "php": "PHP",
    "composer": "PHP packages",
    "docker": "container images",
}
_STOP = {
    "what", "happens", "happen", "upgrade", "upgrading", "updated", "update",
    "change", "changing", "bump", "bumping", "migrate", "migrating", "this",
    "that", "with", "from", "into", "about", "would", "could", "should",
    "does", "doing", "done", "want", "need", "know", "tell", "walk", "through",
    "repository", "project", "application", "version", "versions", "package",
    "library", "please", "just", "only", "they", "them", "your", "have",
}
_VERSION = re.compile(r"\b\d+\.\d+(?:\.\d+)?\b")


def brief(finding: dict) -> str:
    """What the repository is, and what FleetOps will and will not decide."""
    portrait = _portrait(finding.get("bom") or [])
    summary = " ".join(str(finding.get("summary") or "").split())
    advisory = ""
    if finding.get("status") == "verified" or "apply" in summary:
        advisory = summary
    closer = (
        "Ask what happens if you change one of these. "
        "I will not edit the repository, and I will not invent a target version."
    )
    return " ".join(part for part in (portrait, advisory, closer) if part)


def answer(finding: dict, question: str) -> str:
    if isinstance(finding.get("work"), dict):
        from agent.work_order import reply as work_reply

        return work_reply(finding, question)
    asked = " ".join((question or "").split())
    bom = [item for item in (finding.get("bom") or []) if isinstance(item, dict)]
    if not asked:
        return brief(finding)
    if not bom:
        return (
            "I read this repository and found no build manifests I understand. "
            "Point me at the file that pins the versions you want to change. "
            "I will not edit the repository."
        )
    matched = _match(asked, bom)
    if matched:
        return _consequence(asked, matched, bom, finding)
    if _mentions_change(asked):
        names = _sample_names(bom, 8)
        listed = ", ".join(names)
        return (
            f"I do not see that package in the manifests. "
            f"I can say what changes if you upgrade {listed}. "
            "I will not invent a result the files do not show, and I will not edit the repository."
        )
    if _is_general(asked):
        return brief(finding)
    names = _sample_names(bom, 8)
    listed = ", ".join(names)
    return (
        f"The manifests do not answer that directly. "
        f"I can say what changes if you upgrade {listed}. "
        "I will not invent a result the files do not show, and I will not edit the repository."
    )


def _portrait(bom: list[dict]) -> str:
    if not bom:
        return "I read this repository and found no build manifests I understand."
    groups: dict[str, list[dict]] = {}
    for item in bom:
        groups.setdefault(str(item.get("ecosystem") or "other"), []).append(item)
    parts = []
    labels = []
    for ecosystem, items in groups.items():
        label = _LABELS.get(ecosystem, ecosystem)
        labels.append(label)
        shown = _sample(items, 6)
        detail = ", ".join(shown)
        extra = len(items) - len(shown)
        more = f", and {extra} more" if extra else ""
        parts.append(f"{label} in the manifests: {detail}{more}.")
    opening = "This repository is " + " and ".join(labels) + "."
    return " ".join([opening, *parts])


def _consequence(question: str, matched: list[dict], bom: list[dict], finding: dict) -> str:
    by_name: dict[str, list[dict]] = {}
    for item in matched:
        by_name.setdefault(str(item.get("name")), []).append(item)
    chunks = []
    for name, items in list(by_name.items())[:4]:
        paths = sorted({str(item.get("path")) for item in items})
        versions = sorted({str(item.get("version")) for item in items if item.get("version")})
        where = " and ".join(paths[:3])
        current = versions[0] if len(versions) == 1 else ", ".join(versions)
        if current:
            chunks.append(f"{name} is {current} in {where}.")
        else:
            chunks.append(f"{name} is named in {where}, with no version I could read.")
    named = _VERSION.findall(question)
    verified_target = finding.get("target") if finding.get("status") == "verified" else None
    if named:
        asked_for = named[0]
        if verified_target and asked_for == verified_target:
            version_line = f"You asked about {asked_for}. That is the verified playbook target."
        else:
            version_line = (
                f"You asked about {asked_for}. That number is not a verified target, "
                "so I will not call it safe or unsafe."
            )
    elif verified_target and any(item.get("name") == "php" and item.get("ecosystem") == "php" for item in matched):
        version_line = f"The only verified target I have is {verified_target}."
    else:
        version_line = "I have not verified a replacement version, so I will not choose one."
    related = _related(matched, bom)
    related_line = f" Also in these manifests: {related}." if related else ""
    return (
        " ".join(chunks)
        + " "
        + version_line
        + " Changing it means editing that manifest and then rebuilding and retesting what depends on it."
        + related_line
        + " The manifests do not say whether the API, the tests, or the deploy step keep working."
        + " The repository is not modified."
    )


def _related(matched: list[dict], bom: list[dict]) -> str:
    names = {str(item.get("name")) for item in matched}
    ecosystems = {str(item.get("ecosystem")) for item in matched}
    others = []
    for item in bom:
        name = str(item.get("name"))
        if name in names or str(item.get("ecosystem")) not in ecosystems:
            continue
        if name not in others:
            others.append(name)
        if len(others) == 3:
            break
    return ", ".join(others)


def _match(question: str, bom: list[dict]) -> list[dict]:
    exact = [item for item in bom if item.get("name") and _mentions(question, str(item["name"]))]
    if exact:
        return exact
    tokens = [
        token for token in re.findall(r"[a-z][a-z0-9.+-]{3,}", question.lower())
        if token not in _STOP
    ]
    if not tokens:
        return []
    hits = []
    for item in bom:
        name = str(item.get("name") or "").lower()
        if name and any(token in name for token in tokens):
            hits.append(item)
    return hits


def _mentions(question: str, name: str) -> bool:
    if len(name) < 2:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(name.lower())}(?![a-z0-9])", question.lower()) is not None


def _mentions_change(question: str) -> bool:
    lowered = question.lower()
    return any(word in lowered for word in ("upgrade", "upgrading", "bump", "migrate", "migrating"))


def _is_general(question: str) -> bool:
    lowered = question.lower()
    cues = (
        "what is this", "what's this", "what is the repo", "walk me", "talk about",
        "what should", "what do i", "what do we", "don't know", "dont know",
        "how do i", "how do we", "upgrade it", "upgrade this", "help me",
        "where do i start", "what happens",
    )
    return any(cue in lowered for cue in cues)


def _sample(items: list[dict], limit: int) -> list[str]:
    shown = []
    seen = set()
    for item in items:
        name = str(item.get("name") or "unnamed")
        if name in seen:
            continue
        seen.add(name)
        version = item.get("version")
        shown.append(f"{name} {version}" if version else name)
        if len(shown) == limit:
            break
    return shown


def _sample_names(bom: list[dict], limit: int) -> list[str]:
    names = []
    for item in bom:
        name = str(item.get("name") or "")
        if name and name not in names:
            names.append(name)
        if len(names) == limit:
            break
    return names
