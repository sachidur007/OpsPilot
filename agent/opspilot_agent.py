import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout

import boto3
from botocore.config import Config
from dotenv import load_dotenv

from mcp_server.tools.ops_tools import (
    tool_get_fleet,
    tool_get_service_status,
    tool_reject,
    tool_remediate,
    tool_reset_fleet,
    tool_store_analysis,
    tool_trigger_chaos,
)
from simulator.scenarios import ACTIONS

load_dotenv()

MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
REGION = os.getenv("AWS_REGION", "us-east-1")
_BEDROCK_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bedrock")


class OpsPilotAgent:
    def __init__(self, region_name: str = REGION):
        self.region_name = region_name
        self._bedrock = None

    def _client(self):
        if self._bedrock is None:
            self._bedrock = boto3.client(
                "bedrock-runtime",
                region_name=self.region_name,
                config=Config(connect_timeout=2, read_timeout=8, retries={"max_attempts": 1}),
            )
        return self._bedrock

    def get_fleet_status(self):
        return tool_get_fleet()

    def analyze_incident(self, service_id: str):
        telemetry = tool_get_service_status(service_id)
        if telemetry.get("status") == "MISSING":
            return {"service_id": service_id, "status": "MISSING"}
        analysis = self._infer(service_id, telemetry)
        stored = tool_store_analysis(service_id, analysis)
        return {
            "service_id": service_id,
            "telemetry": telemetry,
            "analysis": analysis,
            "service": stored,
        }

    def finding_reply(self, result: dict, detail: bool = False) -> str:
        if result.get("status") == "MISSING":
            return f"{result.get('service_id')} is not in this fleet."
        analysis = result.get("analysis") or {}
        service = result.get("service") or {}
        telemetry = result.get("telemetry") or {}
        name = result.get("service_id") or service.get("service_id")
        status = service.get("status") or telemetry.get("status") or "UNKNOWN"
        version = service.get("version") or telemetry.get("version") or "unknown"
        rate = service.get("error_rate")
        if rate is None:
            rate = (telemetry.get("metrics") or {}).get("error_rate") or 0
        source = "Bedrock" if analysis.get("source") == "bedrock" else "Scenario fallback"
        action = analysis.get("recommended_action") or service.get("recommended_action")
        target = analysis.get("target_version_or_value") or service.get("target")
        cause = analysis.get("root_cause") or "Telemetry anomaly detected"
        if status == "HEALTHY":
            reply = f"{name} is healthy, live {version}, error rate 0. No fix is waiting. Source: {source}."
        else:
            severity = service.get("severity") or status
            reply = (
                f"{name} is {status}, {severity}, live {version}, {float(rate) * 100:.1f}% errors. "
                f"{cause}. Suggested fix: {action} to {target}. Source: {source}."
            )
        if detail and status != "HEALTHY":
            log = telemetry.get("log_message")
            if log:
                reply += f" The log says: {log}."
            reply += (
                f" Approve runs {action} to {target} and marks {name} healthy at error rate 0. "
                "Reject leaves it open as triage. Override picks a different action, and nothing runs until Execute."
            )
        return reply

    def execute_remediation(self, service_id: str, action: str, target: str):
        return tool_remediate(service_id, action, target)

    def reject_proposal(self, service_id: str):
        return tool_reject(service_id)

    def trigger_chaos(self):
        return tool_trigger_chaos()

    def reset_scene(self):
        return tool_reset_fleet()

    def _infer(self, service_id: str, telemetry: dict) -> dict:
        metrics = telemetry.get("metrics") or {}
        try:
            analysis = _BEDROCK_POOL.submit(self._bedrock_analysis, service_id, telemetry).result(timeout=8)
            analysis["source"] = "bedrock"
        except (Exception, FuturesTimeout) as exc:
            detail = " ".join(str(exc).split())
            analysis = {
                "root_cause": telemetry.get("root_cause")
                or metrics.get("impact_summary")
                or "Telemetry anomaly detected",
                "recommended_action": metrics.get("recommended_action") or "rollback",
                "target_version_or_value": metrics.get("target_version") or telemetry.get("target"),
                "source": "scenario-fallback",
                "fallback_reason": (detail or exc.__class__.__name__)[:240],
            }
        if analysis.get("recommended_action") not in ACTIONS:
            analysis["recommended_action"] = metrics.get("recommended_action") or "rollback"
        if not analysis.get("target_version_or_value"):
            analysis["target_version_or_value"] = metrics.get("target_version")
        return analysis

    def _bedrock_analysis(self, service_id: str, telemetry: dict) -> dict:
        prompt = f"""You are an Incident Commander AI. Analyze this telemetry and recommend a precise remediation.
Service: {service_id}
Metrics: {json.dumps(telemetry.get('metrics', {}))}
Logs: {json.dumps(telemetry.get('recent_errors', []))}
Deploy History: {json.dumps(telemetry.get('deployments', []))}

Respond strictly in JSON:
{{
  "root_cause": "brief explanation",
  "recommended_action": "rollback | unseal | cert_rotation | dns_flush | scale_pods | failover",
  "target_version_or_value": "version or target string"
}}"""
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "messages": [{"role": "user", "content": prompt}],
        })
        response = self._client().invoke_model(modelId=MODEL_ID, body=body)
        payload = json.loads(response.get("body").read())
        text = payload["content"][0]["text"]
        return _parse_json(text)


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    return json.loads(cleaned)


def _print_fleet(agent: OpsPilotAgent):
    fleet = agent.get_fleet_status()
    summary = fleet["summary"]
    print("\n================ OpsPilot Fleet ================")
    print(
        f"Active {summary['active']}  SEV-1 {summary['critical']}  "
        f"SEV-2 {summary['sev2']}  SEV-3 {summary['sev3']}  "
        f"Healthy {summary['healthy']}  Triage {summary['triage']}"
    )
    for item in fleet["active_incidents"]:
        print(
            f"  {item['severity']:6}  {item['status']:8}  {item['service_id']:28}  "
            f"{item['recommended_action']} -> {item['target']}"
        )
    print("===============================================")
    return fleet


if __name__ == "__main__":
    agent = OpsPilotAgent()
    if len(sys.argv) > 1 and sys.argv[1] == "chaos":
        print(json.dumps(agent.trigger_chaos(), indent=2))
        sys.exit(0)

    fleet = _print_fleet(agent)
    choice = input("\nService id, number, 'chaos', or 'quit': ").strip()
    if choice.lower() in {"q", "quit"}:
        sys.exit(0)
    if choice.lower() == "chaos":
        print(json.dumps(agent.trigger_chaos(), indent=2))
        sys.exit(0)

    incidents = fleet["active_incidents"]
    if choice.isdigit() and 1 <= int(choice) <= len(incidents):
        service_id = incidents[int(choice) - 1]["service_id"]
    else:
        service_id = choice

    result = agent.analyze_incident(service_id)
    analysis = result.get("analysis", {})
    print("\n[OpsPilot Analysis]")
    print(json.dumps(analysis, indent=2))
    print("\napprove / reject / override")
    decision = input("Decision: ").strip().lower()
    if decision == "approve":
        outcome = agent.execute_remediation(
            service_id,
            analysis["recommended_action"],
            analysis["target_version_or_value"],
        )
        print(json.dumps(outcome, indent=2))
    elif decision == "reject":
        print(json.dumps(agent.reject_proposal(service_id), indent=2))
    elif decision == "override":
        action = input(f"Action {ACTIONS}: ").strip()
        target = input("Target: ").strip()
        print(json.dumps(agent.execute_remediation(service_id, action, target), indent=2))
    else:
        print("No action taken.")
