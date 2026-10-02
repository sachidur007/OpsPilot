import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
STATE_FILE = DATA_DIR / "deployments.json"

def get_logs(service: str = None, level: str = None):
    if not (DATA_DIR / "logs.json").exists():
        return []
    with open(DATA_DIR / "logs.json", "r") as f:
        logs = json.load(f)
    if service:
        logs = [l for l in logs if l["service"] == service]
    if level:
        logs = [l for l in logs if l["level"] == level]
    return logs

def get_metrics(service: str = None):
    if not (DATA_DIR / "metrics.json").exists():
        return {}
    with open(DATA_DIR / "metrics.json", "r") as f:
        metrics = json.load(f)
    if service:
        return metrics.get(service, {})
    return metrics

def get_deployments(service: str = None):
    if not STATE_FILE.exists():
        return []
    with open(STATE_FILE, "r") as f:
        deployments = json.load(f)
    if service:
        deployments = [d for d in deployments if d["service"] == service]
    return deployments

def apply_rollback_state(service: str, target_version: str):
    deployments = get_deployments()
    new_entry = {
        "deployment_id": f"dep-rollback-{target_version}",
        "service": service,
        "version": target_version,
        "timestamp": "2026-10-03T01:19:00Z",
        "status": "SUCCESS",
        "changes": f"Automated rollback to {target_version} performed by OpsPilot Agent"
    }
    deployments.append(new_entry)
    with open(STATE_FILE, "w") as f:
        json.dump(deployments, f, indent=2)
    return new_entry

if __name__ == "__main__":
    print(f"Simulator ready. Currently loaded services: {len(get_metrics())}")
