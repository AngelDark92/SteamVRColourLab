"""Opt-in USB diagnostics and nonce-bound verification of decoder input bytes."""
from __future__ import annotations

import collections
import hashlib
import json
import queue
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path

from .telemetry import thermal_readings

DEVICE_FILES = "/sdcard/Android/data/com.valvesoftware.steamlinkvr/files/"
PROBE_REQUEST = DEVICE_FILES + "colourlab-probe.request"
VERIFY_REQUEST = DEVICE_FILES + "colourlab-verify.request"
CAPTURE_FILE = DEVICE_FILES + "colourlab-capture.bin"
MAX_CAPTURE = 16 * 1024 * 1024


def parse_decoder_line(line):
    if "GXRDecoderProbe" not in line:
        return None
    fields = dict(re.findall(r"([a-z_][a-z_0-9]*)=([^\s]+)", line))
    if fields.get("event") not in ("stats", "capture") or not re.fullmatch(r"[0-9a-f]{32}", fields.get("token", "")):
        return None
    for key, value in list(fields.items()):
        if key not in ("token", "nonce", "sha256", "event", "path", "scope", "stage") and re.fullmatch(r"\d+", value):
            fields[key] = int(value)
    if any(type(fields.get(k)) is not int or fields[k] < 0 for k in ("stream", "monotonic_ns")):
        return None
    pid = re.match(r"\s*\d+\.\d+\s+(\d+)\s+\d+\s", line)
    if not pid:
        return None
    fields["pid"] = int(pid[1])
    return fields


class HeadsetDiagnostics:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.worker = None
        self.adb = None
        self.serial = ""
        self.token = ""
        self.samples = collections.deque(maxlen=2)
        self.sample_at = None
        self.thermal = {}
        self.thermal_at = None
        self.status = "Connect USB ADB for temperatures and optional decoder diagnostics"
        self.verification = {"status": "idle", "message": "Select the expected codec, then Verify during streaming"}
        self.pending = None
        self.captures = queue.Queue()

    def _run(self, args, *, binary=False, check=True, timeout=3):
        from .bitrate_probe import hidden_process_options
        return subprocess.run([self.adb, "-s", self.serial, *args], capture_output=True,
                              text=not binary, timeout=timeout, check=check, **hidden_process_options())

    def start(self, adb, serial):
        if self.worker and self.worker.is_alive():
            raise ValueError("Previous headset diagnostics are still disconnecting; retry shortly")
        self.adb, self.serial = adb, serial
        self.token = uuid.uuid4().hex
        self.stop.clear()
        self.samples.clear()
        self.sample_at = self.thermal_at = None
        self.pending = None
        self.verification = dict(status="idle", message="New ADB session; select the expected codec and Verify")
        self.captures = queue.Queue()
        self.worker = threading.Thread(target=self._work, daemon=True, name="ColourLab-diagnostics")
        self.worker.start()

    def _write_request(self, path, value):
        # Both paths are constants; values are locally generated hex tokens.
        self._run(["shell", f"printf '%s' '{value}' > {path}"])

    def _remove_owned_request(self, path, value):
        try:
            found = self._run(["shell", "cat", path], check=False).stdout.strip()
            if found == value:
                self._run(["shell", "rm", path], check=False)
        except (OSError, subprocess.SubprocessError):
            pass

    def _work(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        next_thermal, request_sent = 0.0, False
        verify_value = None
        try:
            with (self.directory / f"system-{self.token}.jsonl").open("a", encoding="utf-8", buffering=1) as raw:
                try:
                    package = self._run(["shell", "dumpsys", "package", "com.valvesoftware.steamlinkvr"]).stdout
                    raw.write(json.dumps(dict(host_monotonic=time.monotonic(), package=package)) + "\n")
                    self._write_request(PROBE_REQUEST, self.token)
                    request_sent = True
                    self.status = "ADB connected; waiting for optional GXRDecoderProbe patch"
                except (OSError, subprocess.SubprocessError) as exc:
                    self.status = "System telemetry only; decoder probe request failed: " + str(exc)
                while not self.stop.is_set():
                    now = time.monotonic()
                    if now >= next_thermal:
                        outputs = {}
                        for service in ("battery", "thermalservice"):
                            if self.stop.is_set():
                                break
                            try:
                                result = self._run(["shell", "dumpsys", service], check=False)
                                outputs[service] = result.stdout if result.returncode == 0 else ""
                                raw.write(json.dumps(dict(host_monotonic=time.monotonic(), service=service,
                                                          returncode=result.returncode, stdout=result.stdout,
                                                          stderr=result.stderr)) + "\n")
                            except (OSError, subprocess.SubprocessError) as exc:
                                outputs[service] = ""
                                raw.write(json.dumps(dict(service=service, error=str(exc))) + "\n")
                        with self.lock:
                            self.thermal = thermal_readings(outputs.get("battery", ""), outputs.get("thermalservice", ""))
                            self.thermal_at = time.monotonic()
                        if request_sent and not self.stop.is_set():
                            try:
                                owner = self._run(["shell", "cat", PROBE_REQUEST], check=False).stdout.strip()
                                if owner == self.token:
                                    self._write_request(PROBE_REQUEST, self.token)
                                else:
                                    request_sent = False
                                    self.status = "Decoder probe ownership changed; reconnect to take measurements"
                            except (OSError, subprocess.SubprocessError) as exc:
                                self.status = "Decoder probe lease refresh failed: " + str(exc)
                        next_thermal = time.monotonic() + 5
                    with self.lock:
                        pending = dict(self.pending) if self.pending else None
                    if self.stop.is_set():
                        break
                    if pending and pending["nonce"] != verify_value:
                        try:
                            self._write_request(VERIFY_REQUEST, self.token + " " + pending["nonce"])
                            verify_value = pending["nonce"]
                        except (OSError, subprocess.SubprocessError) as exc:
                            self._finish(dict(status="inconclusive", message="Cannot request capture: " + str(exc)), pending)
                    try:
                        event, expected = self.captures.get_nowait()
                    except queue.Empty:
                        pass
                    else:
                        self._verify_capture(event, expected)
                    with self.lock:
                        pending = dict(self.pending) if self.pending else None
                    if pending and time.monotonic() >= pending["deadline"]:
                        self._finish(dict(status="inconclusive", message="No complete fresh decoder capture. Enable the diagnostic patch and stream a keyframe, then retry."), pending)
                    self.wake.wait(.2)
                    self.wake.clear()
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            with self.lock:
                self.status = "Diagnostics stopped: " + str(exc)
        finally:
            self.stop.set()
            if verify_value:
                self._remove_owned_request(VERIFY_REQUEST, self.token + " " + verify_value)
            if request_sent:
                self._remove_owned_request(PROBE_REQUEST, self.token)

    def feed(self, row, now=None):
        now = time.monotonic() if now is None else now
        if row.get("token") != self.token:
            return
        with self.lock:
            if row["event"] == "stats":
                required = ("accepted_input_bytes", "accepted_input_frames", "output_frames",
                            "queue_to_output_count", "queue_to_output_sum_ns", "queue_to_output_max_ns")
                if any(type(row.get(k)) is not int or row[k] < 0 for k in required):
                    return
                if self.samples and any(row.get(k) != self.samples[-1].get(k) for k in ("stream", "pid")):
                    self.samples.clear()
                if self.samples and (row["monotonic_ns"] <= self.samples[-1]["monotonic_ns"] or
                                     any(row[k] < self.samples[-1][k] for k in required)):
                    self.samples.clear()
                self.samples.append(row)
                self.sample_at = now
                self.status = "Fresh diagnostic decoder counters received"
            elif row["event"] == "capture" and self.pending and row.get("nonce") == self.pending["nonce"]:
                if now <= self.pending["deadline"]:
                    self.captures.put((dict(row), dict(self.pending)))
                    self.wake.set()

    def request_verify(self, codec):
        from .codec_verify import CODECS
        if codec not in CODECS:
            raise ValueError("Choose H.264, HEVC or AV1")
        with self.lock:
            if not self.worker or not self.worker.is_alive() or self.stop.is_set():
                self.verification = dict(status="inconclusive", message="Connect USB ADB before verifying the live stream")
                return
            if self.pending:
                return
            self.pending = dict(nonce=uuid.uuid4().hex, expected_codec=codec, deadline=time.monotonic() + 30)
            self.verification = dict(status="waiting", message="Waiting for fresh stream bytes at the headset…")
            self.wake.set()

    def _finish(self, result, pending):
        result.update(expected_codec=pending["expected_codec"], nonce=pending["nonce"], token=self.token,
                      host_monotonic=time.monotonic())
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"verify-{pending['nonce']}.json").write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        with self.lock:
            if self.pending and self.pending["nonce"] == pending["nonce"]:
                self.verification, self.pending = result, None

    def _verify_capture(self, event, pending):
        from .codec_verify import identify_codec
        try:
            with self.lock:
                if (self.stop.is_set() or not self.pending or self.pending["nonce"] != pending["nonce"] or
                        event.get("nonce") != pending["nonce"] or event.get("token") != self.token or
                        time.monotonic() > pending["deadline"]):
                    raise ValueError("Capture request expired or belongs to another session")
            if (event.get("accepted") != 1 or event.get("scope") != "decoder_input" or
                    event.get("stage") != "before_codec_rewrite" or event.get("path") != CAPTURE_FILE or
                    type(event.get("size")) is not int or not 0 < event["size"] <= MAX_CAPTURE or
                    not re.fullmatch(r"[0-9a-f]{64}", str(event.get("sha256", "")))):
                raise ValueError("Capture metadata is incomplete or from an unsupported stage")
            # Bound the remote read, even if a broken helper produced a huge file.
            data = self._run(["exec-out", "head", "-c", str(MAX_CAPTURE + 1), CAPTURE_FILE], binary=True, timeout=8).stdout
            digest = hashlib.sha256(data).hexdigest()
            if len(data) != event["size"] or digest != event["sha256"]:
                raise ValueError("Capture length/hash mismatch; bytes may have changed")
            evidence = self.directory / f"codec-{pending['nonce']}.bin"
            evidence.write_bytes(data)
            result = identify_codec(data)
            if self.stop.is_set() or time.monotonic() > pending["deadline"]:
                raise ValueError("ADB disconnected or capture request expired during verification")
            match = result["detected_codec"] == pending["expected_codec"]
            self._finish(dict(result, status="verified" if match else "mismatch", sha256=digest,
                              capture=event, evidence_file=str(evidence),
                              message=("Verified " if match else "Mismatch: captured ") + result["detected_codec"] +
                                      " in fresh headset decoder-input bytes (before codec rewrite).",
                              scope="Structural codec identification of one accepted decoder-input AU; not decoder conformance or display proof"), pending)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            self._finish(dict(status="inconclusive", message=str(exc), capture=event), pending)

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            fresh = not self.stop.is_set() and self.sample_at is not None and now - self.sample_at <= 3
            result = dict(status=self.status, decoder_input_mbps=None, decoder_input_fps=None,
                          decoder_output_fps=None, queue_to_output_mean_ms=None, queue_to_output_max_ms=None,
                          thermal=self.thermal if not self.stop.is_set() and self.thermal_at is not None and now - self.thermal_at <= 20 else {},
                          verification=dict(self.verification), serial=self.serial, token=self.token,
                          fresh=fresh, source="GXRDecoderProbe cumulative counters; rates use device monotonic time")
            if self.stop.is_set() and result["verification"].get("status") in ("verified", "mismatch"):
                result["verification"] = dict(result["verification"], message="Saved earlier capture: " + result["verification"]["message"])
            if self.sample_at is not None and not fresh:
                result["status"] = "Decoder counters stale/disconnected; saved evidence remains on PC"
            if fresh and len(self.samples) == 2:
                a, b = self.samples
                seconds = (b["monotonic_ns"] - a["monotonic_ns"]) / 1e9
                if 0 < seconds <= 10:
                    result.update(decoder_input_mbps=(b["accepted_input_bytes"] - a["accepted_input_bytes"]) * 8 / seconds / 1e6,
                                  decoder_input_fps=(b["accepted_input_frames"] - a["accepted_input_frames"]) / seconds,
                                  decoder_output_fps=(b["output_frames"] - a["output_frames"]) / seconds,
                                  counters=b)
                    count = b["queue_to_output_count"] - a["queue_to_output_count"]
                    if count:
                        result["queue_to_output_mean_ms"] = (b["queue_to_output_sum_ns"] - a["queue_to_output_sum_ns"]) / count / 1e6
                        result["queue_to_output_max_ms"] = b["queue_to_output_max_ns"] / 1e6
            return result

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.worker:
            self.worker.join(timeout=26)
        with self.lock:
            if self.pending:
                self._finish(dict(status="inconclusive", message="ADB disconnected during verification"), dict(self.pending))
