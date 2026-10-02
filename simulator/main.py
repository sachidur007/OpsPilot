import json

def load_simulated_state():
    return {
        "status": "degraded",
        "services": {
            "checkout-api": {"error_rate": 0.187, "latency_ms": 1450, "version": "v42"},
            "payment-service": {"status": "timeout", "version": "v12"}
        }
    }

if __name__ == "__main__":
    print("Simulator Initialized:", json.dumps(load_simulated_state(), indent=2))
