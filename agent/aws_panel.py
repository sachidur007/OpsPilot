"""The AWS calls this board already makes: Bedrock, CloudWatch Logs, and App Runner."""

from __future__ import annotations

import os

import boto3

from agent.telemetry import GROUP, REGION

APP_RUNNER_URL = os.getenv(
    "OPSPILOT_APP_RUNNER_URL",
    "https://yn6f6qpstp.us-east-1.awsapprunner.com",
).strip()

_described: dict | None = None


def interpret_log_groups(name: str, payload: dict | None, error: str | None) -> dict:
    if error:
        return {"exists": False, "error": error[:240]}
    names = []
    for group in (payload or {}).get("logGroups") or []:
        if isinstance(group, dict) and group.get("logGroupName"):
            names.append(group["logGroupName"])
    return {"exists": name in names, "error": None}


def describe_log_group(name: str = GROUP) -> dict:
    """One DescribeLogGroups call for the life of this process."""
    global _described
    if _described is not None:
        return _described
    try:
        client = boto3.client("logs", region_name=REGION)
        payload = client.describe_log_groups(logGroupNamePrefix=name, limit=50)
        _described = interpret_log_groups(name, payload, None)
    except Exception as exc:
        detail = " ".join(str(exc).split()) or exc.__class__.__name__
        _described = interpret_log_groups(name, None, detail)
    return _described


def aws_status() -> dict:
    from simulator.main import bedrock_view

    bedrock = bedrock_view()
    described = describe_log_group(GROUP)
    return {
        "model_id": bedrock.get("model_id") or os.getenv("BEDROCK_MODEL_ID", ""),
        "last_bedrock": bedrock.get("last_bedrock"),
        "log_group": GROUP,
        "log_group_status": described,
        "app_runner_url": APP_RUNNER_URL,
    }
