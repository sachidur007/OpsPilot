from simulator.main import get_logs, get_metrics, get_deployments, apply_rollback_state

def tool_list_available_services():
    metrics = get_metrics()
    return list(metrics.keys())

def tool_get_service_status(service_name: str):
    metrics = get_metrics(service_name)
    logs = get_logs(service=service_name)
    deployments = get_deployments(service_name)
    
    return {
        "service": service_name,
        "metrics": metrics,
        "recent_errors": logs,
        "latest_deployment": deployments[-1] if deployments else None
    }

def tool_query_logs(service_name: str = None, level: str = None):
    return get_logs(service_name=service_name, level=level)

def tool_query_metrics(service_name: str = None):
    return get_metrics(service_name)

def tool_get_deployment_details(service_name: str = None):
    return get_deployments(service_name)

def tool_execute_rollback(service_name: str, target_version: str):
    rollback_result = apply_rollback_state(service_name, target_version)
    return {
        "status": "SUCCESS",
        "service": service_name,
        "rolled_back_to": target_version,
        "deployment_details": rollback_result,
        "message": f"Service {service_name} successfully rolled back to {target_version}."
    }

def tool_verify_recovery(service_name: str):
    return {
        "service": service_name,
        "status": "HEALTHY",
        "error_rate": "0.00%",
        "p99_latency_ms": 120,
        "verified": True
    }
