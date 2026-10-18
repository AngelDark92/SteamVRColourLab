"""PC-side session recording; every rate retains its measurement stage."""
from __future__ import annotations

import csv
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path


def thermal_readings(battery, thermal):
    """Battery is tenths C; thermalservice HAL temperatures are already C.

    Cached thermal callbacks can be hours old, so only parse the current HAL
    section. Keep sensor names/types; never silently call a skin sensor CPU.
    """
    result = {"battery_c": None, "battery_percent": None, "thermal_status": None, "sensors": []}
    for key, value in re.findall(r"^\s*(temperature|level):\s*(-?\d+)\s*$", battery, re.M):
        if key == "temperature" and -400 <= int(value) <= 1500:
            result["battery_c"] = int(value) / 10
        elif key == "level" and 0 <= int(value) <= 100:
            result["battery_percent"] = int(value)
    status = re.search(r"^\s*Thermal Status:\s*(\d+)", thermal, re.M)
    if status:
        result["thermal_status"] = int(status[1])
    current = thermal.partition("Current temperatures from HAL:")[2].partition("Current cooling devices")[0]
    for value, kind, name, state in re.findall(
            r"Temperature\{mValue=([^,]+),\s*mType=(-?\d+),\s*mName=([^,}]+),\s*mStatus=(\d+)\}", current):
        try:
            celsius = float(value)
        except ValueError:
            continue
        if math.isfinite(celsius) and -40 <= celsius <= 150:
            result["sensors"].append(dict(name=name, type=int(kind), celsius=celsius, status=int(state)))
    return result


class SessionTelemetry:
    FIELDS = ("utc", "host_monotonic_seconds", "window_seconds", "mode", "workload_case", "scene_submissions_fps",
              "host_encoder_target_mbps", "host_encode_latency_mean_ms", "host_sent_payload_mbps",
              "headset_connected", "headset_decoder_input_mbps", "headset_decoder_input_fps",
              "headset_decoder_output_fps", "headset_queue_to_output_mean_ms", "headset_queue_to_output_max_ms",
              "headset_received_video_mbps", "headset_received_aus_per_second", "headset_battery_c",
              "headset_battery_percent", "headset_thermal_status", "headset_telemetry_status")

    def __init__(self, directory):
        self.directory = Path(directory) / "telemetry"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.jsonl = (self.directory / "samples.jsonl").open("a", encoding="utf-8", buffering=1)
        self.csv_file = (self.directory / "samples.csv").open("a", encoding="utf-8", newline="", buffering=1)
        self.csv = csv.DictWriter(self.csv_file, fieldnames=self.FIELDS)
        self.csv.writeheader()
        self.previous_time = None
        self.submissions = 0
        self.latest = None
        (self.directory / "schema.json").write_text(json.dumps({
            "version": 1, "sample_period_seconds": 1,
            "scene_submissions_fps": "Successful stereo submissions by this app; unavailable in desktop preview",
            "host_encoder_target_mbps": "Accepted encoder request from fresh NVENC log, not measured payload",
            "host_sent_payload_mbps": "Unavailable: no exact host byte counter is provided",
            "headset_decoder_input_mbps": "Accepted compressed MediaCodec input bytes over device monotonic time",
            "headset_queue_to_output_mean_ms": "Queue-to-output residence, including decoder buffering; not hardware-only time",
            "headset_queue_to_output_max_ms": "Maximum queue-to-output residence within the current decoder generation",
            "headset_received_video_mbps": "Legacy transport probe only; unavailable without that producer",
            "headset_decoder_output_fps": "Dequeued decoder buffers, not physical presentation",
            "temperatures": "Current HAL sensors and battery; null when unsupported/stale",
        }, indent=2) + "\n", encoding="utf-8")

    def tick(self, now, submitted, desktop, host, headset, vr_status="", workload_case=None):
        self.submissions += bool(submitted and not desktop)
        if self.previous_time is None:
            self.previous_time = now
            self.submissions = 0
            return
        seconds = now - self.previous_time
        if seconds < 1:
            return
        diagnostic = headset.get("diagnostics", {})
        thermal = diagnostic.get("thermal", {})
        row = dict(utc=datetime.now(timezone.utc).isoformat(), host_monotonic_seconds=now,
                   window_seconds=seconds, mode="desktop_preview" if desktop else "steamvr", workload_case=workload_case,
                   scene_submissions_fps=None if desktop else self.submissions / seconds,
                   host_encoder_target_mbps=host.get("target_mbps"),
                   host_encode_latency_mean_ms=host.get("encode_latency_mean_ms"), host_sent_payload_mbps=None,
                   headset_connected=headset.get("connected", False),
                   headset_decoder_input_mbps=diagnostic.get("decoder_input_mbps"),
                   headset_decoder_input_fps=diagnostic.get("decoder_input_fps"),
                   headset_decoder_output_fps=diagnostic.get("decoder_output_fps"),
                   headset_queue_to_output_mean_ms=diagnostic.get("queue_to_output_mean_ms"),
                   headset_queue_to_output_max_ms=diagnostic.get("queue_to_output_max_ms"),
                   headset_received_video_mbps=headset.get("received_mbps"),
                   headset_received_aus_per_second=headset.get("received_aus_per_second"),
                   headset_battery_c=thermal.get("battery_c"), headset_battery_percent=thermal.get("battery_percent"),
                   headset_thermal_status=thermal.get("thermal_status"),
                   headset_telemetry_status=diagnostic.get("status", headset.get("status")))
        self.csv.writerow(row)
        row.update(host=host, headset=diagnostic, vr_status=vr_status)
        self.jsonl.write(json.dumps(row, allow_nan=False) + "\n")
        self.previous_time, self.submissions, self.latest = now, 0, row

    def close(self):
        self.jsonl.close()
        self.csv_file.close()
