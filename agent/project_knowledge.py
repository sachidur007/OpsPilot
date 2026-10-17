"""Answer questions about this repository from the source files on disk."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {
    "venv",
    ".venv",
    ".voice-venv",
    "node_modules",
    ".git",
    "__pycache__",
    ".next",
    "clips",
    "frames",
    "recording",
    "story",
    "voice",
}
SUFFIXES = {".py", ".ts", ".tsx", ".md", ".css"}
STOP = {
    "about", "after", "also", "and", "are", "can", "does", "for", "from", "have",
    "how", "into", "that", "the", "this", "what", "when", "where", "which", "with",
    "work", "works", "you", "your", "tell", "please", "me", "explain", "entire",
    "project", "application", "repo", "code", "file",
}

_INCIDENT = (
    "what's wrong",
    "whats wrong",
    "what is wrong",
    "what wrong",
    "error rate",
    "how bad",
    "is it healthy",
    "status of",
)

_PROJECT = (
    "repo",
    "repository",
    "codebase",
    "source code",
    "this project",
    "this app",
    "this application",
    "the application",
    "the project",
    "entire application",
    "entire project",
    "entire repo",
    "pin to pin",
    "how does",
    "how do i",
    "how do you",
    "where is",
    "where are",
    "what file",
    "which file",
    "command center",
    "microphone",
    "the mic",
    "architecture",
    "bedrock",
    "what can you",
    "what can i",
    "help me",
    "how it works",
    "how this works",
    "the code",
    "in the code",
    "opspilot",
    "command record",
    "what commands",
    "which commands",
)

_BROAD = (
    "what is this",
    "what is opspilot",
    "explain the project",
    "explain this project",
    "entire application",
    "entire project",
    "entire repo",
    "pin to pin",
    "what can you",
    "what can i",
    "how does this work",
    "how does the app",
    "how does the application",
    "what commands",
    "help me",
)

_OVERVIEW = (
    "I'm OpsPilot. Talk to me normally, and ask when you want the product. "
    "The board talks only to the agent on port 8000. "
    "When you ask what's wrong with a service, I investigate it: Bedrock when the account allows it, otherwise I tell you the source is Scenario fallback. "
    "The fleet is the simulator, with 24 scenarios. Approve calls POST /agent/remediate. Reject calls POST /agent/reject. "
    "A service question calls POST /agent/analyze. Every turn is kept in simulator/data/command_record.json. "
    "Ask what's wrong with a service, how the fleet is, or how a button or file in this project works."
)


def is_incident_question(text: str) -> bool:
    lowered = text.lower()
    return any(cue in lowered for cue in _INCIDENT)


def is_project_question(text: str) -> bool:
    lowered = text.lower()
    if lowered.strip() in {"help", "commands", "command"}:
        return True
    return any(cue in lowered for cue in _PROJECT)


def answer_project(question: str) -> str:
    asked = " ".join(question.split())
    tokens = _tokens(asked)
    hits = _search(tokens)
    broad = _is_broad(asked)
    parts = [_OVERVIEW] if broad else ["I read this repository to answer that."]
    if not broad and not hits:
        parts.append(_OVERVIEW)
    if hits and not broad:
        parts.append("The closest source is:")
        for rel, lines in hits:
            excerpt = " ".join(lines)
            parts.append(f"{rel}: {excerpt}")
    elif not _is_broad(asked):
        parts.append("I could not find a closer file for those words. Ask about a file, a button, or a command.")
    return " ".join(parts)


def _is_broad(text: str) -> bool:
    lowered = text.lower().strip()
    return lowered in {"help", "commands", "command"} or any(cue in lowered for cue in _BROAD)


def _tokens(text: str) -> list[str]:
    words = []
    for raw in text.lower().replace("-", " ").replace("_", " ").split():
        word = "".join(ch for ch in raw if ch.isalnum())
        if len(word) < 4 or word in STOP:
            continue
        words.append(word)
    return words


def _search(tokens: list[str]) -> list[tuple[str, list[str]]]:
    if not tokens:
        return []
    ranked: list[tuple[int, str, list[str]]] = []
    for path in _files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = text.splitlines()
        rel = str(path.relative_to(ROOT))
        score = sum(" ".join(lines).lower().count(token) for token in tokens)
        if any(token in rel.lower() for token in tokens):
            score += 2
        picked = _excerpt(lines, tokens)
        if score > 0 and picked:
            ranked.append((score, rel, picked))
    ranked.sort(key=lambda item: item[0], reverse=True)
    chosen: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for _score, rel, picked in ranked:
        if rel in seen:
            continue
        seen.add(rel)
        chosen.append((rel, picked))
        if len(chosen) == 3:
            break
    return chosen


def _excerpt(lines: list[str], tokens: list[str]) -> list[str]:
    best_at = -1
    best = 0
    for index, line in enumerate(lines):
        score = sum(1 for token in tokens if token in line.lower())
        if score > best:
            best = score
            best_at = index
    if best_at < 0:
        return []
    picked = []
    for line in lines[best_at:best_at + 14]:
        clean = " ".join(line.strip().split())
        if len(clean) < 8 or clean.startswith(("import ", "from ")):
            continue
        picked.append(clean[:180])
        if len(picked) == 4:
            break
    return picked


def _files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [name for name in dirnames if name not in SKIP and not name.startswith(".")]
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix not in SUFFIXES or path.name == "project_knowledge.py":
                continue
            try:
                if path.stat().st_size > 200_000:
                    continue
            except OSError:
                continue
            yield path
