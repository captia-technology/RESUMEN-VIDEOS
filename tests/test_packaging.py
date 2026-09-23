"""Packaging checks: manifests agree, the skill follows the Agent Skills spec and the installer is safe."""

import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "resumir-video"
SKILL = PLUGIN / "skills" / "resumir-video"
INSTALLER = ROOT / "scripts" / "install.py"
MANIFESTS = {"agent-plugins": PLUGIN / "plugin.json", "claude": PLUGIN / ".claude-plugin" / "plugin.json",
             "codex": PLUGIN / ".codex-plugin" / "plugin.json"}
SHARED = ("name", "version", "description", "author", "homepage", "repository", "license", "keywords")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AssertionError(f"{path} debe empezar por '---' y LF")
    block = text[4:].split("\n---\n", 1)[0]
    data, parent = {}, None
    for line in block.splitlines():
        key, _, value = line.strip().partition(":")
        value = value.strip().strip('"')
        if line[:1] in (" ", "\t"):
            data[parent][key] = value
        else:
            parent = key
            data[key] = value or {}
    return data


class ManifestTest(unittest.TestCase):
    def test_plugin_manifests_share_metadata(self):
        manifests = {name: load(path) for name, path in MANIFESTS.items()}
        entry = load(ROOT / ".claude-plugin" / "marketplace.json")["plugins"][0]
        for field in SHARED:
            with self.subTest(field=field):
                values = [m.get(field) for m in manifests.values()] + [entry.get(field)]
                self.assertTrue(all(v == values[0] for v in values), values)
        self.assertEqual(manifests["claude"]["name"], SKILL.name)

    def test_versions_agree_everywhere(self):
        version = load(MANIFESTS["claude"])["version"]
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        claude_market = load(ROOT / ".claude-plugin" / "marketplace.json")
        self.assertEqual(claude_market["metadata"]["version"], version)
        self.assertEqual(frontmatter(SKILL / "SKILL.md")["metadata"]["version"], version)
        script = (SKILL / "scripts" / "video.py").read_text(encoding="utf-8")
        self.assertIn(f'__version__ = "{version}"', script)
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertEqual(re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.M).group(1), version)
        for doc, phrase in (("README.md", f"Versión {version} ·"),
                            ("docs/capacidades.md", f"`resumir-video` {version}"),
                            ("docs/instalacion.md", f"Estado: versión {version}")):
            with self.subTest(doc=doc):
                self.assertIn(phrase, (ROOT / doc).read_text(encoding="utf-8"))

    def test_marketplaces_point_to_the_plugin(self):
        claude = load(ROOT / ".claude-plugin" / "marketplace.json")
        codex = load(ROOT / ".agents" / "plugins" / "marketplace.json")
        self.assertEqual(claude["name"], codex["name"])
        self.assertRegex(claude["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertTrue(claude["owner"]["name"])
        for entry, source in ((claude["plugins"][0], claude["plugins"][0]["source"]),
                              (codex["plugins"][0], codex["plugins"][0]["source"]["path"])):
            self.assertEqual(entry["name"], "resumir-video")
            self.assertTrue(source.startswith("./"))
            self.assertEqual((ROOT / source).resolve(), PLUGIN)
        policy = codex["plugins"][0]["policy"]
        self.assertIn(policy["installation"], ("AVAILABLE", "INSTALLED_BY_DEFAULT", "NOT_AVAILABLE"))
        self.assertIn(policy["authentication"], ("ON_INSTALL", "ON_USE"))
        self.assertTrue(codex["plugins"][0]["category"])

    def test_agent_plugins_manifest_uses_the_closed_schema(self):
        manifest = load(MANIFESTS["agent-plugins"])
        self.assertEqual(manifest["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        allowed = {"$schema", "name", "version", "description", "author", "homepage",
                   "repository", "license", "keywords", "extensions"}
        self.assertLessEqual(set(manifest), allowed)

    def test_codex_interface_is_complete(self):
        manifest = load(MANIFESTS["codex"])
        self.assertEqual(manifest["skills"], "./skills/")
        interface = manifest["interface"]
        for field in ("displayName", "shortDescription", "longDescription", "developerName", "category"):
            self.assertTrue(interface[field].strip(), field)
        self.assertTrue(interface["capabilities"])
        prompts = interface["defaultPrompt"]
        self.assertTrue(1 <= len(prompts) <= 3 and all(len(p) <= 128 for p in prompts))
        self.assertTrue(all(url.startswith("https://") for key, url in interface.items() if key.endswith("URL")))


class SkillTest(unittest.TestCase):
    def test_frontmatter_follows_the_portable_spec(self):
        data = frontmatter(SKILL / "SKILL.md")
        self.assertLessEqual(set(data), {"name", "description", "license", "metadata"})
        self.assertEqual(data["name"], SKILL.name)
        self.assertRegex(data["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertLessEqual(len(data["name"]), 64)
        self.assertTrue(1 <= len(data["description"]) <= 1024)
        self.assertNotRegex(data["description"], r"[<>]")
        self.assertEqual(data["license"], load(MANIFESTS["claude"])["license"])
        self.assertLess(len((SKILL / "SKILL.md").read_text(encoding="utf-8").splitlines()), 500)

    def test_codex_metadata(self):
        text = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        top = {line.split(":")[0] for line in text.splitlines() if line and not line[0].isspace()}
        self.assertLessEqual(top, {"interface", "policy", "dependencies"})
        short = re.search(r'short_description:\s*"(.*)"', text).group(1)
        self.assertTrue(25 <= len(short) <= 64)
        self.assertIn("$resumir-video", re.search(r'default_prompt:\s*"(.*)"', text).group(1))

    def test_license_copies_are_identical(self):
        reference = (ROOT / "LICENSE").read_bytes()
        for copy in (PLUGIN / "LICENSE", SKILL / "LICENSE.txt"):
            self.assertEqual(copy.read_bytes(), reference, copy)

    def test_payload_is_portable(self):
        forbidden = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|/Users/|/home/|\bCodex\b decide|corresponde a Codex")
        for path in PLUGIN.rglob("*"):
            if path.is_file() and path.suffix in (".md", ".py", ".json", ".yaml", ".txt"):
                with self.subTest(path=path.relative_to(ROOT)):
                    self.assertIsNone(forbidden.search(path.read_text(encoding="utf-8")))

    def test_repository_docs_have_no_local_paths(self):
        # Drive letters, home folders and UNC shares (\\server\share).
        forbidden = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|/Users/|/home/|\\\\[A-Za-z0-9]")
        documents = [ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "CHANGELOG.md",
                     ROOT / "CONTRIBUTING.md", ROOT / "SECURITY.md",
                     *sorted((ROOT / "docs").glob("*.md"))]
        for path in documents:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsNone(forbidden.search(path.read_text(encoding="utf-8")))

    def test_referenced_files_exist(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)#]+)\)", text):
            self.assertTrue((SKILL / target).is_file(), target)
        for relative in ("scripts/common.py", "scripts/video.py", "scripts/plan.py",
                         "scripts/render.py", "scripts/doc.py", "scripts/test_video.py",
                         "references/operacion.md", "references/compresion.md",
                         "references/revision.md", "references/documento.md",
                         "agents/openai.yaml"):
            self.assertTrue((SKILL / relative).is_file(), relative)

    def test_the_references_describe_the_0_2_0_behaviour(self):
        operation = (SKILL / "references" / "operacion.md").read_text(encoding="utf-8")
        for gone in ("El montaje no se reanuda", "Cada imagen es una búsqueda independiente"):
            self.assertNotIn(gone, operation)
        for present in ("bSSSSS", "indice.gray", "hoja-", "--budget", "--dll-dir",
                        "missing_filters", "degraded", "bloques"):
            self.assertIn(present, operation)

    def test_repository_has_a_single_copy_of_the_skill(self):
        # A project copy would shadow the plugin in Copilot and duplicate it in Codex.
        for folder in (".claude/skills", ".agents/skills", ".github/skills", "skills"):
            self.assertFalse((ROOT / folder / "resumir-video").exists(), folder)

    def test_skill_covers_both_modes_and_the_eleven_step_flow(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        data = frontmatter(SKILL / "SKILL.md")
        for word in ("audio", "documento"):
            self.assertIn(word, data["description"].lower())
        for heading in ("## Invocación", "## Modos", "## Flujo"):
            self.assertIn(heading, text)
        flow = text.split("## Flujo", 1)[1]
        self.assertEqual(len(re.findall(r"^\d+\. \*\*", flow, re.M)), 11)
        for gone in ("No impongas un porcentaje fijo", "No acelera ni recorta la imagen"):
            self.assertNotIn(gone, text)

    def test_every_script_has_its_tests_and_the_skill_stays_self_contained(self):
        scripts = sorted(p.name for p in (SKILL / "scripts").glob("*.py")
                         if not p.name.startswith("test_"))
        self.assertEqual(scripts, ["common.py", "doc.py", "plan.py", "render.py", "video.py"])
        for name in scripts:
            if name != "common.py":
                self.assertTrue((SKILL / "scripts" / f"test_{name}").is_file(), name)
        self.assertFalse(list(SKILL.rglob("__pycache__")))
        entry = (SKILL / "scripts" / "video.py").read_text(encoding="utf-8")
        self.assertIn("sys.dont_write_bytecode = True", entry)
        # La skill no puede depender de la documentación del repositorio.
        for path in SKILL.rglob("*.md"):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotIn("](../../../../docs/", path.read_text(encoding="utf-8"))

    def test_the_repository_documents_the_0_2_0_decisions(self):
        decisions = (ROOT / "docs" / "decisiones.md").read_text(encoding="utf-8")
        for identifier in ("D-007", "D-008", "D-009", "D-010", "D-011"):
            self.assertIn(f"## {identifier} — ", decisions)
        self.assertEqual(decisions.count("Actualización (2026-09-18"), 1)
        architecture = (ROOT / "docs" / "arquitectura.md").read_text(encoding="utf-8")
        for module in ("common.py", "plan.py", "render.py", "doc.py"):
            self.assertIn(module, architecture)
        # Las tres desviaciones respecto a la especificación quedan registradas en los dos sitios.
        for note in ("seek_margin", "-copyts", "trim=end="):
            self.assertIn(note, decisions)
            self.assertIn(note, architecture)
        requirements = (ROOT / "docs" / "requisitos.md").read_text(encoding="utf-8")
        for identifier in ("R1", "R2", "R3", "R4", "R5", "A-1", "A-6", "40 ms", "8 dB"):
            self.assertIn(identifier, requirements)


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resumir-video-install-")
        self.home = Path(self.temporary.name)
        self.env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CONFIG_DIR", "COPILOT_HOME")}
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home))

    def tearDown(self):
        self.temporary.cleanup()

    def run_installer(self, *arguments, ok=True, env=None):
        result = subprocess.run([sys.executable, "-B", str(INSTALLER), "--skip-check", *map(str, arguments)],
                                capture_output=True, text=True, encoding="utf-8", env=env or self.env)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def test_user_install_update_and_uninstall(self):
        claude = self.home / ".claude/skills/resumir-video"
        shared = self.home / ".agents/skills/resumir-video"
        self.run_installer("--dry-run")
        self.assertFalse(claude.exists() or shared.exists())
        self.run_installer()
        for dest in (claude, shared):
            self.assertTrue((dest / "SKILL.md").is_file())
            self.assertFalse(list(dest.rglob("__pycache__")))
        self.assertFalse((self.home / ".copilot").exists())
        self.assertIn("ya instalada", self.run_installer())
        (shared / "SKILL.md").write_text("---\nname: resumir-video\ndescription: antigua\n---\n", encoding="utf-8")
        self.assertIn("desactualizada", self.run_installer("--status"))
        self.run_installer(ok=False)
        self.run_installer("--force")
        self.assertIn("actualizada", self.run_installer("--status", "--agent", "codex"))
        self.run_installer("--uninstall")
        self.assertFalse(claude.exists() or shared.exists())

    def test_foreign_folders_are_never_touched(self):
        foreign = self.home / ".claude/skills/resumir-video"
        foreign.mkdir(parents=True)
        (foreign / "SKILL.md").write_text("---\nname: otra\ndescription: x\n---\n", encoding="utf-8")
        self.run_installer("--agent", "claude", "--force", ok=False)
        self.run_installer("--agent", "claude", "--uninstall", ok=False)
        self.assertIn("name: otra", (foreign / "SKILL.md").read_text(encoding="utf-8"))

    def test_project_scope_and_copilot_home(self):
        project = self.home / "proyecto"
        project.mkdir()
        self.run_installer("--scope", "project", "--project-dir", project)
        self.assertTrue((project / ".claude/skills/resumir-video/SKILL.md").is_file())
        self.assertTrue((project / ".agents/skills/resumir-video/SKILL.md").is_file())
        env = dict(self.env, COPILOT_HOME=str(self.home / "copilot"))
        self.run_installer("--agent", "copilot", env=env)
        self.assertTrue((self.home / "copilot/skills/resumir-video/SKILL.md").is_file())

    def test_project_scope_requires_an_existing_project(self):
        missing = self.home / "proyecto-inexistente"
        self.assertIn("no existe", self.run_installer("--scope", "project", "--project-dir", missing, ok=False))
        self.assertFalse(missing.exists())

    def test_read_only_copies_can_be_updated_and_removed(self):
        self.run_installer("--agent", "codex")
        dest = self.home / ".agents/skills/resumir-video"
        (dest / "SKILL.md").write_text("---\nname: resumir-video\ndescription: antigua\n---\n", encoding="utf-8")
        for path in dest.rglob("*"):
            if path.is_file():
                os.chmod(path, stat.S_IREAD)
        self.run_installer("--agent", "codex", "--uninstall", ok=False)
        self.run_installer("--agent", "codex", "--force")
        self.assertFalse(list(dest.parent.glob(".resumir-video.*")))
        self.assertIn("actualizada", self.run_installer("--status", "--agent", "codex"))
        for path in dest.rglob("*"):
            if path.is_file():
                os.chmod(path, stat.S_IREAD)
        self.run_installer("--agent", "codex", "--uninstall")
        self.assertFalse(dest.exists())

    def test_generated_junk_does_not_make_a_copy_look_outdated(self):
        # Running the skill's own tests without -B leaves __pycache__ inside the copy.
        self.run_installer("--agent", "codex")
        dest = self.home / ".agents/skills/resumir-video"
        (dest / "scripts" / "__pycache__").mkdir(parents=True)
        (dest / "scripts" / "__pycache__" / "video.cpython-311.pyc").write_bytes(b"\x00")
        for name in ("Thumbs.db", "desktop.ini", ".DS_Store"):
            (dest / name).write_bytes(b"\x00")
        self.assertNotIn("desactualizada", self.run_installer("--status", "--agent", "codex"))
        self.assertIn("ya instalada", self.run_installer("--agent", "codex"))
        self.run_installer("--agent", "codex", "--uninstall")
        self.assertFalse(dest.exists())

    def test_status_and_dry_run_change_nothing(self):
        self.run_installer("--agent", "codex")
        skills = self.home / ".agents/skills"
        leftovers = [skills / ".resumir-video.nuevo", skills / ".resumir-video.anterior"]
        for action in (("--status",), ("--dry-run",), ("--uninstall", "--dry-run")):
            for leftover in leftovers:
                leftover.mkdir(exist_ok=True)
            self.run_installer("--agent", "codex", *action)
            for leftover in leftovers:
                self.assertTrue(leftover.is_dir(), (action, leftover.name))
        for leftover in leftovers:
            shutil.rmtree(leftover)

    def test_uninstalling_a_link_keeps_its_target(self):
        target = self.home / "otro-sitio"
        shutil.copytree(SKILL, target)
        link = self.home / ".agents/skills/resumir-video"
        link.parent.mkdir(parents=True)
        self.make_link(target, link)
        self.run_installer("--agent", "codex", "--uninstall")
        self.assertFalse(link.exists())
        self.assertTrue((target / "SKILL.md").is_file())

    def test_leftovers_from_an_interrupted_run_are_cleaned(self):
        self.run_installer("--agent", "codex")
        skills = self.home / ".agents/skills"
        for action in (("--agent", "codex"), ("--agent", "codex", "--uninstall")):
            for name in (".resumir-video.nuevo", ".resumir-video.anterior"):
                (skills / name).mkdir()
                (skills / name / "SKILL.md").write_text("---\nname: resumir-video\ndescription: resto\n---\n",
                                                        encoding="utf-8")
            self.run_installer(*action)
            self.assertFalse(list(skills.glob(".resumir-video.*")), action)

    def test_dangling_links_are_detected_and_replaced(self):
        target = self.home / "borrado"
        target.mkdir()
        link = self.home / ".agents/skills/resumir-video"
        link.parent.mkdir(parents=True)
        self.make_link(target, link)
        target.rmdir()
        self.assertIn("enlace", self.run_installer("--status", "--agent", "codex"))
        self.run_installer("--agent", "codex", "--force")
        self.assertTrue((link / "SKILL.md").is_file())

    def make_link(self, target, link):
        # Windows: a junction, as created by other skill installers (symlinks need extra privileges).
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        else:
            os.symlink(target, link, target_is_directory=True)

    def test_links_are_replaced_without_touching_their_target(self):
        target = self.home / "otro-sitio"
        target.mkdir()
        (target / "SKILL.md").write_text("---\nname: resumir-video\ndescription: x\n---\n", encoding="utf-8")
        link = self.home / ".agents/skills/resumir-video"
        link.parent.mkdir(parents=True)
        self.make_link(target, link)
        self.assertIn("enlace", self.run_installer("--status", "--agent", "codex"))
        self.run_installer("--agent", "codex", ok=False)
        self.run_installer("--agent", "codex", "--force")
        self.assertIn("description: x", (target / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("actualizada", self.run_installer("--status", "--agent", "codex"))


if __name__ == "__main__":
    unittest.main()
