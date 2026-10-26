"""Testes da ponte Claude ↔ Codex (experimento for-claude+gpt).

Nenhum teste chama o Codex de verdade: HEBE_CODEX_COMPANION_CMD aponta para um
companion falso que imita as saídas JSON do plugin openai-codex, e HOME aponta para
uma pasta temporária (diário e política privados).
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "codex_bridge.py"

FAKE_COMPANION = textwrap.dedent('''
    import json, os, sys, time
    args = sys.argv[1:]
    with open(os.environ["FAKE_LOG"], "a") as f:
        f.write(json.dumps({"args": args, "secret_env": os.environ.get("SUPER_SECRET"),
                            "plugin_data": os.environ.get("CLAUDE_PLUGIN_DATA"),
                            "endpoint": os.environ.get("CODEX_COMPANION_APP_SERVER_ENDPOINT"),
                            "transcript": os.environ.get("CODEX_COMPANION_TRANSCRIPT_PATH"),
                            "codex_home": os.environ.get("CODEX_HOME")}) + "\\n")
    mode = os.environ.get("FAKE_MODE", "ok")
    running_file = os.environ["FAKE_RUNNING"]
    running = json.load(open(running_file)) if os.path.exists(running_file) else []
    cmd = args[0]
    if cmd == "adversarial-review":
        if mode == "slow":
            json.dump(running + [{"id": "job-mine", "pid": os.getpid()},
                                 {"id": "other-started-later", "pid": 1}], open(running_file, "w"))
            time.sleep(5)
        if mode == "bad":
            print("not json"); sys.exit(1)
        if mode == "fail":
            print("{}"); sys.exit(1)
        if mode == "empty":
            print("{}"); sys.exit(0)
        inner = {"verdict": "needs-attention", "summary": "dois achados",
                 "findings": [{"severity": "high", "title": "A", "body": "x" * 2000, "file": "a.js",
                               "line_start": 3, "recommendation": "corrigir"},
                              {"severity": "medium", "title": "B", "body": "y", "file": "b.js",
                               "line_start": 9, "recommendation": "ok"}]}
        print(json.dumps({"review": "Adversarial Review", "codex": {"status": 0, "stdout": json.dumps(inner)}}))
    elif cmd == "task":
        cwd = args[args.index("--cwd") + 1]
        prompt = open(args[args.index("--prompt-file") + 1]).read()
        assert "Regras desta delegação" in prompt
        open(os.path.join(cwd, "feature.txt"), "w").write("novo\\n")
        if mode == "slow":
            json.dump(running + [{"id": "job-build", "pid": os.getpid()}], open(running_file, "w"))
            time.sleep(10)
        if mode == "touchmain":
            open(os.environ["FAKE_MAIN"], "w").write("conteúdo trocado pelo Codex\\n")
        if mode == "scope":
            open(os.path.join(cwd, "package-lock.json"), "w").write("{}\\n")
            os.makedirs(os.path.join(cwd, "vault"), exist_ok=True)
            open(os.path.join(cwd, "vault", "nota.md"), "w").write("nota\\n")
            open(os.path.join(cwd, "test-run.log"), "w").write("ok\\n")
            os.rename(os.path.join(cwd, "app.txt"), os.path.join(cwd, "renamed.txt"))
        print(json.dumps({"status": 0, "threadId": "t1", "rawOutput": "Feito: feature.txt. Testes: 1 pass.",
                          "touchedFiles": ["feature.txt"]}))
    elif cmd == "setup":
        print(json.dumps({"ready": True, "auth": {"detail": "login ativo"}}))
    elif cmd == "status":
        print(json.dumps({"running": running}))
    elif cmd == "cancel":
        print(json.dumps({"jobId": args[1], "status": "cancelled",
                          "turnInterrupted": os.environ.get("FAKE_INTERRUPT", "1") == "1"}))
    else:
        print("{}")
''')


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir(mode=0o755)
        fake = self.root / "fake_companion.py"
        fake.write_text(FAKE_COMPANION)
        self.calls = self.root / "calls.jsonl"
        self.running = self.root / "running.json"
        self.env = dict(os.environ, HOME=str(self.home),
                        HEBE_CODEX_COMPANION_CMD=f"{sys.executable} {fake}",
                        HEBE_CODEX_WORKTREES=str(self.root / "worktrees"),
                        HEBE_CODEX_ENV_PASSTHROUGH="FAKE_",
                        FAKE_LOG=str(self.calls), FAKE_RUNNING=str(self.running),
                        SUPER_SECRET="nao-deve-chegar", PYTHONDONTWRITEBYTECODE="1",
                        HEBE_CODEX_STATE=str(Path(tempfile.gettempdir()).resolve() / f"hebe-state-{os.getpid()}-{id(self)}"),
                        CODEX_COMPANION_TRANSCRIPT_PATH="/caminho/da/transcricao",
                        CODEX_COMPANION_APP_SERVER_ENDPOINT="unix:/broker/com/ambiente/completo",
                        HEBE_CODEX_HOME=str(self.root / "codex-home"), HEBE_CODEX_LOGIN_CMD="true")
        self.repo = self.root / "repo"
        self.repo.mkdir()
        for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
            git(self.repo, *args)
        (self.repo / "app.txt").write_text("base\n")
        (self.repo / "node_modules").mkdir()
        (self.repo / "node_modules" / "dep.js").write_text("module\n")
        (self.repo / ".env").mkdir()
        (self.repo / ".gitignore").write_text("node_modules/\n.env/\nlinked/\nplain/\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "base")

    def tearDown(self):
        self.tmp.cleanup()

    def run_bridge(self, *args, mode="ok", expect=0):
        env = dict(self.env, FAKE_MODE=mode)
        done = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, expect, done.stdout + done.stderr)
        return json.loads(done.stdout)

    def calls_list(self):
        if not self.calls.exists():
            return []
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def codex_calls(self, kind):
        return [c["args"] for c in self.calls_list() if c["args"][0] == kind]

    def ledger(self):
        path = self.home / ".config" / "hebe-brain" / "codex-experiment.jsonl"
        self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")
        return [json.loads(line) for line in path.read_text().splitlines()]

    def brief(self, text="Implemente feature.txt.\n"):
        path = self.root / "brief.md"
        path.write_text(text)
        return str(path)

    # ------------------------------------------------------------ review

    def test_review_working_tree_by_default(self):
        (self.repo / "app.txt").write_text("mudado\n")
        out = self.run_bridge("review", "--cwd", str(self.repo), "--focus", "segurança")
        self.assertEqual((out["verdict"], out["scope"]), ("needs-attention", "working-tree"))
        self.assertLessEqual(len(out["findings"][0]["body"]), 900)
        call = self.codex_calls("adversarial-review")[0]
        self.assertIn("working-tree", call)
        self.assertNotIn("--base", call)
        self.assertEqual(call[-2:], ["--", "segurança"])
        entry = self.ledger()[0]
        self.assertEqual((entry["kind"], entry["model"], entry["ok"]), ("review", "gpt-6.1-sol", True))
        self.assertEqual(entry["findings"], {"high": 1, "medium": 1})
        self.assertNotIn("segurança", json.dumps(entry, ensure_ascii=False))

    def test_review_base_requires_clean_tree(self):
        out = self.run_bridge("review", "--cwd", str(self.repo), "--base", "HEAD")
        self.assertEqual(out["scope"], "branch")
        (self.repo / "app.txt").write_text("mudado\n")
        out = self.run_bridge("review", "--cwd", str(self.repo), "--base", "HEAD", expect=2)
        self.assertIn("não commitadas", out["error"])

    def test_review_clean_tree_without_base_refuses(self):
        out = self.run_bridge("review", "--cwd", str(self.repo), expect=2)
        self.assertIn("não há o que revisar", out["error"])

    def test_focus_starting_with_dash_stays_positional(self):
        (self.repo / "app.txt").write_text("mudado\n")
        self.run_bridge("review", "--cwd", str(self.repo), "--focus=--background")
        call = self.codex_calls("adversarial-review")[0]
        self.assertEqual(call[-2:], ["--", "--background"])

    def test_companion_failures_are_not_recorded_as_reviews(self):
        (self.repo / "app.txt").write_text("mudado\n")
        for mode in ("bad", "fail", "empty"):
            with self.subTest(mode=mode):
                out = self.run_bridge("review", "--cwd", str(self.repo), mode=mode, expect=3)
                self.assertIn("@reviewer", out["error"])
        self.assertTrue(all(e["ok"] is False for e in self.ledger()))

    def test_timeout_cancels_only_jobs_from_this_call(self):
        (self.repo / "app.txt").write_text("mudado\n")
        self.running.write_text(json.dumps([{"id": "job-alheio"}]))
        out = self.run_bridge("review", "--cwd", str(self.repo), "--timeout", "1", mode="slow", expect=3)
        self.assertIn("pgid:", out["error"])
        self.assertEqual(self.codex_calls("cancel"), [], "nada de cancel por id: só o grupo desta chamada morre")
        entry = self.ledger()[0]
        self.assertEqual((len(entry["cancelled"]), entry["failed"]), (1, []))

    def test_codex_never_reviews_its_own_worktree(self):
        out = self.run_bridge("build", "--repo", str(self.repo), "--brief", self.brief(), "--label", "feat-x")
        refused = self.run_bridge("review", "--cwd", out["worktree"], expect=4)
        self.assertIn("próprio trabalho", refused["error"])

    def test_minimal_environment_and_own_state(self):
        (self.repo / "app.txt").write_text("mudado\n")
        self.run_bridge("review", "--cwd", str(self.repo))
        for call in self.calls_list():
            self.assertIsNone(call["secret_env"])
            self.assertIsNone(call["transcript"], "a transcrição do Claude não vai para o Codex")
            self.assertEqual(call["plugin_data"], self.env["HEBE_CODEX_STATE"])
            self.assertTrue(call["endpoint"].endswith("no-broker.sock"), "força o modo direto")

    def test_review_refuses_secret_content(self):
        (self.repo / ".env.local").write_text("X=1\n")
        out = self.run_bridge("review", "--cwd", str(self.repo), expect=4)
        self.assertIn(".env.local", out["error"])
        (self.repo / ".env.local").unlink()
        (self.repo / "config.py").write_text("API_KEY = 'sk-ant-api03-" + "B" * 40 + "'\n")
        out = self.run_bridge("review", "--cwd", str(self.repo), expect=4)
        self.assertIn("segredo", out["error"])
        self.assertEqual(self.codex_calls("adversarial-review"), [])

    def test_isolated_codex_home_and_login(self):
        (self.repo / "app.txt").write_text("mudado\n")
        self.run_bridge("review", "--cwd", str(self.repo))
        home = self.root / "codex-home"
        self.assertTrue(all(c["codex_home"] == str(home) for c in self.calls_list()))
        config = (home / "config.toml").read_text()
        self.assertNotIn("mcp_servers", config)
        self.assertIn("network_access = false", config)
        self.assertEqual(oct(home.stat().st_mode & 0o777), "0o700")
        (home / "AGENTS.md").write_text("crie Brain.md\n")
        self.run_bridge("review", "--cwd", str(self.repo))
        self.assertFalse((home / "AGENTS.md").exists(), "instruções globais não entram no home isolado")
        self.env["HEBE_CODEX_LOGIN_CMD"] = "false"
        calls_before = len(self.calls_list())
        out = self.run_bridge("review", "--cwd", str(self.repo), expect=3)
        self.assertIn("codex login", out["error"])
        self.assertEqual(len(self.calls_list()), calls_before, "sem login isolado nada vai para o Codex")

    def test_policy_is_case_insensitive_where_the_disk_is(self):
        probe = self.root / "CaseProbe"
        probe.mkdir()
        if not (self.root / "caseprobe").exists():
            self.skipTest("sistema de arquivos diferencia maiúsculas")
        (self.repo / "app.txt").write_text("mudado\n")
        self.run_bridge("policy", "deny", str(self.repo).upper())
        self.run_bridge("review", "--cwd", str(self.repo), expect=4)

    def test_secret_in_focus_is_refused_before_any_call(self):
        (self.repo / "app.txt").write_text("mudado\n")
        out = self.run_bridge("review", "--cwd", str(self.repo),
                              "--focus", "use a chave sk-ant-api03-" + "A" * 40, expect=4)
        self.assertIn("segredo", out["error"])
        self.assertEqual(self.calls_list(), [])

    def test_policy_blocks_path_and_its_repository(self):
        (self.repo / "app.txt").write_text("mudado\n")
        (self.repo / "private").mkdir()
        self.run_bridge("policy", "deny", str(self.repo / "private"))
        out = self.run_bridge("review", "--cwd", str(self.repo), expect=4)
        self.assertIn("bloqueada", out["error"])
        self.run_bridge("build", "--repo", str(self.repo), "--brief", self.brief(), "--label", "x", expect=4)
        self.assertEqual(self.calls_list(), [])
        self.run_bridge("policy", "allow", str(self.repo / "private"))
        self.run_bridge("review", "--cwd", str(self.repo))

    # ------------------------------------------------------------ build

    def test_build_uses_isolated_worktree_and_reports_scope(self):
        out = self.run_bridge("build", "--repo", str(self.repo), "--brief", self.brief(), "--label", "feat-x",
                              "--copy", "node_modules", "--allow", ".")
        wt = Path(out["worktree"])
        self.assertTrue(str(wt).startswith(str(self.root / "worktrees")))
        self.assertTrue((wt / "feature.txt").exists())
        self.assertFalse((self.repo / "feature.txt").exists(), "a árvore do Claude não pode mudar")
        self.assertTrue((wt / "node_modules" / "dep.js").exists())
        self.assertEqual(out["scope_flags"], [])
        call = self.codex_calls("task")[0]
        self.assertEqual(call[call.index("--effort") + 1], "high")
        self.assertEqual(call[call.index("--model") + 1], "gpt-6-astra")
        entry = self.ledger()[0]
        self.assertEqual((entry["kind"], entry["effort"], entry["ok"]), ("build", "high", True))

    def test_build_flags_scope_problems(self):
        out = self.run_bridge("build", "--repo", str(self.repo), "--brief", self.brief(), "--label", "feat-y",
                              "--allow", "src", mode="scope")
        reasons = {flag["reason"] for flag in out["scope_flags"]}
        self.assertIn("lockfile alterado (dependência)", reasons)
        self.assertTrue(any("vault" in r for r in reasons))
        self.assertIn("log ou resultado de teste versionado", reasons)
        self.assertIn("fora das pastas permitidas", reasons)
        self.assertIn("arquivo apagado", reasons, "renomear não pode esconder o apagado")

    def test_copy_refusals_create_no_worktree(self):
        (self.repo / "linked").symlink_to(self.home)
        (self.repo / "plain").write_text("arquivo\n")
        (self.repo / "tracked").mkdir()
        (self.repo / "tracked" / "f").write_text("x\n")
        git(self.repo, "add", "tracked")
        git(self.repo, "commit", "-q", "-m", "tracked")
        for rel, code in ((".env", 4), ("linked", 4), ("plain", 2), ("tracked", 2), ("../home", 2)):
            with self.subTest(copy=rel):
                self.run_bridge("build", "--repo", str(self.repo), "--brief", self.brief(), "--label", "c",
                                "--copy", rel, expect=code)
        self.assertFalse((self.root / "worktrees").exists() and any((self.root / "worktrees").iterdir()))
        self.assertEqual(self.codex_calls("task"), [])

    def test_copy_scans_inside_the_folder(self):
        cache = self.repo / "node_modules"
        (cache / "pkg").mkdir()
        (cache / "pkg" / "index.js").write_text("x\n")
        (cache / ".bin").mkdir()
        (cache / ".bin" / "tool").symlink_to("../pkg/index.js")
        (cache / "pkg" / "cert.pem").write_text("-----BEGIN CERTIFICATE-----\n")
        out = self.run_bridge("build", "--repo", str(self.repo), "--brief", self.brief(), "--label", "ok",
                              "--copy", "node_modules")
        self.assertTrue((Path(out["worktree"]) / "node_modules" / ".bin" / "tool").is_symlink())
        cases = {
            "env": lambda: (cache / "pkg" / ".env").write_text("TOKEN=x\n"),
            "key": lambda: (cache / "pkg" / "server.key").write_text("-----BEGIN PRIVATE KEY-----\n"),
            "fora": lambda: (cache / "escape").symlink_to(self.home),
            "absoluto": lambda: (cache / "abs").symlink_to(cache / "pkg" / "index.js"),
        }
        for name, make in cases.items():
            with self.subTest(case=name):
                make()
                refused = self.run_bridge("build", "--repo", str(self.repo), "--brief", self.brief(),
                                          "--label", "c", "--copy", "node_modules", expect=4)
                self.assertIn("recusado", refused["error"])
                for leftover in ("pkg/.env", "pkg/server.key", "escape", "abs"):
                    target = cache / leftover
                    if target.is_symlink() or target.exists():
                        target.unlink()

    def test_interrupt_cancels_own_job_and_keeps_worktree(self):
        import signal, time as _time
        env = dict(self.env, FAKE_MODE="slow")
        proc = subprocess.Popen([sys.executable, str(SCRIPT), "build", "--repo", str(self.repo), "--brief",
                                 self.brief(), "--label", "intr"], stdout=subprocess.PIPE, text=True, env=env)
        _time.sleep(2)
        proc.send_signal(signal.SIGINT)
        out, _ = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 3, out)
        self.assertIn("interrompida", json.loads(out)["error"])
        self.assertEqual(len(self.ledger()[-1]["cancelled"]), 1)
        worktrees = list((self.root / "worktrees").iterdir())
        self.assertEqual(len(worktrees), 1, "a worktree precisa ficar para inspeção")
        self.assertTrue((worktrees[0] / "feature.txt").exists())

    def test_change_to_already_dirty_main_file_is_flagged(self):
        (self.repo / "app.txt").write_text("sujo antes do build\n")
        env_main = str(self.repo / "app.txt")
        self.env["FAKE_MAIN"] = env_main
        out = self.run_bridge("build", "--repo", str(self.repo), "--brief", self.brief(), "--label", "m",
                              mode="touchmain")
        flags = [f for f in out["scope_flags"] if "árvore do Claude mudou" in f["reason"]]
        self.assertEqual([f["file"] for f in flags], ["(árvore principal) app.txt"])

    def test_missing_companion_leaves_no_orphan_worktree(self):
        env = dict(self.env)
        env.pop("HEBE_CODEX_COMPANION_CMD")
        env["HEBE_CODEX_COMPANION"] = str(self.root / "nao-existe.mjs")
        done = subprocess.run([sys.executable, str(SCRIPT), "build", "--repo", str(self.repo), "--brief",
                               self.brief(), "--label", "z"], capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 3)
        branches = subprocess.run(["git", "-C", str(self.repo), "branch", "--list", "codex/*"],
                                  capture_output=True, text=True).stdout
        self.assertEqual(branches.strip(), "")

    def test_brief_limits(self):
        self.run_bridge("build", "--repo", str(self.repo), "--brief", self.brief("é" * 40000), "--label", "z", expect=2)
        self.run_bridge("build", "--repo", str(self.repo), "--brief", self.brief("x\n"), "--label", "z",
                        "--effort", "ultra", expect=2)

    def test_cleanup_keeps_branch_with_commits(self):
        out = self.run_bridge("build", "--repo", str(self.repo), "--brief", self.brief(), "--label", "feat-k")
        git(out["worktree"], "add", "-A")
        git(out["worktree"], "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "trabalho")
        done = self.run_bridge("cleanup", "--worktree", out["worktree"], "--force")
        self.assertFalse(done["branch_deleted"])
        branches = subprocess.run(["git", "-C", str(self.repo), "branch", "--list", out["branch"]],
                                  capture_output=True, text=True).stdout
        self.assertIn(out["branch"], branches)

    def test_sigterm_cancels_own_job(self):
        import signal, time as _time
        env = dict(self.env, FAKE_MODE="slow")
        proc = subprocess.Popen([sys.executable, str(SCRIPT), "build", "--repo", str(self.repo), "--brief",
                                 self.brief(), "--label", "term"], stdout=subprocess.PIPE, text=True, env=env)
        _time.sleep(2)
        proc.send_signal(signal.SIGTERM)
        out, _ = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 3, out)
        self.assertEqual(len(self.ledger()[-1]["cancelled"]), 1)

    def test_bad_allow_and_brief(self):
        self.run_bridge("build", "--repo", str(self.repo), "--brief", self.brief(), "--label", "a",
                        "--allow", "", expect=2)
        fifo = self.root / "brief.fifo"
        os.mkfifo(fifo)
        out = self.run_bridge("build", "--repo", str(self.repo), "--brief", str(fifo), "--label", "a", expect=2)
        self.assertIn("arquivo comum", out["error"])

    def test_cleanup_removes_worktree_and_branch(self):
        out = self.run_bridge("build", "--repo", str(self.repo), "--brief", self.brief(), "--label", "feat-c")
        self.run_bridge("cleanup", "--worktree", out["worktree"], expect=2)
        done = self.run_bridge("cleanup", "--worktree", out["worktree"], "--force")
        self.assertTrue(done["branch_deleted"])
        self.assertFalse(Path(out["worktree"]).exists())
        refused = self.run_bridge("cleanup", "--worktree", str(self.repo), expect=2)
        self.assertIn("Só removo", refused["error"])

    # ------------------------------------------------------------ experimento

    def test_outcome_validated_by_kind_and_report(self):
        (self.repo / "app.txt").write_text("mudado\n")
        review = self.run_bridge("review", "--cwd", str(self.repo))
        self.run_bridge("outcome", "--id", review["ledger_id"], "--result", "accepted", expect=2)
        self.run_bridge("outcome", "--id", review["ledger_id"], "--result", "confirmed", "--real", "1",
                        "--false", "1", "--missed", "2", "--reviewer", "opus")
        report = self.run_bridge("report", "--days", "30")
        group = report["groups"][0]
        self.assertEqual((group["kind"], group["runs"], group["precision"]), ("review", 1, 0.5))
        self.assertEqual(group["missed_reported"], 2)
        self.assertEqual(group["outcomes"], {"confirmed": 1})
        self.run_bridge("outcome", "--id", "nao-existe", "--result", "accepted", expect=2)

    def test_rotated_ledger_is_still_read(self):
        (self.repo / "app.txt").write_text("mudado\n")
        review = self.run_bridge("review", "--cwd", str(self.repo))
        folder = self.home / ".config" / "hebe-brain"
        os.replace(folder / "codex-experiment.jsonl", folder / "codex-experiment.jsonl.1")
        self.run_bridge("outcome", "--id", review["ledger_id"], "--result", "noise")
        self.assertEqual(self.run_bridge("report")["groups"][0]["outcomes"], {"noise": 1})


if __name__ == "__main__":
    unittest.main()
