#!/bin/sh
# Local only. The hosted skill endpoint is
# https://yn6f6qpstp.us-east-1.awsapprunner.com/alexa
# Use this script when the agent is running on this machine and Amazon
# cannot call 127.0.0.1. Paste the printed https host, plus /alexa.
set -e
if command -v cloudflared >/dev/null 2>&1; then
  exec cloudflared tunnel --url http://127.0.0.1:8000
fi
if command -v ngrok >/dev/null 2>&1; then
  exec ngrok http 127.0.0.1:8000
fi
echo "Install cloudflared or ngrok, then run this again." >&2
exit 1
