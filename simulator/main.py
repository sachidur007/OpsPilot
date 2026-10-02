import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

def get_logs(service: str = None, level: str = None):
    with open(DATA_DIR / "logs.json", "r") as f:
        logs = json.load(f)
    if service:
        logs = [l for l in logs if l["service"] == service]
    if level:
        logs = [l for l in logs if l["level"] == level]
    return logs

def get_metrics(service: str = None):
    with open(DATA_DIR / "metrics.json", "r") as f:
        metrics = json.load(f)
    if service:
        return metrics.get(service, {})
    return metrics

def get_deployments(service: str = None):
    with open(DATA_DIR / "deployments.json", "r") as f:
        deployments = json.load(f)
    if service:
        deployments = [d for d in deployments if d["service"] == service]
    return deployments

if __name__ == "__main__":
    print("--- Simulated Incident Scenarios ---")
    print("1. Checkout API Error Spike (v42):")
    print(json.dumps(get_metrics("checkout-api"), indent=2))
    print("\n2. Inventory Service OOM Memory Leak:")
    print(json.dumps(get_logs(service="inventory-service"), indent=2))
    print("\n3. Payment Service DB Connection Pool Exhaustion:")
    print(json.dumps(get_logs(service="payment-service"), indent=2))
