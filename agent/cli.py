"""Hand FleetOps a repository from the terminal.

    python -m agent.cli /path/to/repo --ask "set this up"
    python -m agent.cli /path/to/repo --approve
    python -m agent.cli /path/to/repo --run
"""

from __future__ import annotations

import argparse
import sys

from agent.repo_investigation import RepoDecisionError, approve_repository, investigate_repository
from agent.repo_reader import RepoReadError
from agent.work_order import reply, run_install


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FleetOps side worker for one repository.")
    parser.add_argument("repo", help="Local checkout or git URL")
    parser.add_argument("--ask", default="", help="The task to plan")
    parser.add_argument("--approve", action="store_true", help="Record permission to start")
    parser.add_argument("--run", action="store_true", help="Run the project's install after approval")
    args = parser.parse_args(argv)
    try:
        finding = investigate_repository(args.repo, ask=args.ask, record=False)
    except RepoReadError as exc:
        print(exc, file=sys.stderr)
        return 1
    _print_work(finding)
    if args.approve:
        try:
            result = approve_repository(args.repo, record=False)
        except RepoDecisionError as exc:
            print(exc, file=sys.stderr)
            return 2
        finding = result["finding"]
        print("Permission granted. The repository was not modified.")
    if args.run:
        if finding.get("decision") != "approved":
            print(reply(finding, "install the requirements"))
            return 2
        print(run_install(finding))
    return 0


def _print_work(finding: dict) -> None:
    work = finding.get("work") or {}
    print(work.get("project") or finding.get("repo"))
    print(work.get("summary") or "")
    for step in work.get("steps") or []:
        mark = "done" if step.get("state") == "done" else "waiting"
        print(f"- [{mark}] {step.get('text')}")
    print(work.get("permission") or "")


if __name__ == "__main__":
    raise SystemExit(main())
