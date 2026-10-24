"""Keep agent entry points, links and mirrored copies consistent."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_DOCS = (
    ROOT / "AGENTS.md",
    ROOT / ".agents" / "AGENTS.md",
    ROOT / ".cursor" / "rules" / "project.mdc",
    ROOT / "CLAUDE.md",
    ROOT / "README.md",
)
SKILLS = (
    ROOT / ".opencode" / "skills" / "cavecrew" / "SKILL.md",
    ROOT / ".opencode" / "skills" / "cavecrew" / "references" / "hermes-roles.md",
    ROOT / ".opencode" / "skills" / "steamvrcolourlab-build" / "SKILL.md",
    ROOT / ".agents" / "skills" / "cavecrew" / "SKILL.md",
    ROOT / ".agents" / "skills" / "cavecrew" / "references" / "hermes-roles.md",
    ROOT / ".agents" / "skills" / "steamvrcolourlab-build" / "SKILL.md",
)
AGENTS = (
    ROOT / ".opencode" / "agents" / "cavecrew-builder.md",
    ROOT / ".opencode" / "agents" / "cavecrew-investigator.md",
    ROOT / ".opencode" / "agents" / "cavecrew-reviewer.md",
)
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def frontmatter(path: Path) -> dict[str, str]:
    body = text(path)
    if not body.startswith("---\n"):
        return {}
    block = body.split("---", 2)[1]
    fields: dict[str, str] = {}
    key = None
    for line in block.splitlines():
        if line.startswith((" ", "\t")) and key:
            fields[key] += " " + line.strip()
        elif ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


class AgentDocTests(unittest.TestCase):
    def test_required_entry_points_exist(self):
        for path in (*CORE_DOCS, *SKILLS, *AGENTS, ROOT / "CLAUDE.md"):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertTrue(path.is_file(), path)

    def test_local_links_resolve(self):
        for path in (*CORE_DOCS, *SKILLS, *AGENTS):
            for target in LINK.findall(text(path)):
                target = target.split("#", 1)[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                resolved = (path.parent / target).resolve()
                if ROOT not in resolved.parents and resolved != ROOT:
                    # Workspace links only exist when this checkout sits inside
                    # the full toolkit. CI checks the repository alone.
                    continue
                with self.subTest(document=path.relative_to(ROOT), target=target):
                    self.assertTrue(resolved.exists(), resolved)

    def test_mirrored_skills_and_agents_match(self):
        pairs = (
            (ROOT / ".opencode" / "skills" / "cavecrew" / "SKILL.md",
             ROOT / ".agents" / "skills" / "cavecrew" / "SKILL.md"),
            (ROOT / ".opencode" / "skills" / "cavecrew" / "references" / "hermes-roles.md",
             ROOT / ".agents" / "skills" / "cavecrew" / "references" / "hermes-roles.md"),
            (ROOT / ".opencode" / "skills" / "steamvrcolourlab-build" / "SKILL.md",
             ROOT / ".agents" / "skills" / "steamvrcolourlab-build" / "SKILL.md"),
        )
        for canonical, mirror in pairs:
            with self.subTest(skill=mirror.relative_to(ROOT)):
                self.assertEqual(text(canonical), text(mirror))
        workspace_agents = ROOT.parent / ".opencode" / "agents"
        if workspace_agents.is_dir():
            for path in AGENTS:
                mirror = workspace_agents / path.name
                with self.subTest(agent=path.name):
                    self.assertTrue(mirror.is_file(), mirror)
                    self.assertEqual(text(path), text(mirror))

    def test_skill_frontmatter_matches_directory(self):
        for path in SKILLS:
            if path.name != "SKILL.md":
                continue
            with self.subTest(skill=path.parent.name):
                fields = frontmatter(path)
                self.assertEqual(fields.get("name"), path.parent.name)
                self.assertTrue(fields.get("description"))
                self.assertLessEqual(len(fields["description"]), 240)

    def test_agent_descriptions_are_short(self):
        for path in AGENTS:
            with self.subTest(agent=path.name):
                description = frontmatter(path).get("description", "")
                self.assertTrue(description)
                self.assertLessEqual(len(description), 160)

    def test_no_stale_host_claims_or_typos(self):
        corpus = "\n".join(text(path) for path in (*CORE_DOCS, *SKILLS, *AGENTS))
        for stale in ("hermes-role-contracts", ".github/agents/", ".codex/",
                      "COLOULAB_OUTPUT_ROOT"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, corpus)

    def test_core_documents_stay_short(self):
        limits = {
            ROOT / "AGENTS.md": 9_000,
            ROOT / "README.md": 16_000,
            ROOT / ".agents" / "AGENTS.md": 1_500,
            ROOT / ".cursor" / "rules" / "project.mdc": 2_000,
            ROOT / "CLAUDE.md": 500,
        }
        workspace_agents = ROOT.parent / "AGENTS.md"
        if workspace_agents.is_file():
            limits[workspace_agents] = 9_000
        for path, limit in limits.items():
            label = path.relative_to(ROOT) if ROOT in path.parents else path.name
            with self.subTest(document=label):
                self.assertLessEqual(path.stat().st_size, limit)


if __name__ == "__main__":
    unittest.main()
