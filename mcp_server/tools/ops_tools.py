from simulator.main import (
    get_deployments,
    get_fleet,
    get_logs,
    get_metrics,
    get_service_record,
    remediate,
    reject_incident,
    reset_fleet,
    store_analysis,
    trigger_chaos,
)
from simulator.scenarios import SCENARIOS


def tool_list_available_services():
    return [item["service"] for item in SCENARIOS]


def tool_get_fleet():
    return get_fleet()


def tool_get_service_status(service_name: str):
    record = get_service_record(service_name)
    if not record:
        return {"service": service_name, "status": "MISSING"}
    return record


def tool_query_logs(service_name: str | None = None, level: str | None = None):
    return get_logs(service_name, level)


def tool_query_metrics(service_name: str | None = None):
    return get_metrics(service_name)


def tool_get_deployment_details(service_name: str | None = None):
    return get_deployments(service_name)


def tool_execute_rollback(service_name: str, target_version: str):
    return remediate(service_name, "rollback", target_version)


def tool_remediate(service_id: str, action: str, target: str):
    return remediate(service_id, action, target)


def tool_reject(service_id: str):
    return reject_incident(service_id)


def tool_trigger_chaos():
    return trigger_chaos()


def tool_reset_fleet():
    return reset_fleet()


def tool_store_analysis(service_id: str, analysis: dict):
    return store_analysis(service_id, analysis)


def tool_verify_recovery(service_name: str):
    record = get_service_record(service_name)
    if not record:
        return {"service": service_name, "verified": False, "status": "MISSING"}
    healthy = record["status"] == "HEALTHY"
    return {
        "service": service_name,
        "status": record["status"],
        "error_rate": record["error_rate"],
        "verified": healthy,
    }
