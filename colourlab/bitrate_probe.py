"""Optional ADB log reader. User initiated; no install, restart or encoder edits."""
from __future__ import annotations

import collections
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .bitrate import export_case, parse_probe_line


def hidden_process_options():
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def find_adb(explicit=None):
    if explicit:
        found = shutil.which(str(explicit))
        return found or (str(Path(explicit)) if Path(explicit).is_file() else None)
    found = shutil.which("adb")
    if found:
        return found
    for key in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        candidate = Path(os.environ.get(key, "")) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
        if candidate.is_file():
            return str(candidate)
    return None


class HeadsetProbe:
    def __init__(self, directory, adb=None):
        self.directory, self.adb_option = Path(directory), adb
        self.lock = threading.RLock()
        self.process = None
        self.worker = None
        self.stop_event = threading.Event()
        self.connected = False
        self.status = "Optional headset probe disconnected"
        self.serial = ""
        self.adb = None
        self.log_path = None
        self.receives = collections.deque(maxlen=2048)
        self.last_receive_host = None
        self.codec = "unknown"
        self.result = None
        self.cases = {}
        self.commands = queue.Queue()
        self.command_worker = None
        self.exports = []

    def connect(self, serial=""):
        if self.worker and self.worker.is_alive():
            return
        if self.command_worker and self.command_worker.is_alive():
            self.status = "Finishing the previous ADB connection; try Connect again shortly"
            return
        self.stop_event.clear()
        self.commands = queue.Queue()
        self.status = "Looking for an authorized ADB headset…"
        self.worker = threading.Thread(target=self._read, args=(serial,), daemon=True, name="ColourLab-headset")
        self.worker.start()

    def _read(self, requested_serial):
        output = None
        try:
            self.adb = find_adb(self.adb_option)
            if not self.adb:
                raise ValueError("ADB not found. Add Android platform-tools to PATH or launch with --adb PATH.")
            listing = subprocess.run([self.adb, "devices"], capture_output=True, text=True, timeout=8,
                                     check=True, **hidden_process_options()).stdout
            devices = [parts[0] for line in listing.splitlines() if len(parts := line.split()) == 2 and parts[1] == "device"]
            if requested_serial:
                if requested_serial not in devices:
                    raise ValueError("Selected device is offline or unauthorized. Check ADB authorization in the headset.")
                self.serial = requested_serial
            elif len(devices) == 1:
                self.serial = devices[0]
            else:
                raise ValueError("Connect one authorized headset, or enter its device serial on the Bitrate tab.")
            if self.stop_event.is_set():
                return
            self.directory.mkdir(parents=True, exist_ok=True)
            self.log_path = self.directory / f"headset-{time.time_ns()}.log"
            output = self.log_path.open("w", encoding="utf-8", buffering=1)
            process = subprocess.Popen([self.adb, "-s", self.serial, "logcat", "-v", "monotonic", "-T", "1",
                                        "-s", "GXRStreamProbe", "GXRTestPhase"], stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                       **hidden_process_options())
            with self.lock:
                self.process = process
                self.connected = not self.stop_event.is_set()
                self.receives.clear()
                self.last_receive_host = None
                self.status = "ADB connected; waiting for diagnostic probe frames"
            if self.stop_event.is_set():
                process.terminate()
            self.command_worker = threading.Thread(target=self._commands, daemon=True, name="ColourLab-markers")
            self.command_worker.start()
            for line in process.stdout:
                if self.stop_event.is_set():
                    break
                output.write(line)
                row = parse_probe_line(line)
                if row:
                    self.feed(row)
            if not self.stop_event.is_set():
                with self.lock:
                    self.status = "ADB log stream ended; reconnect the headset probe"
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            with self.lock:
                self.status = str(exc)
        finally:
            self.stop_event.set()
            with self.lock:
                self.connected = False
                process = self.process
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            if process and process.stdout:
                process.stdout.close()
            if output:
                output.close()

    def feed(self, row, now=None):
        with self.lock:
            if row["event"] == "receive":
                self.last_receive_host = time.monotonic() if now is None else now
                self.codec = row.get("wire", "unknown")
                if not row.get("codec_config") and not row.get("duplicate_id"):
                    self.receives.append(row)
                self.status = "Diagnostic decoder-input frames received"
            if row["event"] == "phase" and row.get("edge") == "end" and row.get("case") in self.cases:
                # Leave room for decoder outputs and a cumulative checkpoint.
                timer = threading.Timer(2.0, self._export, args=(row["case"],))
                timer.daemon = True
                self.exports.append(timer)
                timer.start()

    def marker(self, edge, test):
        with self.lock:
            if not self.connected:
                return False
            self.cases[test.case] = (self.log_path, test.snapshot())
            self.commands.put((edge, test.case, test.scene, test.target))
            return True

    def _commands(self):
        while not self.stop_event.is_set():
            try:
                edge, case, scene, target = self.commands.get(timeout=.25)
            except queue.Empty:
                continue
            try:
                subprocess.run([self.adb, "-s", self.serial, "shell", "log", "-t", "GXRTestPhase",
                                f"round={target} mode={scene} edge={edge} case={case}"],
                               capture_output=True, timeout=5, check=True, **hidden_process_options())
            except (OSError, subprocess.SubprocessError) as exc:
                with self.lock:
                    self.status = "Cannot write headset test marker: " + str(exc)
            finally:
                self.commands.task_done()

    def _export(self, case):
        try:
            with self.lock:
                path, context = self.cases[case]
            result = export_case(path, self.directory / case, case, context)
            with self.lock:
                self.result = result
                self.status = f"Saved {result['received_video_mbps']:.1f} Mbps measured result"
        except (OSError, ValueError, KeyError) as exc:
            with self.lock:
                self.status = "No verified test result: " + str(exc)

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            rows = list(self.receives)
            fresh = self.connected and self.last_receive_host is not None and now - self.last_receive_host <= 2
            rate = None
            fps = None
            if fresh and rows and rows[-1]["monotonic_ns"] - rows[0]["monotonic_ns"] >= 1_000_000_000:
                latest = rows[-1]["monotonic_ns"]
                same_stream = [r for r in rows if (r.get("pid"), r.get("stream")) == (rows[-1].get("pid"), rows[-1].get("stream"))]
                if same_stream and latest - same_stream[0]["monotonic_ns"] >= 1_000_000_000:
                    window = [r for r in same_stream if latest - 1_000_000_000 < r["monotonic_ns"] <= latest]
                    rate, fps = sum(r["size"] for r in window) * 8 / 1e6, len(window)
            return dict(connected=self.connected, status=self.status, received_mbps=rate,
                        received_aus_per_second=fps, wire_codec=self.codec if fresh else "unknown",
                        log_file=str(self.log_path) if self.log_path else None, result=self.result)

    def close(self):
        # Give a just-requested end marker a bounded chance to reach logcat
        # before shutting down its reader (not an APK/process restart).
        deadline = time.monotonic() + 1.0
        while self.connected and self.commands.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(.02)
        self.stop_event.set()
        with self.lock:
            self.connected = False
            process = self.process
            self.status = "Headset probe disconnected; captures preserved"
        if process and process.poll() is None:
            process.terminate()
        if self.worker:
            self.worker.join(timeout=10)
        if self.command_worker:
            self.command_worker.join(timeout=6)
        for timer in self.exports:
            timer.join(timeout=4)


class HostEncoderTarget:
    """Latest recorded NVENC request, deliberately never called payload Mbps."""
    def __init__(self, path=None):
        candidates = [Path(path)] if path else []
        if not path and os.name == "nt":
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                    candidates.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]) / "logs/vrserver.txt")
            except OSError:
                pass
            candidates.append(Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Steam/logs/vrserver.txt")
        self.path = next((p for p in candidates if p.is_file()), candidates[0] if candidates else None)
        self.offset = self.path.stat().st_size if self.path and self.path.is_file() else 0
        self.target, self.updated = None, None
        self.partial = ""

    def poll(self):
        if not self.path or not self.path.is_file():
            return
        try:
            if self.path.stat().st_size < self.offset:
                self.offset, self.partial = 0, ""
            with self.path.open("rb") as source:
                source.seek(self.offset)
                data = source.read(256 * 1024)
                self.offset = source.tell()
            text = self.partial + data.decode("utf-8", "replace")
            lines = text.split("\n")
            self.partial = lines.pop()
            for line in lines:
                match = re.search(r"NvencTap: heartbeat api=\d+ enabled=1 .*?avg=([\d.]+)M", line)
                if match:
                    self.target, self.updated = float(match[1]), time.monotonic()
        except OSError:
            self.target = None

    def snapshot(self):
        return self.target if self.updated is not None and time.monotonic() - self.updated <= 20 else None
