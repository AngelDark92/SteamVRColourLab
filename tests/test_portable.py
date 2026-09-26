"""Portable paths and report persistence; no graphics or SteamVR initialization."""
import argparse
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app as entry
from colourlab.core import Settings


class TemporaryApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.home_patch = patch.object(entry, "application_home", return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)
        # Keep unittest's logging handlers intact and avoid locking temporary
        # files on Windows. Application event/report files remain real.
        self.logging_patch = patch.object(entry.logging, "basicConfig")
        self.logging_patch.start()
        self.addCleanup(self.logging_patch.stop)
        args = argparse.Namespace(config=None, output=self.home / "runs",
                                  settings_dir=None, desktop=True)
        self.app = entry.Application(args)
        self.addCleanup(self.app.close)


class PortablePathTests(unittest.TestCase):
    def test_frozen_home_uses_executable_not_unpack_directory_or_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / "portable" / "SteamVRColourLab.exe"
            with patch.object(entry.sys, "frozen", True, create=True), \
                 patch.object(entry.sys, "executable", str(exe)), \
                 patch.object(entry.sys, "_MEIPASS", str(root / "unpacked"), create=True), \
                 patch.object(Path, "cwd", return_value=root / "elsewhere"):
                self.assertEqual(entry.application_home(), exe.parent.resolve())

    def test_source_home_uses_entry_script_not_python_executable(self):
        with patch.object(entry.sys, "frozen", False, create=True), \
             patch.object(entry.sys, "executable", "Z:/unrelated/python.exe"):
            self.assertEqual(entry.application_home(), Path(entry.__file__).resolve().parent)

    def test_zipapp_home_is_beside_archive_not_inside_it(self):
        archive = Path("C:/portable/SteamVRColourLab.pyz")
        with patch.object(entry.sys, "frozen", False, create=True), \
             patch.object(entry, "__loader__", SimpleNamespace(archive=str(archive))):
            self.assertEqual(entry.application_home(), archive.resolve().parent)

    def test_cli_defaults_resolve_under_portable_home(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = Mock()
            with patch.object(entry, "application_home", return_value=root), \
                 patch.object(entry, "Application", return_value=fake) as constructor:
                self.assertEqual(entry.main(["--desktop"]), 0)
            args = constructor.call_args.args[0]
            self.assertEqual(args.output, root / "runs")
            self.assertIsNone(args.settings_dir)
            fake.close.assert_called_once()


class PortablePersistenceTests(TemporaryApplicationTests):
    def test_snapshot_roundtrip_and_picker_stay_under_portable_home(self):
        wanted = replace(self.app.settings, start_rgb=(.0123456789012345, .2, .3),
                         codec="HEVC", notes="Portable snapshot")
        self.app.change(wanted, "test")
        snapshot = self.app.save_settings_snapshot()
        self.assertEqual(snapshot.parent, self.home / "settings")
        self.assertEqual(Settings.load(snapshot), wanted)
        self.assertIn(snapshot, self.app.settings_files())
        self.assertEqual(self.app.run_dir.parent, self.home / "runs")

    def test_explicit_settings_directory_is_honoured(self):
        args = argparse.Namespace(config=None, output=self.home / "other-runs",
                                  settings_dir=self.home / "custom-settings", desktop=True)
        other = entry.Application(args)
        self.addCleanup(other.close)
        self.assertEqual(other.save_settings_snapshot().parent, args.settings_dir)

    def test_report_records_live_state_without_applying_invalid_desktop_inputs(self):
        desktop = SimpleNamespace(apply=Mock(return_value=False),
                                  status=SimpleNamespace(set=Mock()), close=Mock())
        self.app.ui = desktop
        self.app.change(replace(self.app.settings, mode="10bit", notes="VR edit"), "test")
        self.app.save_report(apply_ui=False)
        desktop.apply.assert_not_called()
        reports = list(self.app.run_dir.glob("report-*.json"))
        self.assertEqual(len(reports), 1)
        data = json.loads(reports[0].read_text(encoding="utf-8"))
        self.assertEqual(data["settings"]["mode"], "10bit")
        self.assertEqual(data["settings"]["notes"], "VR edit")
        self.assertFalse(data["stream_depth_confirmed"])
        replay = list(self.app.run_dir.glob("settings-*.json"))
        self.assertEqual(len(replay), 1)
        self.assertEqual(Settings.load(replay[0]), self.app.settings)
        self.assertIn(replay[0], self.app.settings_files())


if __name__ == "__main__":
    unittest.main()
