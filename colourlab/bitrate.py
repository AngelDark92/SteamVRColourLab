"""Fullscreen workload scheduling and saved decoder-input evidence analysis.

No encoder settings are changed. Mbps is compressed video payload at the
headset, never inferred from a host target or from submitted scene frames.
"""
from __future__ import annotations

import collections
import csv
import json
import math
import re
import uuid
from pathlib import Path

SCENES = {"static": "Static detail", "motion": "Moving detail",
          "contrast": "High-contrast motion", "noise": "Changing noise (maximum load)"}


def is_fullscreen(settings):
    return settings.pattern.startswith("bitrate_")


class BitrateTest:
    def __init__(self):
        self.scene = "motion"
        self.duration = 45.0
        self.target = 500
        self.serial = ""
        self.running = False
        self.started = None
        self.elapsed = 0.0
        self.submissions = 0
        self.interrupted = False
        self.previous = None
        self.case = ""
        self.result = "No test recorded"

    def configure(self, field, value):
        if self.running:
            raise ValueError("Stop the running test before changing its configuration.")
        if field == "scene" and value in SCENES:
            self.scene = value
        elif field == "duration" and type(value) in (int, float) and math.isfinite(value) and 15 <= value <= 600:
            self.duration = float(value)
        elif field == "target" and type(value) in (int, float) and math.isfinite(value) and value == int(value) and 10 <= value <= 2000:
            self.target = int(value)
        elif field == "serial" and isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:\-]{0,128}", value):
            self.serial = value
        else:
            raise ValueError("Use duration 15–600 s, integer target 10–2000 Mbps, or a valid device serial.")

    def begin(self, settings):
        if self.running:
            raise ValueError("A bitrate test is already running.")
        self.previous = settings
        self.running, self.started = True, None
        self.elapsed, self.submissions, self.interrupted = 0.0, 0, False
        self.case = uuid.uuid4().hex
        self.result = "Waiting for scene focus, tracking and minimized VR menu"

    def tick(self, now, submitted):
        """Start the clock on the first submitted stereo frame, not the click."""
        if not self.running:
            return False, False
        started_now = self.started is None and submitted
        if started_now:
            self.started = now
            self.result = "Running fullscreen"
        if self.started is not None:
            self.elapsed = max(0.0, now - self.started)
            if submitted:
                self.submissions += 1
            else:
                self.interrupted = True
            return started_now, self.elapsed >= self.duration
        return False, False

    def snapshot(self):
        return dict(scene=self.scene, duration=self.duration, selected_target_mbps=self.target,
                    target_is_user_note=True, running=self.running, elapsed_seconds=round(self.elapsed, 1),
                    scene_submissions=self.submissions, interrupted=self.interrupted,
                    case=self.case, status=self.result)


def parse_probe_line(line):
    fields = dict(re.findall(r"([a-z_][a-z_0-9]*)=([^\s]+)", line))
    if "GXRStreamProbe" in line and "event" in fields:
        for key, value in list(fields.items()):
            if key != "sha256":
                try:
                    fields[key] = int(value)
                except ValueError:
                    pass
        match = re.match(r"\s*\d+\.\d+\s+(\d+)\s+\d+\s", line)
        if match:
            fields["pid"] = int(match[1])
        required = {"receive": ("transport_id", "size"), "queue": ("transport_id", "size"),
                    "output": ("transport_id",), "release": ("transport_id",)}.get(fields["event"], ())
        if any(type(fields.get(key)) is not int or fields[key] < 0
               for key in ("monotonic_ns", "stream", *required)):
            return None
        return fields
    if "GXRTestPhase" in line and "case" in fields:
        match = re.match(r"\s*(\d+\.\d+)\s", line)
        if match:
            fields.update(event="phase", monotonic_ns=round(float(match[1]) * 1e9))
            return fields
    return None


def frame_key(row):
    return row.get("pid"), row.get("stream"), row.get("transport_id")


def analyse_case(log_path: Path, case: str):
    records = [row for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines()
               if (row := parse_probe_line(line)) is not None]
    starts = [r for r in records if r["event"] == "phase" and r.get("case") == case and r.get("edge") == "start"]
    ends = [r for r in records if r["event"] == "phase" and r.get("case") == case and r.get("edge") == "end"]
    if not starts or not ends:
        raise ValueError("Headset phase markers are unavailable; no measured test result.")
    start, end = starts[0], ends[-1]
    t0, t1 = start["monotonic_ns"] + 5_000_000_000, end["monotonic_ns"] - 2_000_000_000
    if t1 <= t0:
        raise ValueError("Test was too short for 5 s settling and 2 s teardown exclusion.")
    window = [r for r in records if t0 <= r.get("monotonic_ns", -1) < t1]
    received = [r for r in window if r["event"] == "receive" and not r.get("codec_config") and not r.get("duplicate_id")]
    if not received:
        raise ValueError("No diagnostic decoder-input frames in this test. Install/enable the compatible headset probe.")
    outputs = {frame_key(r): r["monotonic_ns"] for r in records if r["event"] == "output"}
    releases = {frame_key(r): r["monotonic_ns"] for r in records if r["event"] == "release" and r.get("status") == 0 and r.get("render") == 1}
    queues = collections.defaultdict(list)
    for r in records:
        if r["event"] == "queue" and r.get("accepted") == 1:
            queues[frame_key(r)].append(r)
    frames = [dict(pid=r.get("pid"), stream=r["stream"], generation=r.get("generation"),
                   transport_frame_id=r["transport_id"], receive_monotonic_ns=r["monotonic_ns"],
                   received_bytes=r["size"], wire_codec=r.get("wire", "unknown"),
                   accepted_queue_count=len(queues[frame_key(r)]),
                   output_monotonic_ns=outputs.get(frame_key(r), ""),
                   render_release_monotonic_ns=releases.get(frame_key(r), "")) for r in received]
    checks, missing, previous = [], 0, {}
    for r in received:
        key = (r.get("pid"), r["stream"])
        if key in previous:
            missing += max(0, r["transport_id"] - previous[key] - 1)
        previous[key] = r["transport_id"]
    for identity in previous:
        totals = [r for r in records if r["event"] == "totals" and (r.get("pid"), r.get("stream")) == identity]
        before = [r for r in totals if r["monotonic_ns"] < t0]
        after = [r for r in totals if r["monotonic_ns"] >= t1]
        if not before or not after:
            checks.append(dict(pid=identity[0], stream=identity[1], complete=False, reason="Missing before/after cumulative checkpoints"))
            continue
        a, b = before[-1], after[-1]
        rows = [r for r in records if (r.get("pid"), r.get("stream")) == identity and a["monotonic_ns"] < r.get("monotonic_ns", 0) <= b["monotonic_ns"]]
        receives = [r for r in rows if r["event"] == "receive"]
        attempts = [r for r in rows if r["event"] == "queue"]
        accepted = [r for r in attempts if r.get("accepted") == 1]
        released = [r for r in rows if r["event"] == "release" and r.get("status") == 0]
        observed = dict(receives=len(receives), received_bytes=sum(r["size"] for r in receives),
                        attempts=len(attempts), accepted=len(accepted), accepted_bytes=sum(r["size"] for r in accepted),
                        outputs=sum(r["event"] == "output" for r in rows), released=len(released),
                        render_released=sum(r.get("render") == 1 for r in released))
        matches = {key: observed[key] == b.get(key, -1) - a.get(key, -1) for key in observed}
        checks.append(dict(pid=identity[0], stream=identity[1], complete=all(matches.values()), checks=matches))
    seconds = (t1 - t0) / 1e9
    buckets = []
    for width_ms in (100, 1000):
        width = width_ms * 1_000_000
        sizes = [0] * ((t1 - t0) // width)
        for r in received:
            index = (r["monotonic_ns"] - t0) // width
            if index < len(sizes):
                sizes[index] += r["size"]
        buckets += [dict(bucket_ms=width_ms, start_monotonic_ns=t0 + i * width,
                         received_bytes=size, received_video_mbps=8 * size / (width_ms / 1000) / 1e6)
                    for i, size in enumerate(sizes)]
    rate = sum(r["size"] for r in received) * 8 / seconds / 1e6
    accepted_in_window = [r for r in window if r["event"] == "queue" and r.get("accepted") == 1 and not r.get("codec_config")]
    summary = dict(case=case, scene=start.get("mode"), selected_target_mbps=int(start["round"]),
                   seconds=seconds, received_video_mbps=rate, received_aus=len(received), received_aus_per_second=len(received) / seconds,
                   accepted_video_mbps=sum(r["size"] for r in accepted_in_window) * 8 / seconds / 1e6,
                   received_ids_missing_between_frames=missing,
                   accepted_ids_without_output=[r["transport_frame_id"] for r in frames if r["accepted_queue_count"] and not r["output_monotonic_ns"]],
                   accepted_ids_without_render_release=[r["transport_frame_id"] for r in frames if r["accepted_queue_count"] and not r["render_release_monotonic_ns"]],
                   decoder_output_count=sum(r["event"] == "output" for r in window),
                   successful_render_release_count=sum(r["event"] == "release" and r.get("status") == 0 and r.get("render") == 1 for r in window),
                   telemetry_complete=bool(checks) and all(c["complete"] for c in checks), counter_checks=checks,
                   queue_failures=sum(r["event"] == "queue" and r.get("accepted") == 0 for r in window),
                   wrapper_drops=sum(r["event"] == "queue_result" and r.get("dropped") == 1 for r in window),
                   max_100ms_mbps=max((r["received_video_mbps"] for r in buckets if r["bucket_ms"] == 100), default=None),
                   max_1s_mbps=max((r["received_video_mbps"] for r in buckets if r["bucket_ms"] == 1000), default=None),
                   one_second_windows_at_or_above_target=sum(r["bucket_ms"] == 1000 and r["received_video_mbps"] >= int(start["round"]) for r in buckets),
                   scope="Reassembled compressed video payload, excluding network overhead; render release is not physical presentation proof.")
    return summary, frames, buckets


def export_case(log_path, directory, case, context):
    summary, frames, buckets = analyse_case(log_path, case)
    summary["workload"] = context
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, rows in (("frames.csv", frames), ("bitrate-windows.csv", buckets)):
        with (directory / name).open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    (directory / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return summary
