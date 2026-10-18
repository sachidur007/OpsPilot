import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from agent.alexa_skill import handle_alexa, request_allowed
from agent.telemetry import tracer
from agent.voice import synthesize_speech

from agent.opspilot_agent import OpsPilotAgent
from mcp_server.protocol import ops_mcp
from simulator.main import append_record, discuss, route_question
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
    tool_trigger_chaos,
    tool_verify_recovery,
)

agent = OpsPilotAgent()
protocol_app = ops_mcp.streamable_http_app(streamable_http_path="/", stateless_http=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with ops_mcp.session_manager.run():
        yield


app = FastAPI(title="OpsPilot MCP Server", lifespan=lifespan)

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


class ServiceRequest(BaseModel):
    service_id: str


class SpeakRequest(BaseModel):
    text: str


class RecordRequest(BaseModel):
    service_id: str | None = None
    channel: str
    role: str
    text: str


class DiscussRequest(BaseModel):
    service_id: str | None = None
    channel: str = "text"
    text: str


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
    return tool_remediate(req.service_id, req.action, req.target)


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
def agent_analyze(req: ServiceRequest):
    return agent.analyze_incident(req.service_id)


@app.post("/agent/remediate")
def agent_remediate(req: RemediateRequest):
    return agent.execute_remediation(req.service_id, req.action, req.target)


@app.post("/agent/reject")
def agent_reject(req: ServiceRequest):
    return agent.reject_proposal(req.service_id)


@app.post("/agent/chaos")
def agent_chaos():
    return agent.trigger_chaos()


@app.post("/agent/reset")
def agent_reset():
    return tool_reset_fleet()


@app.post("/agent/record")
def agent_record(req: RecordRequest):
    channel = req.channel if req.channel in {"voice", "text", "action"} else "text"
    role = req.role if req.role in {"user", "agent"} else "user"
    return {"record": append_record(req.service_id, channel, role, req.text)}


@app.post("/agent/discuss")
def agent_discuss(req: DiscussRequest):
    channel = req.channel if req.channel in {"voice", "text"} else "text"
    asked = " ".join((req.text or "").split())[:600]
    from agent.dialogue import answer as dialogue_answer

    spoken = dialogue_answer(req.service_id, asked)
    if spoken:
        append_record(req.service_id, channel, "user", asked or "Talk about this service.")
        record = append_record(req.service_id, channel, "agent", spoken)
        return {
            "reply": spoken,
            "record": record,
            "service_id": req.service_id,
            "scope": "service",
            "source": "dialogue",
        }
    route = route_question(req.service_id, req.text or "")
    if route["kind"] == "chat":
        from agent.conversation import reply as chat_reply

        reply = chat_reply(route["asked"], req.service_id)
        append_record(req.service_id, channel, "user", route["asked"])
        record = append_record(req.service_id, channel, "agent", reply)
        return {
            "reply": reply,
            "record": record,
            "service_id": req.service_id,
            "scope": "service",
            "source": "conversation",
        }
    if route["kind"] == "project":
        from agent.project_knowledge import answer_project

        reply = answer_project(route["asked"])
        append_record(req.service_id, channel, "user", route["asked"])
        record = append_record(req.service_id, channel, "agent", reply)
        return {
            "reply": reply,
            "record": record,
            "service_id": req.service_id,
            "scope": "service",
            "source": "project",
        }
    if route["kind"] == "decision":
        from simulator.main import explain_decision

        reply = explain_decision(route["service_id"], route["asked"])
        append_record(route["service_id"], channel, "user", route["asked"])
        record = append_record(route["service_id"], channel, "agent", reply)
        return {
            "reply": reply,
            "record": record,
            "service_id": route["service_id"],
            "scope": "service",
            "source": "conversation",
        }
    if route["kind"] != "service":
        return discuss(req.service_id, req.text, channel)
    result = agent.analyze_incident(route["service_id"])
    reply = agent.finding_reply(result, detail=route.get("detail", False))
    if route.get("moved"):
        reply = f"That question is about {route['service_id']}, so I moved it to Entire fleet. " + reply
    append_record(route["service_id"], channel, "user", route["asked"])
    record = append_record(route["service_id"], channel, "agent", reply)
    return {
        "reply": reply,
        "record": record,
        "service_id": route["service_id"],
        "scope": "all" if route.get("moved") else "service",
        "source": (result.get("analysis") or {}).get("source"),
    }


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
