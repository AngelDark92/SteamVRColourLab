"""Workload lifecycle and byte accounting, without contacting a headset."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

from colourlab.bitrate import BitrateTest, analyse_case, export_case, parse_probe_line
from colourlab.bitrate_probe import HeadsetProbe, HostEncoderTarget
from colourlab.core import Settings
from tests.test_portable import TemporaryApplicationTests


def log_row(seconds, event, **fields):
    values = dict(event=event, monotonic_ns=int(seconds * 1e9), stream=1, **fields)
    return f"{seconds:.3f} 42 43 I GXRStreamProbe: " + " ".join(f"{k}={v}" for k, v in values.items())


def capture():
    base = dict(receives=100, received_bytes=1000, attempts=100, accepted=100,
                accepted_bytes=1000, outputs=100, released=100, render_released=100)
    final = dict(receives=101, received_bytes=1100, attempts=102, accepted=102,
                 accepted_bytes=1200, outputs=101, released=101, render_released=101)
    return ["0.000 42 43 I GXRTestPhase: round=500 mode=motion edge=start case=test",
            log_row(4, "totals", **base),
            log_row(6, "receive", generation=2, au=101, transport_id=100, size=100, codec_config=0, duplicate_id=0, wire="AV1"),
            log_row(6.01, "queue", transport_id=100, size=100, accepted=1, codec_config=0),
            log_row(6.02, "queue", transport_id=100, size=100, accepted=1, codec_config=0),
            log_row(6.03, "output", transport_id=100),
            log_row(6.04, "release", transport_id=100, status=0, render=1),
            log_row(19, "totals", **final),
            "20.000 42 43 I GXRTestPhase: round=500 mode=motion edge=end case=test"]


class WorkloadTests(unittest.TestCase):
    def test_waits_for_first_scene_submission_and_marks_focus_loss(self):
        test = BitrateTest()
        test.begin(Settings())
        self.assertEqual(test.tick(100, False), (False, False))
        self.assertIsNone(test.started)
        self.assertEqual(test.tick(200, True), (True, False))
        self.assertEqual(test.elapsed, 0)
        self.assertEqual(test.tick(210, False), (False, False))
        self.assertTrue(test.interrupted)
        self.assertEqual(test.tick(245, True), (False, True))

    def test_rejects_nonfinite_duration_fractional_target_and_live_config_edits(self):
        test = BitrateTest()
        for field, value in (("duration", float("nan")), ("duration", 0), ("target", 500.5),
                             ("target", float("inf")), ("serial", "x; shell command")):
            with self.assertRaises(ValueError):
                test.configure(field, value)
        test.configure("target", 600.0)
        self.assertEqual(test.target, 600)
        test.begin(Settings())
        with self.assertRaises(ValueError):
            test.configure("scene", "noise")


class WorkloadApplicationTests(TemporaryApplicationTests):
    def test_start_hides_menu_and_stop_restores_source_without_changing_stream_notes(self):
        self.app.args.desktop = False
        self.app.dashboard = Mock()
        original = replace(self.app.settings, mode="10bit", labels=True, bitrate_mbps="unchanged", panel_width=.2)
        self.app.change(original, "test")
        self.app.bitrate.configure("scene", "noise")
        self.app.start_bitrate()
        self.assertEqual(self.app.settings.pattern, "bitrate_noise")
        self.assertTrue(self.app.settings.animate)
        self.app.dashboard.set_expanded.assert_called_with(False)
        self.app.stop_bitrate()
        self.assertEqual(self.app.settings, original)
        self.assertTrue(list(self.app.run_dir.glob("bitrate-workload-*.json")))

    def test_source_edit_ends_test_and_preserves_the_new_choice(self):
        self.app.start_bitrate()
        self.app.change(replace(self.app.settings, mode="8bit"), "source edit")
        self.assertFalse(self.app.bitrate.running)
        self.assertEqual(self.app.settings.mode, "8bit")
        self.assertEqual(self.app.settings.pattern, "horizontal")

    def test_target_configuration_never_edits_stream_settings(self):
        original = self.app.settings.to_dict()
        self.app.bitrate.configure("target", 600)
        self.assertEqual(self.app.settings.to_dict(), original)
        self.assertIsNone(self.app.encoder_target.snapshot())


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "headset.log"
        self.path.write_text("\n".join(capture()), encoding="utf-8")

    def test_counter_deltas_work_when_attaching_midstream_and_count_duplicate_queues(self):
        result, frames, buckets = analyse_case(self.path, "test")
        self.assertTrue(result["telemetry_complete"])
        self.assertEqual(result["seconds"], 13)
        self.assertAlmostEqual(result["received_video_mbps"], 800 / 13 / 1e6)
        self.assertAlmostEqual(result["accepted_video_mbps"], 1600 / 13 / 1e6)
        self.assertEqual(frames[0]["accepted_queue_count"], 2)
        self.assertTrue(buckets)

    def test_lost_output_log_is_not_reported_as_complete_telemetry(self):
        self.path.write_text("\n".join(line for line in capture() if "event=output " not in line), encoding="utf-8")
        result, frames, _ = analyse_case(self.path, "test")
        self.assertFalse(result["telemetry_complete"])
        self.assertEqual(result["accepted_ids_without_output"], [100])
        self.assertEqual(frames[0]["output_monotonic_ns"], "")

    def test_no_probe_data_does_not_invent_bitrate(self):
        self.path.write_text("\n".join(line for line in capture() if "event=receive " not in line), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "No diagnostic"):
            analyse_case(self.path, "test")

    def test_exports_real_byte_counts_and_distinct_rate_windows(self):
        output = self.root / "result"
        result = export_case(self.path, output, "test", {"interrupted": False})
        self.assertEqual(json.loads((output / "summary.json").read_text())["received_video_mbps"], result["received_video_mbps"])
        self.assertIn("received_bytes", (output / "frames.csv").read_text())
        self.assertIn("1000,", (output / "bitrate-windows.csv").read_text())

    def test_headset_rate_uses_monotonic_clock_and_expires_on_disconnect(self):
        probe = HeadsetProbe(self.root)
        probe.connected = True
        for i in range(91):
            probe.feed(dict(event="receive", pid=1, stream=1, transport_id=i,
                            monotonic_ns=10_000_000_000 + i * 1_000_000_000 // 90,
                            size=1000, wire="AV1"), now=100)
        snapshot = probe.snapshot(now=100)
        self.assertAlmostEqual(snapshot["received_mbps"], .72)
        self.assertEqual(snapshot["received_aus_per_second"], 90)
        self.assertIsNone(probe.snapshot(now=103)["received_mbps"])
        probe.connected = False
        self.assertIsNone(probe.snapshot(now=100)["received_mbps"])

    def test_probe_parser_keeps_sha_as_text_and_never_uses_transport_id_as_clock(self):
        r = parse_probe_line("1.000 42 43 I GXRStreamProbe: event=capture monotonic_ns=1000000000 stream=1 transport_id=90 sha256=012345")
        self.assertEqual(r["sha256"], "012345")
        self.assertEqual(r["monotonic_ns"], 1_000_000_000)
        self.assertIsNone(parse_probe_line("1.000 42 43 I GXRStreamProbe: event=receive monotonic_ns=1000000000 stream=1 size=truncated"))

    def test_host_target_skips_stale_history_and_reassembles_partial_lines(self):
        path = self.root / "vrserver.txt"
        path.write_text("NvencTap: heartbeat api=12 enabled=1 1x1 avg=500M\n")
        host = HostEncoderTarget(path)
        host.poll()
        self.assertIsNone(host.snapshot())
        with path.open("a") as out:
            out.write("NvencTap: heartbeat api=12 enabled=1 1x1 avg=326")
        host.poll()
        self.assertIsNone(host.snapshot())
        with path.open("a") as out:
            out.write("M max=326M\n")
        host.poll()
        self.assertEqual(host.snapshot(), 326)

    def test_unauthorized_or_ambiguous_devices_never_start_logcat(self):
        for listing in ("List of devices attached\nA unauthorized\n", "List of devices attached\nA device\nB device\n"):
            probe = HeadsetProbe(self.root)
            with patch("colourlab.bitrate_probe.find_adb", return_value="adb"), \
                 patch("colourlab.bitrate_probe.subprocess.run", return_value=SimpleNamespace(stdout=listing)), \
                 patch("colourlab.bitrate_probe.subprocess.Popen") as spawn:
                probe._read("", usb_only=False)
            spawn.assert_not_called()
            self.assertFalse(probe.connected)
            self.assertIn("authorized headset", probe.status)

    def test_marker_is_a_bounded_log_command_without_install_or_process_changes(self):
        probe = HeadsetProbe(self.root)
        probe.adb, probe.serial = "adb", "headset"
        probe.commands.put(("start", "abc123", "noise", 600))
        def done(*args, **kwargs):
            probe.stop_event.set()
            return SimpleNamespace(returncode=0)
        with patch("colourlab.bitrate_probe.subprocess.run", side_effect=done) as run:
            probe._commands()
        self.assertEqual(run.call_args.args[0], ["adb", "-s", "headset", "shell", "log", "-t", "GXRTestPhase",
                         "round=600 mode=noise edge=start case=abc123"])
        self.assertEqual(run.call_args.kwargs["timeout"], 5)
        self.assertEqual(probe.commands.unfinished_tasks, 0)

