import subprocess
import unittest
from pathlib import Path

from simulator.scenarios import ACTIONS
from simulator.main import STATE_FILE, get_service_record

from agent.playbooks import match_playbooks
from agent.repo_investigation import approve_repository, discuss_repository, investigate_repository, reject_repository
from agent.repo_reader import read_repository

ROOT = Path(__file__).resolve().parents[1]
VULNERABLE = ROOT / "tests" / "fixtures" / "php_vulnerable"
NODE_ONLY = ROOT / "tests" / "fixtures" / "node_only"
PHP_SRC = ROOT / "tests" / "fixtures" / "php_src"
ORG_SHOP = ROOT / "tests" / "fixtures" / "org_shop"


class RepoReaderTests(unittest.TestCase):
    def test_vulnerable_php_image_is_in_the_bill_of_materials(self):
        bom = read_repository(str(VULNERABLE))["bom"]
        php = [item for item in bom if item["ecosystem"] == "php" and item["name"] == "php"]
        self.assertEqual(php, [{
            "path": "Dockerfile",
            "ecosystem": "php",
            "name": "php",
            "version": "8.2.0",
        }])

    def test_node_repo_has_no_php(self):
        bom = read_repository(str(NODE_ONLY))["bom"]
        self.assertTrue(any(item["name"] == "left-pad" for item in bom))
        self.assertFalse(any(item["ecosystem"] == "php" for item in bom))

    def test_git_url_clone_reads_manifests(self):
        import tempfile

        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            origin = Path(tmp) / "origin"
            origin.mkdir()
            (origin / "package.json").write_text('{"dependencies":{"left-pad":"1.0.0"}}\n', encoding="utf-8")
            _git(["init"], origin)
            _git(["add", "package.json"], origin)
            _git(["-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "init"], origin)
            bom = read_repository(origin.as_uri())["bom"]
        self.assertTrue(any(item["name"] == "left-pad" for item in bom))


class PlaybookTests(unittest.TestCase):
    def test_php_below_the_patched_release_is_verified(self):
        finding = match_playbooks(read_repository(str(VULNERABLE))["bom"])
        self.assertEqual(finding["status"], "verified")
        self.assertEqual(finding["source"], "playbook")
        self.assertEqual(finding["provision"], "upgrade_runtime")
        self.assertEqual(finding["target"], "8.4.15")
        self.assertEqual(finding["advisories"], ["CVE-2026-109618", "CVE-2026-109619"])
        self.assertTrue(finding["approve_enabled"])

    def test_repo_with_no_php_is_unverified(self):
        finding = match_playbooks(read_repository(str(NODE_ONLY))["bom"])
        self.assertEqual(finding["status"], "unverified")
        self.assertIsNone(finding["provision"])
        self.assertFalse(finding["approve_enabled"])
        self.assertTrue(finding["bom"])

    def test_patched_php_is_unverified(self):
        finding = match_playbooks([{
            "path": "Dockerfile",
            "ecosystem": "php",
            "name": "php",
            "version": "8.4.15",
        }])
        self.assertEqual(finding["status"], "unverified")
        self.assertIn("do not apply", finding["summary"])

    def test_php_interpreter_source_is_read_from_its_version_header(self):
        bom = read_repository(str(PHP_SRC))["bom"]
        php = [item for item in bom if item["name"] == "php"]
        self.assertEqual(php, [{
            "path": "main/php_version.h",
            "ecosystem": "php",
            "name": "php",
            "version": "8.3.6",
        }])
        finding = match_playbooks(bom)
        self.assertEqual(finding["status"], "verified")
        self.assertEqual(finding["target"], "8.4.15")


class SideWorkerTests(unittest.TestCase):
    def test_handoff_reads_instructions_and_waits_for_permission(self):
        import tempfile

        readme = (ORG_SHOP / "README.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            finding = investigate_repository(
                str(ORG_SHOP),
                data_dir=data,
                record=False,
                ask="Set this service up",
            )
            work = finding["work"]
            self.assertTrue(finding["approve_enabled"])
            self.assertEqual(work["project"], "Shop")
            self.assertIn("requirements.md", work["summary"])
            self.assertIn("pip install -r requirements.txt", work["summary"])
            self.assertIn("until you approve", work["summary"])
            before = discuss_repository(
                finding["repo"],
                "install the requirements",
                data_dir=data,
                record=False,
            )
            self.assertIn("need approval", before["reply"])
            plan = discuss_repository(
                finding["repo"],
                "what would you do next",
                data_dir=data,
                record=False,
            )
            self.assertIn("have not run it", plan["reply"])
            result = approve_repository(finding["repo"], data_dir=data, record=False)
            note = Path(result["work_path"]).read_text(encoding="utf-8")
            self.assertEqual(result["status"], "CLEARED")
            self.assertIn("Permission granted", note)
            self.assertIn("does not modify the repository", note)
        self.assertEqual((ORG_SHOP / "README.md").read_text(encoding="utf-8"), readme)


class GateTests(unittest.TestCase):
    def test_approve_writes_a_note_and_leaves_the_fleet_unchanged(self):
        import tempfile

        before = STATE_FILE.read_bytes()
        dockerfile = (VULNERABLE / "Dockerfile").read_text(encoding="utf-8")
        service = get_service_record("payment-service")
        self.assertIn(service["metrics"]["recommended_action"], ACTIONS)
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            finding = investigate_repository(str(VULNERABLE), data_dir=data, record=False)
            result = approve_repository(finding["repo"], data_dir=data, record=False)
            note = Path(result["work_path"]).read_text(encoding="utf-8")
        self.assertEqual(result["status"], "CLEARED")
        self.assertIn("Permission granted", note)
        self.assertIn("does not modify the repository", note)
        self.assertEqual(STATE_FILE.read_bytes(), before)
        again = get_service_record("payment-service")
        self.assertEqual(again["metrics"]["recommended_action"], service["metrics"]["recommended_action"])
        self.assertEqual((VULNERABLE / "Dockerfile").read_text(encoding="utf-8"), dockerfile)

    def test_reject_does_not_write_a_provision(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            finding = investigate_repository(str(VULNERABLE), data_dir=data, record=False)
            result = reject_repository(finding["repo"], data_dir=data, record=False)
            self.assertEqual(result["status"], "REJECTED")
            self.assertEqual(list((data / "provisions").glob("*")), [])

    def test_any_repo_can_be_cleared_without_a_playbook(self):
        import tempfile

        package = (NODE_ONLY / "package.json").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            finding = investigate_repository(str(NODE_ONLY), data_dir=data, record=False)
            self.assertTrue(finding["approve_enabled"])
            result = approve_repository(finding["repo"], data_dir=data, record=False)
            self.assertEqual(result["status"], "CLEARED")
            self.assertTrue(Path(result["work_path"]).is_file())
        self.assertEqual((NODE_ONLY / "package.json").read_text(encoding="utf-8"), package)


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
