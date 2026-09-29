"""Contrato de empacotamento: manifestos, frontmatter e texto das skills/comandos."""

import json
from pathlib import Path
import re
import unittest


PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parent
MODELS = {"haiku", "sonnet", "opus", "fable"}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        raise AssertionError("%s sem frontmatter" % path)
    return dict(line.split(": ", 1) for line in match.group(1).splitlines() if ": " in line), text


class ManifestTests(unittest.TestCase):
    @unittest.skipUnless((REPO / ".claude-plugin" / "marketplace.json").exists(), "fora do checkout do repositório")
    def test_versions_match_everywhere(self):
        claude = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]
        codex = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())["version"]
        market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
        entry = next(p for p in market["plugins"] if p["name"] == "hebe-orchestrator")
        changelog = re.search(r"^## (\d+\.\d+\.\d+)", (REPO / "CHANGELOG.md").read_text(), re.M).group(1)
        self.assertEqual({claude, codex, entry["version"], changelog}, {claude})

    def test_codex_manifest_points_only_to_codex_skills(self):
        manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["skills"], "./codex-skills/")
        self.assertTrue((PLUGIN / "codex-skills" / "orchestrate" / "SKILL.md").is_file())

    def test_agents_frontmatter(self):
        agents = sorted((PLUGIN / "agents").glob("*.md"))
        self.assertEqual([a.stem for a in agents], ["advisor", "code-worker", "design-worker", "reviewer", "worker"])
        for path in agents:
            with self.subTest(agent=path.stem):
                meta, _ = frontmatter(path)
                self.assertEqual(meta["name"], path.stem)
                self.assertIn(meta["model"], MODELS)
                self.assertTrue(meta.get("description"))
                if meta["model"] == "haiku":
                    self.assertNotIn("effort", meta, "o Haiku 4.5 não aceita esforço")
                elif "effort" in meta:
                    self.assertIn(meta["effort"], EFFORTS)

    def test_skills_and_command_frontmatter(self):
        for path in [PLUGIN / "skills" / "orchestrator-guide" / "SKILL.md", PLUGIN / "codex-skills" / "orchestrate" / "SKILL.md"]:
            with self.subTest(skill=str(path.relative_to(PLUGIN))):
                meta, _ = frontmatter(path)
                self.assertTrue(meta.get("name") and meta.get("description"))
        meta, text = frontmatter(PLUGIN / "commands" / "orchestrate.md")
        self.assertTrue(meta.get("description"))
        self.assertIn("$ARGUMENTS", text)

    def test_no_positional_placeholders_in_skill_text(self):
        # "$1", "$2"... viram argumentos quando a skill ou o comando recebe texto.
        for path in [PLUGIN / "commands" / "orchestrate.md", PLUGIN / "skills" / "orchestrator-guide" / "SKILL.md",
                     PLUGIN / "codex-skills" / "orchestrate" / "SKILL.md"]:
            with self.subTest(file=str(path.relative_to(PLUGIN))):
                self.assertIsNone(re.search(r"\$\d", path.read_text(encoding="utf-8")))

    def test_scripts_referenced_by_docs_exist(self):
        for name in ("jev.py", "jev_decide.py", "jev_rules.py"):
            self.assertTrue((PLUGIN / "scripts" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
