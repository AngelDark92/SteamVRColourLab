"""Release-policy regression tests using disposable, real Git repositories."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.release_policy import ReleasePolicyError, release_plan


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "release_policy.py"


class ReleasePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_AUTHOR_NAME="Release Test", GIT_COMMITTER_NAME="Release Test",
                        GIT_AUTHOR_EMAIL="test@example.invalid",
                        GIT_COMMITTER_EMAIL="test@example.invalid")
        self.git("init", "--initial-branch=main")
        package = self.repo / "colourlab"
        package.mkdir()
        (package / "__init__.py").write_bytes(
            b'"""Preserve this module."""\r\n__version__ = "0.2.1"  # preserve comment\r\n'
            b'OTHER = "unchanged"\r\n'
        )
        self.git("add", ".")
        self.commit("chore: initial source")

    def git(self, *args, repo=None):
        return subprocess.run(
            ["git", "-C", str(repo or self.repo), *args], env=self.env,
            text=True, encoding="utf-8", capture_output=True, check=True,
        ).stdout.strip()

    def commit(self, subject, body=None):
        args = ["commit", "--allow-empty", "--no-gpg-sign", "-m", subject]
        if body is not None:
            args.extend(["-m", body])
        self.git(*args)

    def test_prefixes_and_lower_component_resets(self):
        for prefix, expected, bump in (
            ("fix", "2.5.10", "patch"),
            ("feat", "2.6.0", "minor"),
            ("rework", "3.0.0", "major"),
        ):
            with self.subTest(prefix=prefix):
                self.git("tag", "-f", "v2.5.9")
                self.commit(f"{prefix}: change")
                plan = release_plan(self.repo)
                self.assertEqual(plan["version"], expected)
                self.assertEqual(plan["bump"], bump)
                self.assertTrue(plan["release"])

    def test_highest_bump_wins_across_all_new_subjects(self):
        self.git("tag", "v1.7.9")
        for prefix in ("fix", "feat", "rework", "fix"):
            self.commit(f"{prefix}: change")
        plan = release_plan(self.repo)
        self.assertEqual(plan["version"], "2.0.0")
        self.assertEqual(plan["bump"], "major")

    def test_scoped_prefixes(self):
        self.git("tag", "v1.2.3")
        for prefix, expected in (("fix", "1.2.4"), ("feat", "1.3.0"), ("rework", "2.0.0")):
            with self.subTest(prefix=prefix):
                self.commit(f"{prefix}(windows build): scoped change")
                self.assertEqual(release_plan(self.repo)["version"], expected)

    def test_unrecognized_subjects_do_not_release(self):
        self.git("tag", "v1.2.3")
        for subject in ("docs: explain fix: sample", "chore: housekeeping", "prefix feat: embedded",
                        "Fix: wrong case", "fix:no separating space", "fix: ", "feat: \t ",
                        "rework(scope): "):
            self.commit(subject)
        plan = release_plan(self.repo)
        self.assertEqual(plan["version"], "1.2.3")
        self.assertEqual(plan["bump"], "none")
        self.assertFalse(plan["release"])
        self.assertFalse(plan["already_tagged"])

    def test_body_only_prefix_is_ignored(self):
        self.git("tag", "v1.2.3")
        self.commit("docs: release instructions", "rework: only an example\nfeat: another example")
        self.assertFalse(release_plan(self.repo)["release"])

    def test_tags_sort_numerically_not_by_name_or_commit_order(self):
        self.git("tag", "v1.9.0")
        self.commit("docs: older base")
        self.git("tag", "v1.10.0")
        self.commit("docs: newer commit with lower version")
        self.git("tag", "v1.2.30")
        self.commit("fix: latest change")
        plan = release_plan(self.repo)
        self.assertEqual(plan["base_tag"], "v1.10.0")
        self.assertEqual(plan["version"], "1.10.1")

    def test_tags_outside_head_history_are_not_a_base(self):
        self.git("tag", "v1.2.3")
        self.git("checkout", "-b", "other")
        self.commit("feat: unmerged feature")
        self.git("tag", "v9.0.0")
        self.git("checkout", "main")
        self.commit("fix: current branch")
        self.assertEqual(release_plan(self.repo)["version"], "1.2.4")

    def test_no_tags_uses_module_seed(self):
        plan = release_plan(self.repo)
        self.assertEqual(plan["version"], "0.2.1")
        self.assertIsNone(plan["base_tag"])
        self.assertFalse(plan["release"])
        self.commit("fix: first release")
        plan = release_plan(self.repo)
        self.assertEqual(plan["version"], "0.2.2")
        self.assertTrue(plan["release"])
        self.assertIsNone(plan["base_tag"])

    def test_commits_before_base_tag_do_not_contribute(self):
        self.commit("rework: already released")
        self.git("tag", "v1.2.3")
        self.commit("fix: one new change")
        self.assertEqual(release_plan(self.repo)["version"], "1.2.4")

    def test_head_tag_is_idempotent_and_allows_publication_retry(self):
        self.commit("rework: released already")
        self.git("tag", "-a", "v2.0.0", "-m", "Release 2.0.0")
        plan = release_plan(self.repo)
        self.assertEqual(plan["version"], "2.0.0")
        self.assertEqual(plan["tag"], "v2.0.0")
        self.assertEqual(plan["base_tag"], "v2.0.0")
        self.assertEqual(plan["bump"], "none")
        self.assertTrue(plan["release"])
        self.assertTrue(plan["already_tagged"])
        self.assertEqual(plan, release_plan(self.repo))

    def test_multiple_semantic_tags_on_head_are_rejected(self):
        self.git("tag", "v1.2.3")
        self.git("tag", "v1.2.4")
        with self.assertRaisesRegex(ReleasePolicyError, "Ambiguous"):
            release_plan(self.repo)

    def test_candidate_tag_collision_does_not_block_feature_branch_build(self):
        self.git("tag", "v1.2.3")
        self.git("checkout", "-b", "other")
        self.commit("fix: different release")
        self.git("tag", "v1.2.4")
        self.git("checkout", "main")
        self.commit("fix: current change")
        plan = release_plan(self.repo)
        self.assertEqual(plan['version'], '1.2.4')
        self.assertNotEqual(self.git('rev-parse', 'v1.2.4'), plan['commit'])

    def test_shallow_history_is_rejected(self):
        self.commit("fix: later change")
        shallow = self.root / "shallow"
        self.git("clone", "--depth=1", self.repo.as_uri(), str(shallow))
        with self.assertRaisesRegex(ReleasePolicyError, "Full Git history"):
            release_plan(shallow)

    def test_cli_json_github_outputs_and_precise_stamping(self):
        self.git("tag", "v1.2.3")
        self.commit("feat: CLI validation")
        module = self.repo / "colourlab" / "__init__.py"
        before = module.read_bytes()
        commit_before = self.git("rev-parse", "HEAD")
        tags_before = self.git("tag", "--list")
        output = self.root / "build" / "release-plan.json"
        github_output = self.root / "github-output.txt"
        github_output.write_text("previous=value\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), "--output", str(output),
             "--stamp", "--github-output", str(github_output)],
            env=self.env, text=True, encoding="utf-8", capture_output=True, check=True,
        )
        plan = json.loads(result.stdout)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), plan)
        self.assertEqual(plan["version"], "1.3.0")
        self.assertEqual(plan["commit"], commit_before)
        self.assertEqual(module.read_bytes(), before.replace(b'"0.2.1"', b'"1.3.0"'))
        self.assertEqual(self.git("rev-parse", "HEAD"), commit_before)
        self.assertEqual(self.git("tag", "--list"), tags_before)
        self.assertEqual(dict(line.split("=", 1) for line in github_output.read_text().splitlines()), {
            "previous": "value", "version": "1.3.0", "tag": "v1.3.0", "commit": commit_before,
            "base_tag": "v1.2.3", "bump": "minor", "release": "true", "already_tagged": "false",
        })

    def test_cli_without_stamp_preserves_source_and_serializes_no_base(self):
        module = self.repo / "colourlab" / "__init__.py"
        before = module.read_bytes()
        output = self.root / "plan.json"
        github_output = self.root / "github-output.txt"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), "--output", str(output),
             "--github-output", str(github_output)],
            env=self.env, text=True, encoding="utf-8", capture_output=True, check=True,
        )
        self.assertIsNone(json.loads(result.stdout)["base_tag"])
        self.assertIn("base_tag=\n", github_output.read_text())
        self.assertIn("release=false\n", github_output.read_text())
        self.assertEqual(module.read_bytes(), before)

    def test_repeated_first_release_stamping_uses_committed_seed(self):
        self.commit("fix: first release")
        module = self.repo / "colourlab" / "__init__.py"
        before = module.read_bytes().replace(b'"0.2.1"', b'"7.8.9"').replace(
            b'OTHER = "unchanged"', b'OTHER = "local edit"'
        )
        module.write_bytes(before)
        command = [sys.executable, str(SCRIPT), "--repo", str(self.repo), "--output",
                   str(self.root / "plan.json"), "--stamp"]
        first = subprocess.run(command, env=self.env, text=True, encoding="utf-8",
                               capture_output=True, check=True)
        first_plan = json.loads(first.stdout)
        self.assertEqual(first_plan["version"], "0.2.2")
        self.assertEqual(module.read_bytes(), before.replace(b'"7.8.9"', b'"0.2.2"'))
        first_source = module.read_bytes()
        second = subprocess.run(command, env=self.env, text=True, encoding="utf-8",
                                capture_output=True, check=True)
        self.assertEqual(json.loads(second.stdout), first_plan)
        self.assertEqual(module.read_bytes(), first_source)


if __name__ == "__main__":
    unittest.main()
