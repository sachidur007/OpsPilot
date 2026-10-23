"""Match a bill of materials against advisory playbooks. No model call."""

from __future__ import annotations

import json
from pathlib import Path

PLAYBOOKS_FILE = Path(__file__).with_name("playbooks.json")


def load_playbooks(path: Path | None = None) -> list[dict]:
    raw = json.loads((path or PLAYBOOKS_FILE).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def match_playbooks(bom: list[dict], playbooks: list[dict] | None = None) -> dict:
    books = playbooks if playbooks is not None else load_playbooks()
    matches = []
    for book in books:
        evidence = [
            item for item in bom
            if item.get("ecosystem") == book.get("ecosystem")
            and item.get("name") == book.get("name")
            and _below(item.get("version"), book.get("affected_below"))
        ]
        if evidence:
            matches.append((book, evidence))
    if not matches:
        return {
            "status": "unverified",
            "source": "unverified",
            "summary": _unverified_summary(bom, books),
            "advisories": [],
            "provision": None,
            "target": None,
            "evidence": [],
            "bom": bom,
            "approve_enabled": False,
        }
    book, evidence = matches[0]
    extra = len(matches) - 1
    summary = str(book.get("summary") or "A playbook matched this repository.")
    if extra:
        summary = f"{summary} {extra} more playbook match{'es' if extra != 1 else ''}."
    return {
        "status": "verified",
        "source": "playbook",
        "summary": summary,
        "advisories": list(book.get("advisories") or []),
        "provision": book.get("provision"),
        "target": book.get("target"),
        "evidence": evidence,
        "bom": bom,
        "approve_enabled": bool(book.get("provision") and book.get("target")),
        "playbook_id": book.get("id"),
    }


def _unverified_summary(bom: list[dict], books: list[dict]) -> str:
    notes = []
    for book in books:
        present = [
            item for item in bom
            if item.get("ecosystem") == book.get("ecosystem")
            and item.get("name") == book.get("name")
            and item.get("version")
        ]
        if not present:
            continue
        versions = ", ".join(sorted({str(item["version"]) for item in present}))
        advisories = list(book.get("advisories") or [])
        advisory_label = ", ".join(advisories) or "the playbook"
        verb = "does" if len(advisories) == 1 else "do"
        package = "PHP" if book.get("name") == "php" else book.get("name")
        notes.append(
            f"{package} {versions} is in this repository. "
            f"That is at or above {book.get('affected_below')}, so {advisory_label} {verb} not apply."
        )
    if notes:
        return " ".join(notes) + " No fix is proposed."
    if not bom:
        return "This repository has no manifests the reader understands. No fix is proposed."
    return f"Read {len(bom)} manifest entries. Nothing matches a known playbook. No fix is proposed."


def _below(version: object, ceiling: object) -> bool:
    left = _parts(version)
    right = _parts(ceiling)
    if left is None or right is None:
        return False
    width = max(len(left), len(right))
    left = left + (0,) * (width - len(left))
    right = right + (0,) * (width - len(right))
    return left < right


def _parts(version: object) -> tuple[int, ...] | None:
    if not isinstance(version, str) or not version.strip():
        return None
    numbers = []
    for piece in version.split("."):
        digits = []
        for char in piece:
            if char.isdigit():
                digits.append(char)
            else:
                break
        if not digits:
            break
        numbers.append(int("".join(digits)))
    return tuple(numbers) or None
