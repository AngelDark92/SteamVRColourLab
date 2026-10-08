"""Portable ZIP validation and publication sequencing without remote writes."""

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import app
from colourlab import __version__
from tools import publish_release
from tools.verify_package import verify_archive


class ArtifactFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.artifacts = Path(self.temporary.name)
        self.plan = {
            "version": "1.3.0", "tag": "v1.3.0", "commit": "a" * 40,
            "base_tag": "v1.2.3", "bump": "minor", "release": True,
            "already_tagged": False,
        }
        (self.artifacts / "build").mkdir()
        (self.artifacts / "dist").mkdir()
        self.plan_path = self.artifacts / "build" / "release-plan.json"
        self.write_plan()
        self.archive = self.artifacts / "dist" / "SteamVRColourLab-Windows-x64.zip"
        self.checksum = self.archive.with_suffix(".zip.sha256")
        self.info = {"version": self.plan["version"], "source_commit": self.plan["commit"]}
        # These are structural fixtures, not runnable Windows executables.
        self.members = {
            "SteamVRColourLab.exe": b"fixture executable",
            "BUILD_INFO.json": json.dumps(self.info).encode("utf-8"),
            "LICENSE": b"fixture license",
            "THIRD_PARTY_NOTICES.md": b"fixture notices",
            "licenses/MANIFEST.json": b"{}",
            "licenses/CPython-LICENSE.txt": b"fixture Python license",
            "start_windows.bat": b"@SteamVRColourLab.exe\r\n",
            "_internal/python313.dll": b"fixture bundled runtime",
        }
        self.write_archive()

    def write_plan(self):
        self.plan_path.write_text(json.dumps(self.plan), encoding="utf-8")

    def write_archive(self, *, extra=None, omit=()):
        with zipfile.ZipFile(self.archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name, content in self.members.items():
                if name not in omit:
                    bundle.writestr("SteamVRColourLab/" + name, content)
            for name, content in (extra or {}).items():
                bundle.writestr(name, content)
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.checksum.write_text(f"{digest}  {self.archive.name}\n", encoding="ascii")


class ArchiveValidationTests(ArtifactFixture):
    def test_valid_archive_matches_exact_build(self):
        self.assertEqual(verify_archive(self.archive, self.plan), self.info)

    def test_corrupt_checksum_is_rejected(self):
        self.checksum.write_text(f"{'0' * 64}  {self.archive.name}\n", encoding="ascii")
        with self.assertRaisesRegex(ValueError, "checksum"):
            verify_archive(self.archive, self.plan)

    def test_wrong_recorded_filename_is_rejected(self):
        self.checksum.write_text(
            f"{hashlib.sha256(self.archive.read_bytes()).hexdigest()}  wrong.zip\n", encoding="ascii"
        )
        with self.assertRaisesRegex(ValueError, "filename"):
            verify_archive(self.archive, self.plan)

    def test_wrong_version_or_commit_is_rejected(self):
        for field, value in (("version", "1.3.1"), ("commit", "b" * 40)):
            with self.subTest(field=field):
                expected = dict(self.plan, **{field: value})
                with self.assertRaisesRegex(ValueError, "version/commit"):
                    verify_archive(self.archive, expected)

    def test_personal_state_and_python_cache_are_rejected(self):
        for path in ("runs/session.json", "settings/profile.json", "Settings/local.json",
                     "nested/RUNS/session.json", "__pycache__/module.pyc"):
            with self.subTest(path=path):
                self.write_archive(extra={"SteamVRColourLab/" + path: b"private"})
                with self.assertRaisesRegex(ValueError, "Personal or source-only data"):
                    verify_archive(self.archive, self.plan)

    def test_path_traversal_or_wrong_root_is_rejected(self):
        for path in ("SteamVRColourLab/../escape.txt", "SteamVRColourLab/nested/../../escape.txt",
                     "SteamVRColourLab/nested\\..\\escape.txt", "../escape.txt",
                     "SteamVRColourLab/C:/escape.txt", "unrelated/file.txt"):
            with self.subTest(path=path):
                self.write_archive(extra={path: b"unsafe"})
                with self.assertRaisesRegex(ValueError, "Unsafe package path"):
                    verify_archive(self.archive, self.plan)

    def test_missing_runtime_is_rejected(self):
        self.write_archive(omit=("_internal/python313.dll",))
        with self.assertRaisesRegex(ValueError, "Incomplete portable archive"):
            verify_archive(self.archive, self.plan)

    def test_missing_license_is_rejected(self):
        self.write_archive(omit=("licenses/CPython-LICENSE.txt",))
        with self.assertRaisesRegex(ValueError, "Incomplete portable archive"):
            verify_archive(self.archive, self.plan)


class VersionOptionTests(unittest.TestCase):
    def test_version_exits_successfully_without_initializing_application(self):
        output = io.StringIO()
        with patch.object(app, "Application") as application, redirect_stdout(output):
            with self.assertRaises(SystemExit) as result:
                app.main(["--version"])
        self.assertEqual(result.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), __version__)
        application.assert_not_called()


class PublishReleaseTests(ArtifactFixture):
    def setUp(self):
        super().setUp()
        self.commands = []
        self.head = self.plan["commit"]
        self.tag_commit = self.plan["commit"]
        self.fresh_plan = dict(self.plan)
        self.known_tags = [self.plan["base_tag"]]
        self.release_pages = [[]]
        self.fail_upload = False

    def command(self, *args):
        """Model command responses; reject any unexpected operation."""
        self.commands.append(args)
        tag = self.plan["tag"]
        if args == ("git", "rev-parse", "HEAD"):
            return self.head
        if args == ("git", "fetch", "origin", "--tags"):
            return ""
        if args == (sys.executable, "tools/release_policy.py", "--output", str(self.artifacts / "build/publish-plan.json")):
            return json.dumps(self.fresh_plan)
        if args == ("git", "tag", "--list", "v*"):
            return "\n".join(self.known_tags)
        if args == ("git", "rev-parse", f"{tag}^{{commit}}"):
            return self.tag_commit
        if args == ("git", "tag", tag, self.plan["commit"]):
            return ""
        if args == ("git", "push", "origin", f"refs/tags/{tag}"):
            return ""
        if args == ("gh", "api", "--paginate", "--slurp",
                    "repos/{owner}/{repo}/releases?per_page=100"):
            return json.dumps(self.release_pages)
        revision = f"{self.plan['base_tag']}..{self.plan['commit']}"
        if args == ("git", "log", "--format=- %s (%h)", revision):
            return "- feat: portable release (aaaaaaa)"
        if args == ("gh", "release", "create", tag, "--verify-tag", "--draft", "--title", tag,
                    "--notes-file", str(self.artifacts / "release-notes.md")):
            return ""
        if args == self.upload_command():
            if self.fail_upload:
                raise subprocess.CalledProcessError(1, args)
            return ""
        if args == self.publish_command():
            return ""
        raise AssertionError(f"Unexpected command: {args!r}")

    def upload_command(self):
        return ("gh", "release", "upload", self.plan["tag"], str(self.archive),
                str(self.checksum), "--clobber")

    def publish_command(self):
        return ("gh", "release", "edit", self.plan["tag"], "--draft=false", "--latest")

    def publish(self):
        with patch.object(publish_release, "run", side_effect=self.command), redirect_stdout(io.StringIO()):
            publish_release.publish(self.artifacts)

    def assert_no_remote_mutations(self):
        self.assertFalse(any(args[:2] == ("git", "push") or args[:2] == ("gh", "release")
                             for args in self.commands), self.commands)

    def test_new_release_tags_exact_commit_and_uploads_before_publication(self):
        self.publish()
        tag_command = ("git", "tag", self.plan["tag"], self.plan["commit"])
        push_command = ("git", "push", "origin", "refs/tags/" + self.plan["tag"])
        create = next(args for args in self.commands if args[:3] == ("gh", "release", "create"))
        self.assertLess(self.commands.index(tag_command), self.commands.index(push_command))
        self.assertLess(self.commands.index(push_command), self.commands.index(create))
        self.assertIn("--draft", create)
        self.assertIn("--verify-tag", create)
        self.assertLess(self.commands.index(create), self.commands.index(self.upload_command()))
        self.assertLess(self.commands.index(self.upload_command()), self.commands.index(self.publish_command()))
        notes = (self.artifacts / "release-notes.md").read_text(encoding="utf-8")
        self.assertIn(self.plan["commit"], notes)
        self.assertIn("feat: portable release", notes)

    def test_published_rerun_preserves_existing_assets_and_tag(self):
        self.known_tags.append(self.plan["tag"])
        self.release_pages = [[], [{"tag_name": self.plan["tag"], "draft": False}]]
        self.publish()
        self.assert_no_remote_mutations()
        self.assertNotIn(("git", "tag", self.plan["tag"], self.plan["commit"]), self.commands)
        self.assertFalse((self.artifacts / "release-notes.md").exists())

    def test_existing_draft_retries_upload_then_publishes(self):
        self.known_tags.append(self.plan["tag"])
        self.release_pages = [[{"tag_name": self.plan["tag"], "draft": True}]]
        self.publish()
        self.assertFalse(any(args[:3] == ("gh", "release", "create") for args in self.commands))
        self.assertLess(self.commands.index(self.upload_command()), self.commands.index(self.publish_command()))
        self.assertFalse(any(args[:2] == ("git", "push") for args in self.commands))

    def test_failed_upload_does_not_publish_draft(self):
        self.fail_upload = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.publish()
        self.assertIn(self.upload_command(), self.commands)
        self.assertNotIn(self.publish_command(), self.commands)

    def test_head_mismatch_stops_before_tag_refresh_or_mutation(self):
        self.head = "b" * 40
        with self.assertRaisesRegex(ValueError, "another commit"):
            self.publish()
        self.assertEqual(self.commands, [("git", "rev-parse", "HEAD")])

    def test_conflicting_tag_is_rejected_without_remote_mutation(self):
        self.known_tags.append(self.plan["tag"])
        self.tag_commit = "b" * 40
        with self.assertRaisesRegex(ValueError, "tag already belongs"):
            self.publish()
        self.assert_no_remote_mutations()

    def test_newer_tag_blocks_stale_publication(self):
        self.known_tags.extend([self.plan["tag"], "v1.10.0"])
        with self.assertRaisesRegex(ValueError, "newer version"):
            self.publish()
        self.assert_no_remote_mutations()

    def test_changed_release_plan_blocks_publication(self):
        self.fresh_plan["version"] = "1.4.0"
        with self.assertRaisesRegex(ValueError, "changed during the build"):
            self.publish()
        self.assert_no_remote_mutations()

    def test_non_release_plan_runs_no_commands(self):
        self.plan["release"] = False
        self.write_plan()
        with self.assertRaisesRegex(ValueError, "does not request a release"):
            self.publish()
        self.assertEqual(self.commands, [])

    def test_invalid_artifact_runs_no_commands(self):
        self.checksum.write_text("bad checksum", encoding="ascii")
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.publish()
        self.assertEqual(self.commands, [])


if __name__ == "__main__":
    unittest.main()
