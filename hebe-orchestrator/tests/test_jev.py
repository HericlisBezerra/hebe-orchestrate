"""Tests for the explicit TypeSafe/Jev connector; no real network or account use."""

import importlib.util
import http.client
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.parse import urlsplit


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "jev.py"
SPEC = importlib.util.spec_from_file_location("hebe_jev", SCRIPT)
jev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jev)


class JevTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.request = self.root / "request.json"
        self.payload = {
            "state": {"objective": "Synthetic test"},
            "questions": {
                "route": {
                    "type": "choice",
                    "instructions": "Choose a route.",
                    "criteria": {"local": "Use code.", "review": "Escalate."},
                },
                "safe": {"type": "noul", "instructions": "Is this synthetic?"},
            },
        }
        self.request.write_text(json.dumps(self.payload), encoding="utf-8")

    def cli(self, *args, env=None):
        clean = dict(os.environ)
        clean.pop("TYPESAFE_API_KEY", None)
        if env:
            clean.update(env)
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                              text=True, timeout=20, env=clean)

    def test_preview_is_offline_and_does_not_require_credentials(self):
        result = self.cli("preview", "--file", str(self.request))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["valid"])
        self.assertFalse(output["network_used"])
        self.assertFalse(output["credential_used"])
        self.assertEqual(output["model"], "jev-latest")
        self.assertEqual(output["question_types"], {"noul": 1, "choice": 1, "score": 0})
        self.assertEqual(output["question_ids"], ["route", "safe"])

    def test_validation_rejects_duplicate_keys_and_invalid_questions(self):
        duplicate = self.root / "duplicate.json"
        duplicate.write_text('{"state":"a","state":"b","questions":{}}', encoding="utf-8")
        result = self.cli("preview", "--file", str(duplicate))
        self.assertEqual(result.returncode, 2)
        self.assertIn("chave duplicada", result.stderr)
        invalid = self.root / "invalid.json"
        invalid.write_text(json.dumps({"state": "x", "questions": {"q": {"type": "choice", "instructions": "x", "criteria": {}}}}), encoding="utf-8")
        result = self.cli("preview", "--file", str(invalid))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Choice exige", result.stderr)

    def test_evaluation_file_symlink_is_rejected(self):
        link = self.root / "request-link.json"
        link.symlink_to(self.request)
        result = self.cli("preview", "--file", str(link))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Não foi possível ler", result.stderr)

    def test_response_validation_preserves_typed_answers(self):
        questions = jev.evaluation_input(str(self.request), None)["questions"]
        raw = {
            "model": "jev-1.test",
            "answers": {
                "route": {"type": "choice", "choice": "local", "confidence": 0.8,
                          "probabilities": {"local": 0.9, "review": 0.1}},
                "safe": {"type": "noul", "noul": 0.99},
            },
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }
        output = jev.evaluation_output(raw, questions)
        self.assertEqual(output["answers"]["route"]["choice"], "local")
        self.assertEqual(output["answers"]["safe"]["noul"], 0.99)

    def test_credentials_are_private_and_symlinks_are_rejected(self):
        home = self.root / "home"
        home.mkdir(mode=0o700)
        with mock.patch.object(Path, "home", return_value=home):
            jev.save_credentials("synthetic-secret")
            target = home / ".config" / "hebe-brain" / "typesafe.json"
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(jev.stored_credentials(), "synthetic-secret")
            target.unlink()
            outside = self.root / "outside"
            outside.write_text("unchanged", encoding="utf-8")
            target.symlink_to(outside)
            with self.assertRaises(jev.JevError):
                jev.stored_credentials()
            self.assertEqual(outside.read_text(), "unchanged")

    def test_web_setup_requires_unpredictable_path_before_revealing_csrf(self):
        captured = io.StringIO()
        outcome = {}

        def run():
            try:
                outcome["result"] = jev.configure_web()
            except BaseException as exc:
                outcome["error"] = exc

        with mock.patch.object(jev, "SETUP_LIFETIME", 5), \
                mock.patch.object(jev, "model_list", return_value=[{"name": "synthetic"}]), \
                mock.patch.object(jev, "save_credentials") as save, \
                mock.patch.object(sys, "stdout", captured):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            deadline = time.monotonic() + 2
            while "\n" not in captured.getvalue() and time.monotonic() < deadline:
                time.sleep(0.01)
            metadata = json.loads(captured.getvalue().splitlines()[0])
            parsed = urlsplit(metadata["setup_url"])
            origin = f"http://{parsed.netloc}"

            client = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=2)
            client.request("GET", "/")
            denied = client.getresponse()
            denied.read()
            self.assertEqual(denied.status, 403)
            client.close()

            client = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=2)
            client.request("GET", parsed.path)
            page_response = client.getresponse()
            page = page_response.read().decode("utf-8")
            self.assertEqual(page_response.status, 200)
            csrf = __import__("re").search(r"X-HeBe-CSRF':'([^']+)", page).group(1)
            configure_path = __import__("re").search(r"fetch\('([^']+)'", page).group(1)
            client.close()

            body = json.dumps({"api_key": "synthetic-key"})
            client = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=2)
            client.request("POST", configure_path, body=body, headers={
                "Content-Type": "application/json", "Origin": origin, "X-HeBe-CSRF": csrf,
            })
            accepted = client.getresponse()
            accepted.read()
            self.assertEqual(accepted.status, 200)
            client.close()
            worker.join(timeout=2)

        self.assertNotIn("error", outcome)
        self.assertTrue(outcome["result"]["validated"])
        save.assert_called_once_with("synthetic-key")

    def test_invalid_api_shape_is_rejected_without_echoing_content(self):
        questions = jev.evaluation_input(str(self.request), None)["questions"]
        with self.assertRaisesRegex(jev.JevError, "incompatível"):
            jev.evaluation_output({"model": "x", "answers": {}, "usage": {}}, questions)


if __name__ == "__main__":
    unittest.main()
