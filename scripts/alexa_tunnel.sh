#!/bin/sh
# Expose the existing agent so Alexa can call POST /alexa.
# Amazon cannot reach 127.0.0.1. Paste the printed https host, plus /alexa,
# into the Alexa console endpoint.
set -e
if command -v cloudflared >/dev/null 2>&1; then
  exec cloudflared tunnel --url http://127.0.0.1:8000
fi
if command -v ngrok >/dev/null 2>&1; then
  exec ngrok http 127.0.0.1:8000
fi
echo "Install cloudflared or ngrok, then run this again." >&2
exit 1
