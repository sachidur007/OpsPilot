import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import simulator.main as sim
from agent.aws_panel import interpret_log_groups
from agent.coworker_reply import SCOPE_LINE, build_coworker
from agent.outbound import create_jira_issue, post_slack
from agent.opspilot_agent import OpsPilotAgent
from mcp_server.protocol import get_alert, get_timeline, list_incidents
from mcp_server.tools.ops_tools import tool_get_alert, tool_get_timeline, tool_list_incidents


@contextmanager
def isolated_fleet():
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    saved = (sim.DATA_DIR, sim.STATE_FILE, sim.RECORD_FILE, sim.METRICS_FILE, sim.LOGS_FILE, sim.DEPLOYMENTS_FILE)
    sim.DATA_DIR = root
    sim.STATE_FILE = root / "fleet_state.json"
    sim.RECORD_FILE = root / "command_record.json"
    sim.METRICS_FILE = root / "metrics.json"
    sim.LOGS_FILE = root / "logs.json"
    sim.DEPLOYMENTS_FILE = root / "deployments.json"
    try:
        yield
    finally:
        sim.DATA_DIR, sim.STATE_FILE, sim.RECORD_FILE, sim.METRICS_FILE, sim.LOGS_FILE, sim.DEPLOYMENTS_FILE = saved
        tmp.cleanup()


class McpIncidentToolsTests(unittest.TestCase):
    def test_tools_are_registered_for_initialize(self):
        self.assertTrue(callable(list_incidents))
        self.assertTrue(callable(get_timeline))
        self.assertTrue(callable(get_alert))

    def test_incident_payloads(self):
        with isolated_fleet():
            sim.reset_fleet()
            incidents = tool_list_incidents()["incidents"]
            names = {item["service_id"] for item in incidents}
            self.assertEqual(names, {"payment-service", "vault-secrets-manager", "ingress-nginx-controller"})
            alert = tool_get_alert("payment-service")["alert"]
            self.assertEqual(alert["service"], "payment-service")
            self.assertEqual(alert["severity"], "SEV-1")
            self.assertGreaterEqual(alert["error_rate"], 0.20)
            self.assertEqual(alert["suggested_action"], "rollback")
            self.assertTrue(alert["target"])
            healthy = tool_get_alert("auth-service")
            self.assertIsNone(healthy["alert"])
            self.assertEqual(healthy["forecast"], "approaching SEV-2")
            flat = tool_get_alert("recommendation-engine")
            self.assertIsNone(flat["forecast"])
            timeline = tool_get_timeline("")["timeline"]
            self.assertTrue(any(item["kind"] == "scene" for item in timeline))
            scoped = tool_get_timeline("payment-service")["timeline"]
            self.assertTrue(all(item["service_id"] == "payment-service" for item in scoped))
            for item in incidents:
                self.assertFalse(item.get("jira_key"))


class SilenceAndSlopeTests(unittest.TestCase):
    def test_operator_can_declare_a_healthy_service(self):
        with isolated_fleet():
            sim.reset_fleet()
            empty = sim.declare_incident("notification-service", {"title": "  "})
            self.assertEqual(empty["status"], "NEEDS_FIELDS")
            declared = sim.declare_incident("notification-service", {
                "title": "Checkout retries failing",
                "severity": "SEV-1",
                "details": "Checkout retries are failing after the deploy.",
                "notes": "Started after the 14:00 release.",
                "links": ["https://example.com/runbook", "not-a-link"],
                "attributes": [
                    {"name": "Region", "value": "us-east-1"},
                    {"name": "", "value": "ignored"},
                ],
            })
            self.assertEqual(declared["status"], "DECLARED")
            self.assertEqual(declared["service"]["service_id"], "notification-service")
            self.assertEqual(declared["service"]["severity"], "SEV-1")
            record = declared["service"]["declaration"]
            self.assertEqual(record["title"], "Checkout retries failing")
            self.assertEqual(record["details"], "Checkout retries are failing after the deploy.")
            self.assertEqual(record["notes"], "Started after the 14:00 release.")
            self.assertEqual(record["links"], ["https://example.com/runbook"])
            self.assertEqual(record["attributes"], [{"name": "Region", "value": "us-east-1"}])
            self.assertNotEqual(declared["service"]["status"], "HEALTHY")
            self.assertEqual(declared["service"]["proposal_source"], "declared")
            state = json.loads(sim.STATE_FILE.read_text())
            self.assertTrue(any("Checkout retries failing" in item["message"] for item in state["timeline"]))
            again = sim.declare_incident("notification-service")
            self.assertEqual(again["status"], "ALREADY_OPEN")
            missing = sim.declare_incident("not-a-service")
            self.assertEqual(missing["status"], "MISSING")

    def test_approve_reject_and_override_keep_the_reason(self):
        with isolated_fleet():
            sim.reset_fleet()
            bare = sim.reject_incident("payment-service", "  ")
            self.assertEqual(bare["status"], "NEEDS_REASON")
            rejected = sim.reject_incident("payment-service", "The suggested rollback is the release that failed.")
            self.assertEqual(rejected["status"], "TRIAGE")
            self.assertEqual(rejected["service"]["decision"]["reason"], "The suggested rollback is the release that failed.")
            empty = sim.remediate("vault-secrets-manager", "unseal", "v1.12-unseal", "")
            self.assertEqual(empty["status"], "NEEDS_REASON")
            approved = sim.remediate(
                "vault-secrets-manager",
                "unseal",
                "v1.12-unseal",
                "The seal is confirmed and unseal is the right fix.",
            )
            self.assertEqual(approved["status"], "SUCCESS")
            self.assertEqual(approved["service"]["status"], "HEALTHY")
            overrode = sim.remediate(
                "ingress-nginx-controller",
                "rollback",
                "v1.7.8",
                "Cert rotation is the wrong tool for this controller.",
            )
            self.assertEqual(overrode["status"], "SUCCESS")
            state = json.loads(sim.STATE_FILE.read_text())
            messages = [item["message"] for item in state["timeline"]]
            self.assertTrue(any("The suggested rollback is the release that failed." in item for item in messages))
            self.assertTrue(any("Operator approved unseal -> v1.12-unseal" in item for item in messages))
            self.assertTrue(any("Operator overrode rollback -> v1.7.8" in item for item in messages))

    def test_chaos_skips_a_silenced_service(self):
        with isolated_fleet():
            sim.reset_fleet()
            until = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            silenced = sim.silence_service("inventory-service", until)
            self.assertEqual(silenced["status"], "SILENCED")
            with mock.patch("agent.outbound.requests.post") as post:
                opened = sim.trigger_chaos()
                post.assert_not_called()
            self.assertEqual(opened["status"], "TRIGGERED")
            self.assertEqual(opened["service"]["service_id"], "auth-service")
            state = json.loads(sim.STATE_FILE.read_text())
            self.assertIn("inventory-service", state["chaos_queue"])

    def test_one_service_crosses_and_the_label_stays_plain(self):
        with isolated_fleet():
            sim.reset_fleet()
            state = json.loads(sim.STATE_FILE.read_text())
            state["services"]["auth-service"]["error_history"] = [0.03, 0.046]
            state["slope_advanced_at"] = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
            sim.STATE_FILE.write_text(json.dumps(state))
            fleet = sim.get_fleet()
            opened = {item["service_id"] for item in fleet["active_incidents"]}
            self.assertIn("auth-service", opened)
            self.assertEqual(len(opened), 4)
            auth = next(item for item in fleet["active_incidents"] if item["service_id"] == "auth-service")
            self.assertIsNone(auth["forecast"])
            still = next(item for item in fleet["healthy_fleet"] if item["service_id"] == "notification-service")
            self.assertEqual(still["forecast"], "approaching SEV-2")
            self.assertNotIn("machine learning", json.dumps(fleet).lower())


class CoworkerAndBudgetTests(unittest.TestCase):
    def test_coworker_names_the_fleet_record(self):
        with isolated_fleet():
            sim.reset_fleet()
            parts = build_coworker("What is wrong?", "payment-service")
            self.assertIn("payment-service", parts["situation"])
            self.assertIn("Source:", parts["insight"])
            self.assertIn("project_knowledge.py", parts["knowledge"])
            self.assertEqual(parts["scope"], SCOPE_LINE)
            self.assertIn("fleet record", parts["scope"])
            self.assertIn("repository you handed over", parts["scope"])
            self.assertEqual(parts["token_budget"]["cap"], 40)
            self.assertEqual(parts["token_budget"]["remaining"], 40)

    def test_refused_bedrock_still_counts_and_stays_fallback(self):
        with isolated_fleet():
            sim.reset_fleet()
            agent = OpsPilotAgent()

            def refused(self, service_id, telemetry):
                raise RuntimeError(
                    "An error occurred (ValidationException) when calling the InvokeModel operation: "
                    "Error 002: Access to Bedrock models is not allowed for this account"
                )

            agent._bedrock_analysis = refused.__get__(agent, OpsPilotAgent)
            result = agent.analyze_incident("payment-service")
            analysis = result["analysis"]
            self.assertEqual(analysis["source"], "scenario-fallback")
            self.assertIn("002", analysis["fallback_reason"])
            budget = sim.budget_view()
            self.assertEqual(budget["calls"], 1)
            self.assertEqual(budget["remaining"], 39)
            last = sim.bedrock_view()["last_bedrock"]
            self.assertEqual(last["source"], "scenario-fallback")
            self.assertIn("002", last["fallback_reason"])


class OutboundGateTests(unittest.TestCase):
    def test_slack_and_jira_stay_idle_without_credentials(self):
        cleared = {
            "SLACK_WEBHOOK_URL": "",
            "JIRA_BASE_URL": "",
            "JIRA_EMAIL": "",
            "JIRA_API_TOKEN": "",
            "JIRA_PROJECT_KEY": "",
        }
        with mock.patch.dict(os.environ, cleared, clear=False):
            with mock.patch("agent.outbound.requests.post") as post:
                self.assertFalse(post_slack("payment-service", "SEV-1", "rollback", "operator"))
                self.assertIsNone(create_jira_issue("payment-service", "SEV-1", "rollback"))
                post.assert_not_called()

    def test_describe_log_groups_reports_the_group_or_the_error(self):
        found = interpret_log_groups("/opspilot/traces", {"logGroups": [{"logGroupName": "/opspilot/traces"}]}, None)
        self.assertTrue(found["exists"])
        self.assertIsNone(found["error"])
        missing = interpret_log_groups("/opspilot/traces", {"logGroups": []}, None)
        self.assertFalse(missing["exists"])
        denied = interpret_log_groups("/opspilot/traces", None, "AccessDenied")
        self.assertFalse(denied["exists"])
        self.assertEqual(denied["error"], "AccessDenied")


if __name__ == "__main__":
    unittest.main()
