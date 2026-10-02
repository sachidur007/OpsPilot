from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from mcp_server.tools.ops_tools import (
    tool_get_service_status,
    tool_query_logs,
    tool_query_metrics,
    tool_get_deployment_details,
    tool_execute_rollback,
    tool_verify_recovery
)

app = FastAPI(title="OpsPilot MCP Server")

class RollbackRequest(BaseModel):
    service_name: str
    target_version: str

@app.get("/health")
def health_check():
    return {"status": "ok", "layer": "mcp-server"}

@app.get("/tools/status/{service_name}")
def get_status(service_name: str):
    return tool_get_service_status(service_name)

@app.get("/tools/logs")
def query_logs_endpoint(service: str = None, level: str = None):
    return tool_query_logs(service_name=service, level=level)

@app.get("/tools/metrics")
def query_metrics_endpoint(service: str = None):
    return tool_query_metrics(service_name=service)

@app.get("/tools/deployments")
def get_deployments_endpoint(service: str = None):
    return tool_get_deployment_details(service_name=service)

@app.post("/tools/rollback")
def rollback_endpoint(req: RollbackRequest):
    return tool_execute_rollback(req.service_name, req.target_version)

@app.get("/tools/verify/{service_name}")
def verify_endpoint(service_name: str):
    return tool_verify_recovery(service_name)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
