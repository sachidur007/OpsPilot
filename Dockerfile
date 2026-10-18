FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent agent
COPY mcp_server mcp_server
COPY simulator simulator

ENV PYTHONUNBUFFERED=1
ENV OPSPILOT_TRACES=1
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "mcp_server.server:app", "--host", "0.0.0.0", "--port", "8000"]
