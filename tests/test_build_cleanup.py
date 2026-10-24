"""Exercise real PowerShell cleanup on disposable directories, never build outputs."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile


POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")
HELPER = Path(__file__).resolve().parents[1] / "tools" / "Portable-Cleanup.ps1"


def powershell_environment():
    environment = dict(os.environ)
    # A PowerShell 7 parent can otherwise hide Windows PowerShell's built-in modules.
    environment.pop("PSModulePath", None)
    return environment


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows PowerShell required")
class PortableCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="colourlab-cleanup-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / "build" / "portable"
        self.dist = self.root / "dist"
        self.staging = self.build / "staging-20260926-120000-001"
        self.previous = self.build / "previous-20260926-120000-001"
        self.package = self.dist / "SteamVRColourLab"
        self.zip = self.dist / "SteamVRColourLab-Windows-x64.zip"
        self.checksum = Path(str(self.zip) + ".sha256")
        for path in (self.staging, self.previous, self.package):
            path.mkdir(parents=True)
        self.write(self.staging / "work" / "scratch.bin", b"temporary")
        self.write(self.package / "SteamVRColourLab.exe", b"new executable")
        self.write(self.root / "source.py", b"source sentinel")

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def archive(self, entries):
        with zipfile.ZipFile(self.zip, "w") as archive:
            for name, value in entries.items():
                archive.writestr(name, value)
        self.checksum.write_text(
            f"{hashlib.sha256(self.zip.read_bytes()).hexdigest()}  {self.zip.name}\n",
            encoding="ascii",
        )

    def run_cleanup(self, **overrides):
        config = {
            "Staging": str(self.staging), "PreviousPackage": str(self.previous),
            "PackagePath": str(self.package), "BuildRoot": str(self.build),
            "DistRoot": str(self.dist), "ZipPath": str(self.zip),
            "HashPath": str(self.checksum), "Helper": str(HELPER),
        }
        config.update(overrides)
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        script = self.root / "invoke.ps1"
        script.write_text("""param([string]$ConfigPath)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$config = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
. $config.Helper
$manifest = Get-PortableArchiveManifest -ZipPath $config.ZipPath -HashPath $config.HashPath
$result = Clear-PortableBuildFiles -Staging $config.Staging -PreviousPackage $config.PreviousPackage -PackagePath $config.PackagePath -BuildRoot $config.BuildRoot -DistRoot $config.DistRoot -PreviousManifest $manifest
Write-Output ('RESULT:' + ($result | ConvertTo-Json -Compress))
""", encoding="utf-8")
        completed = subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(script), "-ConfigPath", str(config_path)],
            capture_output=True, text=True, timeout=60, env=powershell_environment(),
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        results = [line[7:] for line in completed.stdout.splitlines() if line.startswith("RESULT:")]
        self.assertEqual(len(results), 1, completed.stdout + completed.stderr)
        self.assertEqual((self.package / "SteamVRColourLab.exe").read_bytes(), b"new executable")
        self.assertEqual((self.root / "source.py").read_bytes(), b"source sentinel")
        return json.loads(results[0])

    def test_success_removes_verified_old_output_and_restored_user_files(self):
        self.archive({"SteamVRColourLab/SteamVRColourLab.exe": b"old executable"})
        self.write(self.previous / "SteamVRColourLab.exe", b"old executable")
        for folder in ("runs", "settings"):
            for root in (self.previous, self.package):
                self.write(root / folder / "nested" / "user.json", b"user content")
        result = self.run_cleanup()
        self.assertTrue(result["CleanupSucceeded"])
        self.assertIsNone(result["RetainedPrevious"])
        self.assertEqual(result["RemovedFiles"], 4)
        self.assertEqual(result["RemovedBytes"], len(b"temporaryold executableuser contentuser content"))
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())
        self.assertTrue((self.package / "settings/nested/user.json").is_file())

    def test_unknown_modified_and_unrestored_files_survive(self):
        self.archive({"SteamVRColourLab/known.txt": b"original", "SteamVRColourLab/remove.txt": b"same",
                      "SteamVRColourLab/settings/local.json": b"unrestored"})
        retained = {"known.txt": b"modified", "custom.txt": b"unknown",
                    "settings/local.json": b"unrestored", "runs/session.txt": b"different"}
        for name, value in retained.items():
            self.write(self.previous / name, value)
        self.write(self.previous / "remove.txt", b"same")
        self.write(self.package / "runs/session.txt", b"new session")
        result = self.run_cleanup()
        self.assertTrue(result["CleanupSucceeded"])
        self.assertEqual(result["RetainedPrevious"], str(self.previous))
        for name, value in retained.items():
            self.assertEqual((self.previous / name).read_bytes(), value)
        self.assertFalse((self.previous / "remove.txt").exists())

    def test_no_manifest_preserves_output_but_deduplicates_restored_data(self):
        self.write(self.previous / "unknown.exe", b"keep")
        for root in (self.previous, self.package):
            self.write(root / "settings/user.json", b"same")
        self.assertTrue(self.run_cleanup()["CleanupSucceeded"])
        self.assertTrue((self.previous / "unknown.exe").exists())
        self.assertFalse((self.previous / "settings/user.json").exists())

    def test_invalid_archive_authority_keeps_old_files(self):
        for mode in ("missing_checksum", "wrong_hash", "wrong_filename", "invalid_zip", "unsafe_entry", "duplicate"):
            with self.subTest(mode=mode):
                self.staging.mkdir(exist_ok=True)
                self.archive({"SteamVRColourLab/known.txt": b"keep"})
                self.write(self.previous / "known.txt", b"keep")
                if mode == "missing_checksum":
                    self.checksum.unlink()
                elif mode == "wrong_hash":
                    self.checksum.write_text("0" * 64 + "  " + self.zip.name)
                elif mode == "wrong_filename":
                    self.checksum.write_text(hashlib.sha256(self.zip.read_bytes()).hexdigest() + "  other.zip")
                elif mode == "invalid_zip":
                    self.zip.write_bytes(b"not a zip")
                    self.checksum.write_text(hashlib.sha256(self.zip.read_bytes()).hexdigest() + "  " + self.zip.name)
                elif mode == "unsafe_entry":
                    self.archive({"SteamVRColourLab/known.txt": b"keep", "SteamVRColourLab/../source.py": b"source"})
                else:
                    self.archive({"SteamVRColourLab/known.txt": b"keep", "SteamVRColourLab/KNOWN.txt": b"keep"})
                self.assertTrue(self.run_cleanup()["CleanupSucceeded"])
                self.assertEqual((self.previous / "known.txt").read_bytes(), b"keep")

    def test_outside_root_and_unexpected_name_refused_before_deletion(self):
        for target in (self.root / "staging-20260926-120000-001", self.build / "venv-3.14.0-x64", self.build):
            with self.subTest(target=target):
                target.mkdir(exist_ok=True)
                self.write(target / "sentinel", b"keep")
                result = self.run_cleanup(Staging=str(target))
                self.assertFalse(result["CleanupSucceeded"])
                self.assertTrue((target / "sentinel").exists())
                self.assertTrue((self.staging / "work/scratch.bin").exists())

    def test_protected_metadata_in_either_candidate_refuses_all_cleanup(self):
        for root in (self.staging, self.previous):
            for name in (".git", ".github", ".codex", ".agents"):
                with self.subTest(root=root, name=name):
                    marker = root / "nested" / name
                    self.write(marker, b"protected")
                    self.assertFalse(self.run_cleanup()["CleanupSucceeded"])
                    self.assertTrue(marker.exists())
                    self.assertTrue((self.staging / "work/scratch.bin").exists())
                    marker.unlink()

    def test_junction_in_candidates_or_destination_refuses_all_cleanup(self):
        external = self.root / "external"
        external.mkdir()
        self.write(external / "sentinel", b"keep")
        for root in (self.staging, self.previous, self.package):
            with self.subTest(root=root):
                link = root / "redirect"
                script = self.root / "junction.ps1"
                script.write_text("param([string]$Link, [string]$Target)\nNew-Item -ItemType Junction -Path $Link -Target $Target | Out-Null", encoding="utf-8")
                completed = subprocess.run(
                    [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Link", str(link), "-Target", str(external)],
                    capture_output=True, text=True, env=powershell_environment(),
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                try:
                    self.assertFalse(self.run_cleanup()["CleanupSucceeded"])
                    self.assertTrue((self.staging / "work/scratch.bin").exists())
                    self.assertEqual((external / "sentinel").read_bytes(), b"keep")
                finally:
                    os.rmdir(link)

    def test_only_current_invocation_paths_are_removed(self):
        for name in ("staging-20260925-120000-001", "previous-20260925-120000-001", "venv-3.14-x64", "license-cache"):
            self.write(self.build / name / "sentinel", b"keep")
        result = self.run_cleanup(PreviousPackage=None)
        self.assertTrue(result["CleanupSucceeded"])
        for name in ("staging-20260925-120000-001", "previous-20260925-120000-001", "venv-3.14-x64", "license-cache"):
            self.assertEqual((self.build / name / "sentinel").read_bytes(), b"keep")


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows PowerShell required")
class StalePortableCleanupTests(unittest.TestCase):
    """Exercise the age-based pruner against disposable external output roots."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="colourlab-stale-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "output"
        self.build = self.output / "build" / "portable"
        self.package = self.output / "dist" / "SteamVRColourLab"
        self.current_env = "venv-3.14.0-x64"
        self.build.mkdir(parents=True)
        self.write(self.package / "runs" / "session.txt", b"current session")
        self.write(self.build / "license-cache" / "license.txt", b"cache")
        self.write(self.build / "last-cleanup.json", b"{}")
        self.old_staging = self.build / "staging-20260101-010101-001"
        self.old_previous = self.build / "previous-20260101-010101-001"
        self.new_previous = self.build / "previous-20260102-010101-001"
        self.relocated = self.build / "relocated-check"
        self.old_venv = self.build / "venv-3.13.15-x64"
        self.current_venv = self.build / self.current_env

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    @staticmethod
    def make_old(path, days=30):
        timestamp = __import__("time").time() - days * 86400
        for file in sorted(path.rglob("*"), reverse=True):
            os.utime(file, (timestamp, timestamp))
        os.utime(path, (timestamp, timestamp))

    def populate(self):
        self.write(self.old_staging / "work" / "scratch.bin", b"staging")
        self.write(self.old_previous / "SteamVRColourLab.exe", b"old executable")
        self.write(self.new_previous / "SteamVRColourLab.exe", b"newer executable")
        self.write(self.new_previous / "runs" / "session.txt", b"current session")
        self.write(self.relocated / "SteamVRColourLab" / "SteamVRColourLab.exe", b"legacy")
        self.write(self.old_venv / "Scripts" / "python.exe", b"old python")
        self.write(self.current_venv / "Scripts" / "python.exe", b"current python")
        for path in (self.old_staging, self.old_previous, self.new_previous, self.relocated,
                     self.old_venv, self.current_venv):
            self.make_old(path)

    def run_prune(self, *, apply=False, keep_days=0, keep_previous=1):
        config = {
            "BuildRoot": str(self.build), "PackagePath": str(self.package),
            "CurrentEnvironment": self.current_env, "KeepDays": keep_days,
            "KeepPrevious": keep_previous, "Apply": apply,
        }
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        script = self.root / "invoke-prune.ps1"
        script.write_text("""param([string]$ConfigPath)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$config = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
. $env:CLEANUP_HELPER
$result = Clear-StalePortableBuildFiles -BuildRoot $config.BuildRoot -PackagePath $config.PackagePath `
    -CurrentEnvironment $config.CurrentEnvironment -KeepDays $config.KeepDays `
    -KeepPrevious $config.KeepPrevious -Apply:$config.Apply
Write-Output ('RESULT:' + ($result | ConvertTo-Json -Compress -Depth 5))
""", encoding="utf-8")
        environment = powershell_environment()
        environment["CLEANUP_HELPER"] = str(HELPER)
        completed = subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(script), "-ConfigPath", str(config_path)],
            capture_output=True, text=True, timeout=60, env=environment,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        results = [line[7:] for line in completed.stdout.splitlines() if line.startswith("RESULT:")]
        self.assertEqual(len(results), 1, completed.stdout + completed.stderr)
        return json.loads(results[0])

    def test_preview_lists_stale_and_deletes_nothing(self):
        self.populate()
        result = self.run_prune(apply=False, keep_days=0, keep_previous=1)
        paths = {Path(item["Path"]).name for item in result["Candidates"]}
        self.assertEqual(paths, {
            self.old_staging.name, self.old_previous.name, self.relocated.name, self.old_venv.name,
        })
        self.assertFalse(result["Applied"])
        for path in (self.old_staging, self.old_previous, self.relocated, self.old_venv):
            self.assertTrue(path.exists())

    def test_apply_removes_stale_and_keeps_recovery_current_env_and_user_data(self):
        self.populate()
        result = self.run_prune(apply=True, keep_days=0, keep_previous=1)
        self.assertTrue(result["Applied"])
        self.assertGreater(result["RemovedBytes"], 0)
        self.assertEqual(len(result["Removed"]), 4)
        self.assertFalse(self.old_staging.exists())
        self.assertFalse(self.old_previous.exists())
        self.assertFalse(self.relocated.exists())
        self.assertFalse(self.old_venv.exists())
        self.assertTrue(self.new_previous.exists())
        self.assertTrue(self.current_venv.exists())
        self.assertTrue((self.build / "license-cache" / "license.txt").is_file())
        self.assertTrue((self.build / "last-cleanup.json").is_file())
        self.assertEqual((self.package / "runs" / "session.txt").read_bytes(), b"current session")

    def test_unique_previous_user_data_is_refused(self):
        self.populate()
        self.write(self.old_previous / "runs" / "unique.txt", b"must survive")
        result = self.run_prune(apply=True, keep_days=0, keep_previous=1)
        self.assertTrue(self.old_previous.exists())
        refused = {Path(item["Path"]).name: item["Reason"] for item in result["Refused"]}
        self.assertIn(self.old_previous.name, refused)
        self.assertIn("not already preserved", refused[self.old_previous.name])
        self.assertFalse(self.old_staging.exists())

    def test_nested_legacy_user_data_is_refused(self):
        self.populate()
        self.write(self.relocated / "SteamVRColourLab" / "runs" / "old.txt", b"legacy run")
        result = self.run_prune(apply=True, keep_days=0, keep_previous=1)
        self.assertTrue(self.relocated.exists())
        refused = {Path(item["Path"]).name: item["Reason"] for item in result["Refused"]}
        self.assertIn(self.relocated.name, refused)
        self.assertIn("user data", refused[self.relocated.name].lower())

    def test_unexpected_names_and_recent_staging_are_kept(self):
        self.populate()
        self.write(self.build / "manual-notes" / "note.txt", b"keep")
        recent = self.build / "staging-20261024-120000-001"
        self.write(recent / "work" / "scratch.bin", b"recent")
        result = self.run_prune(apply=True, keep_days=7, keep_previous=1)
        names = {Path(item["Path"]).name for item in result["Candidates"]}
        self.assertNotIn("manual-notes", names)
        self.assertNotIn(recent.name, names)
        self.assertTrue((self.build / "manual-notes" / "note.txt").is_file())
        self.assertTrue(recent.exists())

    def test_junction_is_refused(self):
        self.populate()
        external = self.root / "external"
        self.write(external / "sentinel.txt", b"keep")
        link = self.old_staging / "redirect"
        script = self.root / "junction.ps1"
        script.write_text("param([string]$Link, [string]$Target)\nNew-Item -ItemType Junction -Path $Link -Target $Target | Out-Null", encoding="utf-8")
        completed = subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(script), "-Link", str(link), "-Target", str(external)],
            capture_output=True, text=True, env=powershell_environment(),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        try:
            result = self.run_prune(apply=True, keep_days=0, keep_previous=1)
            self.assertTrue(self.old_staging.exists())
            self.assertEqual((external / "sentinel.txt").read_bytes(), b"keep")
            refused = {Path(item["Path"]).name: item["Reason"] for item in result["Refused"]}
            self.assertIn(self.old_staging.name, refused)
        finally:
            os.rmdir(link)


if __name__ == "__main__":
    unittest.main()
