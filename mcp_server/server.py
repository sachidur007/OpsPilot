import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from agent.alexa_skill import handle_alexa, request_allowed
from agent.telemetry import tracer
from agent.voice import synthesize_speech

from agent.opspilot_agent import OpsPilotAgent
from agent.repo_investigation import (
    RepoDecisionError,
    approve_repository,
    discuss_repository,
    investigate_repository,
    reject_repository,
)
from agent.repo_reader import RepoReadError
from mcp_server.protocol import ops_mcp
from agent.aws_panel import aws_status
from agent.coworker_reply import SCOPE_LINE, build_coworker
from simulator.main import append_record, discuss, route_question, silence_service, stamp_coworker
from mcp_server.tools.ops_tools import (
    tool_get_deployment_details,
    tool_get_fleet,
    tool_get_service_status,
    tool_list_available_services,
    tool_query_logs,
    tool_query_metrics,
    tool_execute_rollback,
    tool_remediate,
    tool_reset_fleet,
    tool_declare_incident,
    tool_trigger_chaos,
    tool_verify_recovery,
)

agent = OpsPilotAgent()
protocol_app = ops_mcp.streamable_http_app(streamable_http_path="/", stateless_http=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with ops_mcp.session_manager.run():
        yield


app = FastAPI(title="FleetOps MCP Server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/protocol", protocol_app)


@app.middleware("http")
async def trace_http(request: Request, call_next):
    with tracer.start_as_current_span(f"{request.method} {request.url.path}") as span:
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.target", request.url.path)
        response = await call_next(request)
        span.set_attribute("http.status_code", response.status_code)
        return response


class RollbackRequest(BaseModel):
    service_name: str
    target_version: str


class RemediateRequest(BaseModel):
    service_id: str
    action: str
    target: str
    reason: str = ""


class ServiceRequest(BaseModel):
    service_id: str


class RejectRequest(BaseModel):
    service_id: str
    reason: str = ""


class AttributeInput(BaseModel):
    name: str = ""
    value: str = ""


class DeclareRequest(BaseModel):
    service_id: str
    title: str = ""
    severity: str = ""
    details: str = ""
    notes: str = ""
    links: list[str] = []
    attributes: list[AttributeInput] = []


class AnalyzeRequest(BaseModel):
    service_id: str | None = None
    repo: str | None = None
    ask: str | None = None


class RepoDecisionRequest(BaseModel):
    repo: str


class SpeakRequest(BaseModel):
    text: str


class RecordRequest(BaseModel):
    service_id: str | None = None
    channel: str
    role: str
    text: str


class DiscussRequest(BaseModel):
    service_id: str | None = None
    repo: str | None = None
    channel: str = "text"
    text: str


class SilenceRequest(BaseModel):
    service_id: str
    until: str


def _pack_discuss(payload: dict, repo_finding: dict | None = None) -> dict:
    reply = str(payload.get("reply") or "")
    if SCOPE_LINE not in reply:
        reply = f"{reply} {SCOPE_LINE}".strip()
        payload["reply"] = reply
    coworker = build_coworker(reply, service_id=payload.get("service_id"), repo_finding=repo_finding)
    payload["coworker"] = coworker
    record = payload.get("record")
    if isinstance(record, list):
        payload["record"] = stamp_coworker(record, coworker, reply)
    return payload


@app.get("/health")
def health_check():
    return {"status": "ok", "layer": "mcp-server"}


@app.get("/tools/services")
def list_services_endpoint():
    return tool_list_available_services()


@app.get("/tools/fleet")
def fleet_endpoint():
    return tool_get_fleet()


@app.get("/tools/status/{service_name}")
def get_status(service_name: str):
    return tool_get_service_status(service_name)


@app.get("/tools/logs")
def query_logs_endpoint(service: str | None = None, level: str | None = None):
    return tool_query_logs(service_name=service, level=level)


@app.get("/tools/metrics")
def query_metrics_endpoint(service: str | None = None):
    return tool_query_metrics(service_name=service)


@app.get("/tools/deployments")
def get_deployments_endpoint(service: str | None = None):
    return tool_get_deployment_details(service_name=service)


@app.post("/tools/rollback")
def rollback_endpoint(req: RollbackRequest):
    return tool_execute_rollback(req.service_name, req.target_version)


@app.post("/tools/remediate")
def remediate_endpoint(req: RemediateRequest):
    return tool_remediate(req.service_id, req.action, req.target, req.reason)


@app.post("/tools/chaos/next")
def chaos_endpoint():
    return tool_trigger_chaos()


@app.get("/tools/verify/{service_name}")
def verify_endpoint(service_name: str):
    return tool_verify_recovery(service_name)


@app.get("/agent/fleet")
def agent_fleet():
    return agent.get_fleet_status()


@app.post("/agent/analyze")
def agent_analyze(req: AnalyzeRequest):
    service_id = (req.service_id or "").strip()
    repo = (req.repo or "").strip()
    if bool(service_id) == bool(repo):
        raise HTTPException(status_code=400, detail="Send a service_id or a repo, not both.")
    if repo:
        try:
            return investigate_repository(repo, ask=(req.ask or "").strip())
        except RepoReadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return agent.analyze_incident(service_id)


@app.post("/agent/repo/approve")
def agent_repo_approve(req: RepoDecisionRequest):
    try:
        return approve_repository(req.repo.strip())
    except RepoDecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/agent/repo/reject")
def agent_repo_reject(req: RepoDecisionRequest):
    try:
        return reject_repository(req.repo.strip())
    except RepoDecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/agent/remediate")
def agent_remediate(req: RemediateRequest):
    return agent.execute_remediation(req.service_id, req.action, req.target, req.reason)


@app.post("/agent/reject")
def agent_reject(req: RejectRequest):
    return agent.reject_proposal(req.service_id, req.reason)


@app.post("/agent/chaos")
def agent_chaos():
    return agent.trigger_chaos()


@app.post("/agent/declare")
def agent_declare(req: DeclareRequest):
    return tool_declare_incident(req.service_id, req.model_dump())


@app.post("/agent/reset")
def agent_reset():
    return tool_reset_fleet()


@app.get("/agent/aws")
def agent_aws():
    return aws_status()


@app.post("/agent/silence")
def agent_silence(req: SilenceRequest):
    return silence_service(req.service_id, req.until)


@app.post("/agent/record")
def agent_record(req: RecordRequest):
    channel = req.channel if req.channel in {"voice", "text", "action"} else "text"
    role = req.role if req.role in {"user", "agent"} else "user"
    return {"record": append_record(req.service_id, channel, role, req.text)}


@app.post("/agent/discuss")
def agent_discuss(req: DiscussRequest):
    channel = req.channel if req.channel in {"voice", "text"} else "text"
    asked = " ".join((req.text or "").split())[:600]
    repo = (req.repo or "").strip()
    if repo:
        try:
            result = discuss_repository(repo, asked, channel=channel)
        except RepoDecisionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _pack_discuss({
            "reply": result["reply"],
            "record": result["finding"].get("record"),
            "service_id": result.get("record_id"),
            "repo": result.get("repo"),
            "scope": "repo",
            "source": "repository",
        }, repo_finding=result.get("finding"))
    from agent.dialogue import answer as dialogue_answer

    spoken = dialogue_answer(req.service_id, asked)
    if spoken:
        append_record(req.service_id, channel, "user", asked or "Talk about this service.")
        record = append_record(req.service_id, channel, "agent", spoken)
        return _pack_discuss({
            "reply": spoken,
            "record": record,
            "service_id": req.service_id,
            "scope": "service",
            "source": "dialogue",
        })
    route = route_question(req.service_id, req.text or "")
    if route["kind"] == "chat":
        from agent.conversation import reply as chat_reply

        reply = chat_reply(route["asked"], req.service_id)
        append_record(req.service_id, channel, "user", route["asked"])
        record = append_record(req.service_id, channel, "agent", reply)
        return _pack_discuss({
            "reply": reply,
            "record": record,
            "service_id": req.service_id,
            "scope": "service",
            "source": "conversation",
        })
    if route["kind"] == "project":
        from agent.project_knowledge import answer_project

        reply = answer_project(route["asked"])
        append_record(req.service_id, channel, "user", route["asked"])
        record = append_record(req.service_id, channel, "agent", reply)
        return _pack_discuss({
            "reply": reply,
            "record": record,
            "service_id": req.service_id,
            "scope": "service",
            "source": "project",
        })
    if route["kind"] == "decision":
        from simulator.main import explain_decision

        reply = explain_decision(route["service_id"], route["asked"])
        append_record(route["service_id"], channel, "user", route["asked"])
        record = append_record(route["service_id"], channel, "agent", reply)
        return _pack_discuss({
            "reply": reply,
            "record": record,
            "service_id": route["service_id"],
            "scope": "service",
            "source": "conversation",
        })
    if route["kind"] != "service":
        return _pack_discuss(discuss(req.service_id, req.text, channel))
    result = agent.analyze_incident(route["service_id"])
    reply = agent.finding_reply(result, detail=route.get("detail", False))
    if route.get("moved"):
        reply = f"That question is about {route['service_id']}, so I moved it to Entire fleet. " + reply
    append_record(route["service_id"], channel, "user", route["asked"])
    record = append_record(route["service_id"], channel, "agent", reply)
    return _pack_discuss({
        "reply": reply,
        "record": record,
        "service_id": route["service_id"],
        "scope": "all" if route.get("moved") else "service",
        "source": (result.get("analysis") or {}).get("source"),
    })


@app.post("/alexa")
async def alexa_endpoint(request: Request):
    raw = await request.body()
    client = request.client.host if request.client else ""
    if not request_allowed(request.headers, raw, client):
        return {
            "version": "1.0",
            "sessionAttributes": {},
            "response": {
                "outputSpeech": {"type": "PlainText", "text": "This request is not from Alexa."},
                "shouldEndSession": True,
            },
        }
    return handle_alexa(json.loads(raw), agent)


@app.post("/agent/speak")
def agent_speak(req: SpeakRequest):
    audio = synthesize_speech(req.text)
    return Response(content=audio, media_type="audio/wav")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
