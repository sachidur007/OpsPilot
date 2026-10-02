from simulator.main import get_logs, get_metrics, get_deployments

def tool_get_service_status(service_name: str):
    metrics = get_metrics(service_name)
    logs = get_logs(service=service_name, level="ERROR")
    deployments = get_deployments(service_name)
    
    return {
        "service": service_name,
        "metrics": metrics,
        "recent_errors_count": len(logs),
        "latest_deployment": deployments[-1] if deployments else None
    }

def tool_query_logs(service_name: str = None, level: str = None):
    return get_logs(service=service_name, level=level)

def tool_query_metrics(service_name: str = None):
    return get_metrics(service_name)

def tool_get_deployment_details(service_name: str = None):
    return get_deployments(service_name)

def tool_execute_rollback(service_name: str, target_version: str):
    # Simulation of a rollback action decision
    return {
        "status": "SUCCESS",
        "service": service_name,
        "rolled_back_to": target_version,
        "message": f"Service {service_name} successfully rolled back to {target_version}."
    }

def tool_verify_recovery(service_name: str):
    return {
        "service": service_name,
        "status": "HEALTHY",
        "error_rate": "0.05%",
        "p99_latency_ms": 280,
        "verified": True
    }
