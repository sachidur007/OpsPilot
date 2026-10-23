# Fleet Commander

FleetOps is a voice-first incident commander for engineering teams. You give it one service. It reads that service from the fleet record, keeps the context, and waits for you to approve or reject a recovery action.

The fleet in this demo is a scenario simulator, not a customer's live metrics, logs, or traces. The board says that on every reply.

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

Open http://localhost:3000. The page title is Fleet Commander. The name on the board is FleetOps.

The header button **Reset scene** restores the opening three incidents: payment-service, vault-secrets-manager, and ingress-nginx-controller. It does not delete the command record.

## Spoken commands

Say these to Alexa, or use the same actions on the board.

1. **What's wrong with payments?** FleetOps resolves payments to payment-service and investigates it.
2. **approve** runs the suggested fix, once you have said why. For the opening payment incident that is rollback to v2.0.9, which marks the service healthy at error rate 0. Approve does nothing until a service has just been investigated and the Why field is filled in.
3. **reject** leaves that service open as triage and keeps the reason. It does not mark it healthy.

On the board, Talk about this speaks the open incident. Approve, Reject, and Override are the same decision. Override picks a different action and target, and nothing runs until Execute. A bare "approve" or "reject" is not enough. The words after that are the reason.

Declare incident is on a healthy service. You file a title, a security level, and what happened. SEV-1 is an error rate at or above 20%, or a critical failure. SEV-2 is at or above 5%. Anything else open is SEV-3.

## Source badge

The finding names its source. **Bedrock** means Claude reasoned over the fleet record. **Scenario fallback** means Bedrock was unavailable and the answer came from the scenario on that service. The badge stays visible either way.

This account returns Bedrock Error 002, access to Bedrock models is not allowed. That is an account restriction, not a missing IAM action. `bedrock:InvokeModel` is already allowed. The agent still calls InvokeModel. When that call is refused, the badge stays Scenario fallback. The account holder clears this with the Anthropic first-use form in the Bedrock console in us-east-1. If that form does not clear it, the next step is AWS Support.

Set `BEDROCK_MODEL_ID` in `.env` to a Claude model the account can call. The file stays off git. Use an IAM user, not the root account.

The agent is hosted on App Runner at https://yn6f6qpstp.us-east-1.awsapprunner.com. That URL is an earlier image. Run the board locally to see FleetOps, declare, and the Why field. Request spans from the hosted service are in the CloudWatch log group `/opspilot/traces`. That is the group already created in the account, and `DescribeLogGroups` can see it.

Slack and Jira send a notice only when real credentials are in `.env`. They are not, so those paths return without sending. The board does not invent a message or a ticket.

## Alexa+

The skill package is in `alexa/skill-package/`. Import it in the Alexa developer console. The endpoint must be a public HTTPS URL ending in `/alexa`. Amazon cannot call `127.0.0.1`.

Alexa+ partner tools were closed to this hackathon, so there is no live Alexa demo. The skill package is here, and it calls this same agent.

With the agent already running, open a tunnel with cloudflared or ngrok:

```bash
sh scripts/alexa_tunnel.sh
```

Paste the printed `https://…` host, plus `/alexa`, into the skill endpoint. Set `ALEXA_SKILL_ID` to the skill id from the console before starting the agent if you want the endpoint to accept only that skill.

The board is the Alexa+ client. On investigate it calls `POST /protocol/` with `initialize`, `tools/list`, and `tools/call` for `get_service_status`. That MCP server speaks protocol `2025-11-25`. The public tool list is read-only: `get_fleet`, `get_service_status`, `verify_recovery`, `list_incidents`, `get_timeline`, and `get_alert`. Approve and reject stay on the agent routes. The same handshake is published on its own at https://github.com/sachidur007/mcp-incident-client.

The skill calls only these existing routes, through `POST /alexa`:

- `POST /agent/analyze`
- `POST /agent/remediate`
- `POST /agent/reject`
- `POST /agent/discuss` for “tell me …”

## License

FleetOps is released under the MIT license. Copyright 2026 sachidur007. See [LICENSE](LICENSE).

The code was written with Cursor as the coding assistant. The product decisions are ours.
