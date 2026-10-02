import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()

MCP_BASE_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000")

class OpsPilotAgent:
    def __init__(self, mcp_url: str = MCP_BASE_URL):
        self.mcp_url = mcp_url

    def fetch_services(self):
        res = requests.get(f"{self.mcp_url}/tools/services")
        return res.json() if res.status_code == 200 else []

    def fetch_service_status(self, service_name: str):
        res = requests.get(f"{self.mcp_url}/tools/status/{service_name}")
        return res.json() if res.status_code == 200 else {}

    def execute_rollback(self, service_name: str, target_version: str):
        payload = {"service_name": service_name, "target_version": target_version}
        res = requests.post(f"{self.mcp_url}/tools/rollback", json=payload)
        return res.json() if res.status_code == 200 else {}

    def verify_recovery(self, service_name: str):
        res = requests.get(f"{self.mcp_url}/tools/verify/{service_name}")
        return res.json() if res.status_code == 200 else {}

    def investigate_incident(self, service_name: str):
        print(f"\n[OpsPilot Agent] Starting Investigation: '{service_name}'...")

        status = self.fetch_service_status(service_name)
        metrics = status.get("metrics", {})
        latest_deploy = status.get("latest_deployment", {})
        errors = status.get("recent_errors", [])

        current_ver = latest_deploy.get("version", "unknown")
        ver_metrics = metrics.get(current_ver, {})
        target_version = ver_metrics.get("recommended_rollback", "previous_stable")

        analysis = {
            "target_service": service_name,
            "current_version": current_ver,
            "detected_issue_type": ver_metrics.get("issue_type", "Telemetry Anomaly"),
            "impact_summary": ver_metrics.get("impact_summary", "High Error Rate"),
            "critical_errors": errors
        }

        print("\n[OpsPilot Evidence Collected]")
        print(json.dumps(analysis, indent=2))

        print("\n[OpsPilot Plan Generated]")
        print(f"Root Cause: {ver_metrics.get('issue_type', 'System Error')} introduced in version {current_ver}.")
        print(f"Proposed Action: Execute rollback on '{service_name}' from {current_ver} -> {target_version}.")

        return {
            "requires_approval": True,
            "action": "rollback",
            "service": service_name,
            "target_version": target_version,
            "evidence": analysis
        }

if __name__ == "__main__":
    agent = OpsPilotAgent()
    available_services = agent.fetch_services()

    target = sys.argv[1] if len(sys.argv) > 1 else None

    if not target:
        print("\n================ OpsPilot Active Incidents Catalog ================")
        for index, srv in enumerate(available_services, start=1):
            print(f"{index:2d}. {srv}")
        print("===================================================================")
        
        choice = input("\nSelect service number or enter exact service name: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(available_services):
            target = available_services[int(choice) - 1]
        else:
            target = choice

    proposal = agent.investigate_incident(target)
    
    print("\n--- Human-in-the-Loop Confirmation Required ---")
    confirm = input(f"Approve rollback for '{proposal['service']}' to '{proposal['target_version']}'? (y/n): ")
    
    if confirm.lower() == 'y':
        rollback_res = agent.execute_rollback(proposal['service'], proposal['target_version'])
        print("\n[Rollback Result]:", json.dumps(rollback_res, indent=2))
        
        verify_res = agent.verify_recovery(proposal['service'])
        print("\n[Post-Rollback Verification]:", json.dumps(verify_res, indent=2))
    else:
        print("\nAction cancelled by user.")
