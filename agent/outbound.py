"""Slack and Jira posts. Both stay idle unless the operator put real credentials in .env."""

from __future__ import annotations

import os

import requests

_SLACK_PREFIX = "https://hooks.slack.com/"


def slack_configured() -> bool:
    return os.getenv("SLACK_WEBHOOK_URL", "").strip().startswith(_SLACK_PREFIX)


def jira_configured() -> bool:
    return all(
        os.getenv(name, "").strip()
        for name in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY")
    )


def post_slack(service: str, severity: str | None, action: str, actor: str) -> bool:
    url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not url.startswith(_SLACK_PREFIX):
        return False
    payload = {
        "text": f"{service} {severity or 'none'} {action} decided by {actor}",
        "service": service,
        "severity": severity,
        "action": action,
        "actor": actor,
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        return False
    return True


def create_jira_issue(service: str, severity: str | None, action: str) -> str | None:
    auth = _jira_auth()
    if not auth:
        return None
    base, _email, _token, project = auth
    summary = f"{service} {severity or 'alert'}: {action}"[:255]
    body = {
        "fields": {
            "project": {"key": project},
            "summary": summary,
            "issuetype": {"name": "Task"},
            "description": _adf(f"{severity or 'alert'}. Suggested action: {action}."),
        }
    }
    try:
        response = requests.post(
            f"{base}/rest/api/3/issue",
            json=body,
            auth=(_email, _token),
            timeout=8,
        )
        response.raise_for_status()
        key = response.json().get("key")
    except (requests.RequestException, ValueError):
        return None
    return key if isinstance(key, str) and key else None


def comment_jira(issue_key: str | None, text: str) -> bool:
    if not issue_key:
        return False
    auth = _jira_auth()
    if not auth:
        return False
    base, email, token, _project = auth
    try:
        response = requests.post(
            f"{base}/rest/api/3/issue/{issue_key}/comment",
            json={"body": _adf(text)},
            auth=(email, token),
            timeout=8,
        )
        response.raise_for_status()
    except requests.RequestException:
        return False
    return True


def _jira_auth() -> tuple[str, str, str, str] | None:
    base = os.getenv("JIRA_BASE_URL", "").strip().rstrip("/")
    email = os.getenv("JIRA_EMAIL", "").strip()
    token = os.getenv("JIRA_API_TOKEN", "").strip()
    project = os.getenv("JIRA_PROJECT_KEY", "").strip()
    if not base.startswith("https://") or not email or not token or not project:
        return None
    return base, email, token, project


def _adf(text: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": " ".join(text.split())[:2000]}],
            }
        ],
    }
