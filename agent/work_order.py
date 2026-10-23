"""A side-worker plan for one repository. Nothing is installed or edited here until asked."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

_INSTALL = (
    "pip", "pip3", "npm", "pnpm", "yarn", "mvn", "go", "composer", "bundle",
)
_DOC_COMMAND = (
    r"`((?:npm|pnpm|yarn|pip3?|python3? -m pip|mvn|go|composer|bundle) [^`\n]+)`"
)


def build_work_order(read: dict, ask: str = "", playbook: dict | None = None) -> dict:
    docs = [item for item in (read.get("docs") or []) if isinstance(item, dict)]
    bom = [item for item in (read.get("bom") or []) if isinstance(item, dict)]
    project = _project_name(str(read.get("source") or ""), docs)
    install = _install_from_docs(docs) or _default_install(bom)
    depends = _depends(bom)
    mission = " ".join((ask or "").split()) or "No task yet. Orient on this repository and wait."
    steps = [
        {"id": "instructions", "state": "done", "text": _instruction_step(docs)},
        {"id": "dependencies", "state": "done", "text": depends},
        {"id": "next", "state": "waiting", "text": _next_step(mission, install)},
        {
            "id": "permission",
            "state": "waiting",
            "text": "I will not install or edit anything until you approve.",
        },
    ]
    if playbook and playbook.get("status") == "verified":
        steps.insert(2, {
            "id": "context",
            "state": "done",
            "text": (
                "A known advisory matches something in this tree. "
                "That is context for the task, not the task, unless you ask for it."
            ),
        })
    summary = _summary(project, mission, depends, install, docs)
    return {
        "mission": mission,
        "project": project,
        "summary": summary,
        "instructions": docs,
        "depends_on": depends,
        "install": install,
        "steps": steps,
        "permission": "Approve to let me start. I still will not run an install until you tell me to after that.",
    }


def reply(finding: dict, question: str) -> str:
    work = finding.get("work") if isinstance(finding.get("work"), dict) else {}
    asked = " ".join((question or "").split())
    if wants_run(asked):
        if finding.get("decision") != "approved":
            return (
                "I need approval before I install or edit anything. "
                + str(work.get("permission") or "Approve the plan first.")
            )
        return run_install(finding)
    summary = str(work.get("summary") or "")
    if not asked or _asks_for_plan(asked):
        lines = [summary] if summary else []
        for step in work.get("steps") or []:
            if not isinstance(step, dict):
                continue
            mark = "Done." if step.get("state") == "done" else "Waiting."
            lines.append(f"{mark} {step.get('text')}")
        return " ".join(lines) or "I do not have a plan for this repository yet."
    return (
        f"{summary} Tell me the task, ask what I would do next, or approve and then tell me to install."
    ).strip()


def wants_run(question: str) -> bool:
    lowered = question.lower()
    if any(word in lowered for word in ("what", "why", "how", "should", "would")):
        return False
    return any(cue in lowered for cue in ("do it", "go ahead", "install", "run it", "set it up", "start working"))


def run_install(finding: dict) -> str:
    source = str(finding.get("repo") or "")
    if source.startswith(("https://", "http://", "ssh://", "git@", "file://")):
        return (
            "This handoff was a git URL. I read a temporary copy and I will not install into it. "
            "Run me from the CLI inside a local checkout when you want the install."
        )
    root = Path(source).expanduser().resolve()
    if not root.is_dir():
        return "The local checkout is not there, so I did not run anything."
    command = install_argv(finding)
    if not command:
        return "I do not see an install command in the project instructions or dependency files. I did not run anything."
    shown = " ".join(command)
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"I tried `{shown}` in {root.name}. It did not finish. {exc.__class__.__name__}."
    tail = " ".join(((completed.stdout or "") + "\n" + (completed.stderr or "")).split())[-400:]
    if completed.returncode == 0:
        detail = f" {tail}" if tail else ""
        return f"I ran `{shown}` in {root.name}. It finished.{detail} The repository files I was given were otherwise left as they were."
    return f"I ran `{shown}` in {root.name}. It exited {completed.returncode}. {tail}".strip()


def install_argv(finding: dict) -> list[str] | None:
    work = finding.get("work") if isinstance(finding.get("work"), dict) else {}
    quoted = work.get("install")
    if isinstance(quoted, list) and quoted and _allowed(quoted):
        return [str(part) for part in quoted]
    return _default_install(finding.get("bom") or [])


def _project_name(source: str, docs: list[dict]) -> str:
    for doc in docs:
        title = str(doc.get("title") or "").strip()
        if title:
            return title[:120]
    name = Path(source.rstrip("/")).name
    return name or "This repository"


def _instruction_step(docs: list[dict]) -> str:
    if not docs:
        return "No project instructions at the root. I used the dependency files."
    names = ", ".join(str(doc.get("path")) for doc in docs[:4])
    return f"Read {names}."


def _depends(bom: list[dict]) -> str:
    files: dict[str, int] = {}
    for item in bom:
        path = str(item.get("path") or "")
        if path:
            files[path] = files.get(path, 0) + 1
    if not files:
        return "I did not find a dependency file I recognize."
    shown = [f"{path} ({count})" for path, count in list(files.items())[:4]]
    extra = len(files) - len(shown)
    more = f" and {extra} more" if extra else ""
    return "Dependencies are declared in " + ", ".join(shown) + more + "."


def _next_step(mission: str, install: list[str] | None) -> str:
    command = f" The setup command I would run is `{' '.join(install)}`. I have not run it." if install else ""
    if mission.startswith("No task yet"):
        return "Tell me the task in the record." + command
    return f"You asked: {mission}.{command}"


def _summary(project: str, mission: str, depends: str, install: list[str] | None, docs: list[dict]) -> str:
    command = f" Setup command, not yet run: {' '.join(install)}." if install else ""
    spoken_mission = mission if mission.endswith(".") else f"{mission}."
    read = _instruction_step(docs)
    return f"{project}. {spoken_mission} {read} {depends}{command} I will not install or edit anything until you approve."


def _install_from_docs(docs: list[dict]) -> list[str] | None:
    import re

    pattern = re.compile(_DOC_COMMAND, re.IGNORECASE)
    for doc in docs:
        found = pattern.search(str(doc.get("excerpt") or ""))
        if not found:
            continue
        try:
            argv = shlex.split(found.group(1))
        except ValueError:
            continue
        if _allowed(argv):
            return argv
    return None


def _default_install(bom: list[dict]) -> list[str] | None:
    names = {Path(str(item.get("path") or "")).name for item in bom}
    if "requirements.txt" in names:
        return ["python3", "-m", "pip", "install", "-r", "requirements.txt"]
    if "package.json" in names:
        return ["npm", "install"]
    if "pom.xml" in names:
        return ["mvn", "-q", "-DskipTests", "dependency:resolve"]
    if "go.mod" in names:
        return ["go", "mod", "download"]
    if "composer.json" in names:
        return ["composer", "install"]
    if "Gemfile" in names:
        return ["bundle", "install"]
    return None


def _allowed(argv: list) -> bool:
    if not argv:
        return False
    if argv[0] in {"python", "python3"} and len(argv) >= 4 and argv[1] == "-m" and argv[2] == "pip":
        return True
    return str(argv[0]) in _INSTALL


def _asks_for_plan(question: str) -> bool:
    lowered = question.lower()
    return any(
        cue in lowered
        for cue in ("what would you", "what will you", "what next", "the plan", "walk me", "talk about", "what do you")
    )
