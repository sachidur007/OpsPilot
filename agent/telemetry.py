"""Export request spans to CloudWatch Logs. A bad AWS token drops the span."""

from __future__ import annotations

import json
import os
import time

import boto3
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

GROUP = os.getenv("OPSPILOT_LOG_GROUP", "/opspilot/traces")
STREAM = os.getenv("OPSPILOT_LOG_STREAM", "agent")
REGION = os.getenv("AWS_REGION", "us-east-1")


class CloudWatchSpanExporter(SpanExporter):
    def __init__(self) -> None:
        self._client = None
        self._ready = False

    def _logs(self):
        if self._client is None:
            self._client = boto3.client("logs", region_name=REGION)
        return self._client

    def _ensure(self) -> None:
        if self._ready:
            return
        client = self._logs()
        try:
            client.create_log_group(logGroupName=GROUP)
        except client.exceptions.ResourceAlreadyExistsException:
            pass
        try:
            client.create_log_stream(logGroupName=GROUP, logStreamName=STREAM)
        except client.exceptions.ResourceAlreadyExistsException:
            pass
        self._ready = True

    def export(self, spans: list[ReadableSpan]) -> SpanExportResult:
        if os.getenv("OPSPILOT_TRACES", "1") == "0" or not spans:
            return SpanExportResult.SUCCESS
        try:
            self._ensure()
            events = []
            for span in spans:
                events.append({
                    "timestamp": int((span.start_time or time.time_ns()) / 1_000_000),
                    "message": json.dumps({
                        "name": span.name,
                        "trace_id": format(span.context.trace_id, "032x") if span.context else "",
                        "status": span.status.status_code.name if span.status else "",
                        "attributes": {key: str(value) for key, value in (span.attributes or {}).items()},
                    }),
                })
            events.sort(key=lambda item: item["timestamp"])
            self._logs().put_log_events(logGroupName=GROUP, logStreamName=STREAM, logEvents=events)
        except Exception:
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


_provider = TracerProvider()
_provider.add_span_processor(BatchSpanProcessor(CloudWatchSpanExporter()))
trace.set_tracer_provider(_provider)
tracer = trace.get_tracer("opspilot")
