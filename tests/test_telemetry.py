"""Stage-specific measurements and fresh byte evidence, with no device access."""
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from colourlab.bitrate_probe import HeadsetProbe, HostEncoderTarget
from colourlab.headset_diagnostics import CAPTURE_FILE, HeadsetDiagnostics, parse_decoder_line
from colourlab.telemetry import SessionTelemetry, thermal_readings
from tests.test_codec_verify import AV1
from tests.test_portable import TemporaryApplicationTests


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_recorder_uses_real_window_and_never_calls_submissions_received_fps(self):
        recorder = SessionTelemetry(self.root)
        self.addCleanup(recorder.close)
        host = dict(target_mbps=500, encode_latency_mean_ms=4)
        headset = dict(connected=False, status="disconnected")
        for now in (10, 10.5, 11.5):
            recorder.tick(now, True, False, host, headset)
        row = recorder.latest
        self.assertAlmostEqual(row["scene_submissions_fps"], 2 / 1.5)
        self.assertEqual(row["host_encoder_target_mbps"], 500)
        self.assertIsNone(row["host_sent_payload_mbps"])
        self.assertIsNone(row["headset_decoder_output_fps"])
        self.assertEqual(len((recorder.directory / "samples.jsonl").read_text().splitlines()), 1)
        with (recorder.directory / "samples.csv").open(newline="") as source:
            saved = list(csv.DictReader(source))
        self.assertEqual(saved[0]["headset_decoder_input_mbps"], "")
        self.assertEqual(saved[0]["host_encoder_target_mbps"], "500")

    def test_desktop_preview_has_no_vr_fps_even_when_frames_render(self):
        recorder = SessionTelemetry(self.root)
        self.addCleanup(recorder.close)
        recorder.tick(10, True, True, {}, {})
        recorder.tick(11, True, True, {}, {})
        self.assertIsNone(recorder.latest["scene_submissions_fps"])
        self.assertEqual(recorder.latest["mode"], "desktop_preview")

    def test_thermal_units_current_section_and_missing_values(self):
        thermal = """Thermal Status: 2
Cached temperatures:
Temperature{mValue=99.0, mType=0, mName=old, mStatus=4}
Current temperatures from HAL:
Temperature{mValue=43.5, mType=3, mName=skin, mStatus=2}
Temperature{mValue=NaN, mType=0, mName=cpu, mStatus=0}
Current cooling devices from HAL:
"""
        result = thermal_readings("  temperature: 358\n  level: 72\n", thermal)
        self.assertEqual(result["battery_c"], 35.8)
        self.assertEqual(result["battery_percent"], 72)
        self.assertEqual(result["sensors"], [dict(name="skin", type=3, celsius=43.5, status=2)])
        self.assertEqual(thermal_readings("Permission denied", "unsupported")["sensors"], [])
        self.assertIsNone(thermal_readings("Permission denied", "unsupported")["battery_c"])

    def test_host_latency_is_distinct_from_target_and_disabled_target_is_cleared(self):
        source = self.root / "vrserver.txt"
        source.write_text("old history\n")
        host = HostEncoderTarget(source, self.root)
        with source.open("a") as out:
            out.write("NvencTap: heartbeat api=12 enabled=1 3200x8192 avg=500M max=500M\n")
            out.write("NvencTap: last 10s: vrlink asked avg=350M | submit->lock mean=4.25ms max=7ms\n")
        host.poll()
        self.assertEqual(host.details()["target_mbps"], 500)
        self.assertEqual(host.details()["encode_latency_mean_ms"], 4.25)
        self.assertIn("submit->lock", (self.root / "host-nvenc.log").read_text())
        with source.open("a") as out:
            out.write("NvencTap: heartbeat api=12 enabled=0 3200x8192 avg=500M\n")
        host.poll()
        self.assertIsNone(host.snapshot())


class DiagnosticTests(RecordingTests):
    def setUp(self):
        super().setUp()
        self.probe = HeadsetDiagnostics(self.root)
        self.probe.token = "a" * 32

    def sample(self, seconds, multiplier=1, stream=1, **extra):
        return dict(event="stats", token=self.probe.token, pid=42, stream=stream,
                    monotonic_ns=int(seconds * 1e9), accepted_input_bytes=multiplier * 1_000_000,
                    accepted_input_frames=multiplier * 90, output_frames=multiplier * 89,
                    queue_to_output_count=multiplier * 80, queue_to_output_sum_ns=multiplier * 800_000_000,
                    queue_to_output_max_ns=20_000_000, **extra)

    def test_cumulative_rates_use_device_clock_and_expire(self):
        self.probe.feed(self.sample(30), now=100)
        self.probe.feed(self.sample(32, 3), now=101)
        result = self.probe.snapshot(now=101)
        self.assertEqual(result["decoder_input_mbps"], 8)
        self.assertEqual(result["decoder_input_fps"], 90)
        self.assertEqual(result["decoder_output_fps"], 89)
        self.assertEqual(result["queue_to_output_mean_ms"], 10)
        self.assertIsNone(self.probe.snapshot(now=105)["decoder_input_mbps"])
        self.probe.stop.set()
        self.assertIsNone(self.probe.snapshot(now=101)["decoder_input_mbps"])

    def test_stream_process_counter_and_clock_resets_need_new_baseline(self):
        for changed in (dict(stream=2), dict(pid=99), dict(accepted_input_bytes=1), dict(monotonic_ns=1)):
            self.probe.samples.clear()
            self.probe.feed(self.sample(30), now=100)
            row = self.sample(32, 3)
            row.update(changed)
            self.probe.feed(row, now=101)
            self.assertIsNone(self.probe.snapshot(now=101)["decoder_input_mbps"])

    def test_wrong_token_malformed_counters_and_stale_capture_are_ignored(self):
        row = self.sample(30)
        row["token"] = "b" * 32
        self.probe.feed(row, now=100)
        row = self.sample(30)
        row["output_frames"] = "broken"
        self.probe.feed(row, now=100)
        self.assertEqual(len(self.probe.samples), 0)
        self.probe.pending = dict(nonce="c" * 32, deadline=99, expected_codec="AV1")
        self.probe.feed(dict(event="capture", token=self.probe.token, nonce="c" * 32), now=100)
        self.assertTrue(self.probe.captures.empty())

    def test_parser_requires_logcat_pid_token_and_numeric_clock(self):
        self.assertIsNone(parse_decoder_line("GXRDecoderProbe: event=stats token=" + "a" * 32))
        line = "1.234 42 43 I GXRDecoderProbe: event=stats token=" + "a" * 32 + " monotonic_ns=10 stream=1 accepted_input_bytes=20"
        row = parse_decoder_line(line)
        self.assertEqual(row["pid"], 42)
        self.assertEqual(row["token"], "a" * 32)
        self.assertEqual(row["accepted_input_bytes"], 20)

    def pending_capture(self):
        pending = dict(nonce="b" * 32, expected_codec="AV1", deadline=time.monotonic() + 30)
        self.probe.pending = pending
        event = dict(event="capture", token=self.probe.token, nonce=pending["nonce"], pid=42,
                     stream=1, monotonic_ns=1234, accepted=1, scope="decoder_input", stage="before_codec_rewrite",
                     size=len(AV1), path=CAPTURE_FILE, sha256=hashlib.sha256(AV1).hexdigest())
        return event, pending

    def test_verify_persists_complete_hash_checked_bytes_and_structural_verdict(self):
        event, pending = self.pending_capture()
        with patch.object(self.probe, "_run", return_value=SimpleNamespace(stdout=AV1)) as run:
            self.probe._verify_capture(event, pending)
        result = self.probe.verification
        self.assertEqual(result["status"], "verified")
        self.assertEqual(Path(result["evidence_file"]).read_bytes(), AV1)
        self.assertEqual(json.loads(next(self.root.glob("verify-*.json")).read_text())["sha256"], event["sha256"])
        self.assertEqual(run.call_args.args[0][:3], ["exec-out", "head", "-c"])

    def test_truncated_or_wrong_hash_capture_never_verifies(self):
        event, pending = self.pending_capture()
        with patch.object(self.probe, "_run", return_value=SimpleNamespace(stdout=AV1[:-1])):
            self.probe._verify_capture(event, pending)
        self.assertEqual(self.probe.verification["status"], "inconclusive")
        self.assertIn("length/hash", self.probe.verification["message"])

    def test_settings_label_is_not_proof_and_disconnected_verify_is_inconclusive(self):
        self.probe.request_verify("HEVC")
        self.assertEqual(self.probe.verification["status"], "inconclusive")
        event, pending = self.pending_capture()
        event["accepted"] = 0
        with patch.object(self.probe, "_run") as run:
            self.probe._verify_capture(event, pending)
        run.assert_not_called()
        self.assertEqual(self.probe.verification["status"], "inconclusive")

    def test_usb_connection_rejects_different_or_network_transport(self):
        probe = HeadsetProbe(self.root)
        listing = SimpleNamespace(stdout="List of devices attached\nWIFI device\n")
        usb = SimpleNamespace(stdout="USB\n")
        with patch("colourlab.bitrate_probe.find_adb", return_value="adb"), \
             patch("colourlab.bitrate_probe.subprocess.run", side_effect=[listing, usb]), \
             patch("colourlab.bitrate_probe.subprocess.Popen") as popen:
            probe._read("WIFI")
        popen.assert_not_called()
        self.assertIn("USB mode", probe.status)

    def test_usb_auto_selection_ignores_unrelated_authorized_wifi_device(self):
        probe = HeadsetProbe(self.root)
        self.addCleanup(probe.close)
        listing = SimpleNamespace(stdout="List of devices attached\nWIFI device\nUSB device\n")
        process = Mock(stdout=io.StringIO(""))
        process.poll.return_value = 0
        with patch("colourlab.bitrate_probe.find_adb", return_value="adb"), \
             patch("colourlab.bitrate_probe.subprocess.run", side_effect=[listing, SimpleNamespace(stdout="USB\n")]), \
             patch("colourlab.bitrate_probe.subprocess.Popen", return_value=process) as popen, \
             patch.object(probe.diagnostics, "start"):
            probe._read("")
        self.assertEqual(popen.call_args.args[0][:3], ["adb", "-s", "USB"])

    def test_reconnect_never_reuses_an_alive_worker_or_old_verdict(self):
        self.probe.worker = Mock()
        self.probe.worker.is_alive.return_value = True
        previous_token = self.probe.token
        with self.assertRaises(ValueError):
            self.probe.start("adb", "different-headset")
        self.assertEqual(self.probe.token, previous_token)
        self.probe.worker.is_alive.return_value = False
        self.probe.verification = dict(status="verified", message="Old session")
        with patch("colourlab.headset_diagnostics.threading.Thread"):
            self.probe.start("adb", "different-headset")
        self.assertEqual(self.probe.verification["status"], "idle")
        self.assertEqual(self.probe.serial, "different-headset")

    def test_stale_direct_capture_cannot_be_saved_as_verified(self):
        event, pending = self.pending_capture()
        event["token"] = "c" * 32
        with patch.object(self.probe, "_run") as run:
            self.probe._verify_capture(event, pending)
        run.assert_not_called()
        self.assertEqual(self.probe.verification["status"], "inconclusive")


class TelemetryApplicationTests(TemporaryApplicationTests):
    def test_selecting_expected_codec_never_changes_stream_settings(self):
        previous = self.app.settings
        self.app.verify_codec("AV1")
        self.assertEqual(self.app.codec_expected, "AV1")
        self.assertEqual(self.app.settings, previous)
        self.assertEqual(self.app.headset_probe.diagnostics.verification["status"], "inconclusive")

    def test_report_contains_telemetry_and_codec_evidence(self):
        self.app.save_report(apply_ui=False)
        report = json.loads(next(self.app.run_dir.glob("report-*.json")).read_text())
        self.assertIn("telemetry_latest", report)
        self.assertIn("codec_verification", report)
