# OpsPilot

OpsPilot is a voice-first incident commander for engineering teams. You give it one service. It investigates the live telemetry, keeps the context, and waits for you to approve or reject a recovery action.

The board and Alexa use the same agent. Alexa does not have a second brain.

## Run the board

From the repo root:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn mcp_server.server:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd web_ui
npm install
npm run dev -- --port 3000
```

Open http://localhost:3000.

The header button **Reset scene** restores the opening three incidents: payment-service, vault-secrets-manager, and ingress-nginx-controller. It does not delete the command record.

## Spoken commands

Say these to Alexa, or use the same actions on the board.

1. **What's wrong with payments?** OpsPilot resolves payments to payment-service and investigates it.
2. **approve** runs the suggested fix. For the opening payment incident that is rollback to v2.0.9, which marks the service healthy at error rate 0. Approve does nothing until a service has just been investigated.
3. **reject** leaves that service open as triage. It does not mark it healthy.

On the board, Talk about this speaks the open incident. Approve, Reject, and Override are the same decision.

## Source badge

The finding names its source. **Bedrock** means Claude reasoned over the telemetry. **Scenario fallback** means Bedrock was unavailable and the answer came from the scenario on that service. The badge stays visible either way.

## Alexa+

The skill package is in `alexa/skill-package/`. Import it in the Alexa developer console. The endpoint must be a public HTTPS URL ending in `/alexa`. Amazon cannot call `127.0.0.1`.

With the agent already running, open a tunnel with cloudflared or ngrok:

```bash
sh scripts/alexa_tunnel.sh
```

Paste the printed `https://…` host, plus `/alexa`, into the skill endpoint. Set `ALEXA_SKILL_ID` to the skill id from the console before starting the agent if you want the endpoint to accept only that skill.

The skill calls only these existing routes, through `POST /alexa`:

- `POST /agent/analyze`
- `POST /agent/remediate`
- `POST /agent/reject`

## License

OpsPilot is released under the MIT license. Copyright 2026 sachidur007. See [LICENSE](LICENSE).
