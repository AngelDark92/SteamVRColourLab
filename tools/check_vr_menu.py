"""Opt-in live SteamVR regression: exercise the packaged EXE via overlay events.

Run only with permission and an already connected headset. This changes only
Colour Lab's in-memory controls, records evidence, and closes the launched app.
It does not restart SteamVR, save settings, or change driver configuration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import openvr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    exe, output = args.exe.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    process = None
    handle = None
    report = {"exe": str(exe), "exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
              "scope": "Real EXE, GPU and SteamVR; synthetic overlay clicks, not physical input",
              "completed_cycles": 0, "passed": False}
    # Background init requires the already running runtime. No scene restart.
    system = openvr.init(openvr.VRApplication_Background)
    try:
        if not system.isTrackedDeviceConnected(openvr.k_unTrackedDeviceIndex_Hmd):
            raise RuntimeError("Connect the headset before running this manual test.")
        overlay, view = openvr.VROverlay(), openvr.VROverlayView()
        key = "org.steamvrcolourlab.controls.scene"
        try:
            existing = overlay.findOverlay(key)
        except openvr.error_code.OverlayError_UnknownOverlay:
            existing = None
        if existing:
            raise RuntimeError("Close the existing Colour Lab before running this manual test.")
        env = dict(os.environ)
        windows = os.environ["SystemRoot"]
        env["PATH"] = os.pathsep.join([str(Path(windows) / "System32"), windows])
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        with (output / "process.txt").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([str(exe), "--frames", "9000", "--output", str(output / "runs")],
                                       cwd=output, env=env, stdout=log, stderr=subprocess.STDOUT)

            def wait_for(predicate, label, timeout=12):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(f"EXE exited {process.returncode} while waiting for {label}")
                    result = predicate()
                    if result:
                        return result
                    time.sleep(.05)
                raise TimeoutError(label)

            def find_menu():
                try:
                    candidate = overlay.findOverlay(key)
                    if overlay.getOverlayRenderingPid(candidate) != process.pid:
                        raise RuntimeError("Colour Lab overlay belongs to another process.")
                    return candidate
                except openvr.OpenVRError:
                    return None

            handle = wait_for(find_menu, "scene menu")
            event_path = next((output / "runs").glob("*/events.jsonl"))

            def records():
                # The app flushes complete JSON lines; tolerate an in-progress tail.
                rows = event_path.read_text(encoding="utf-8").splitlines()
                return [json.loads(row) for row in rows if row.endswith("}")]

            def post(kind, x=0, y=0):
                if overlay.getOverlayRenderingPid(handle) != process.pid:
                    raise RuntimeError("Refusing to send input to another process.")
                event = openvr.VREvent_t()
                event.eventType = kind
                event.trackedDeviceIndex = openvr.k_unTrackedDeviceIndexInvalid
                event.data.mouse.x, event.data.mouse.y = x, y
                event.data.mouse.button = openvr.VRMouseButton_Left
                event.data.mouse.cursorIndex = 17
                view.postOverlayEvent(handle, event)

            def click(x, y):
                post(openvr.VREvent_MouseMove, x, y)
                post(openvr.VREvent_MouseButtonDown, x, y)
                post(openvr.VREvent_MouseButtonUp, x, y)

            def setting(field, value):
                rows = [row["data"]["settings"] for row in records() if row["event"] == "settings"]
                return rows and rows[-1][field] == value

            for pattern in ("vertical", "radial", "solid", "hue", "atlas"):
                click(640, 408)
                wait_for(lambda p=pattern: setting("pattern", p), "pattern " + pattern)
            click(1055, 488)
            wait_for(lambda: setting("animate", True), "Motion ON")
            time.sleep(1)
            for cycle in range(12):
                click(796, 696)  # Hide menu, through its actual widget action.
                wait_for(lambda: tuple(overlay.getOverlayMouseScale(handle).v) == (360, 96), "compact menu")
                time.sleep(.3)
                click(180, 48)
                wait_for(lambda: tuple(overlay.getOverlayMouseScale(handle).v) == (1280, 800), "full menu")
                time.sleep(.3)
                report["completed_cycles"] += 1
            click(1055, 488)
            wait_for(lambda: setting("animate", False), "Motion OFF")
            post(openvr.VREvent_Quit)
            process.wait(timeout=10)
            all_records = records()
            fatal = [row for row in all_records if row["event"] == "fatal_error"]
            finished = [row["data"] for row in all_records if row["event"] == "finished"]
            report.update(exit_code=process.returncode, finished=finished, fatal_errors=fatal,
                          menu_transitions=sum(row["event"] == "vr_menu" for row in all_records),
                          events=str(event_path))
            if process.returncode != 0 or fatal or not finished or finished[-1]["vr_submitted_frames"] < 100:
                raise RuntimeError("Portable VR regression did not finish cleanly with submitted frames.")
            if report["menu_transitions"] != 24:
                raise RuntimeError("Expected 12 complete hide/open cycles.")
            report["passed"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if process and process.poll() is None:
            # Terminate only the test process this script owns after a failed check.
            process.terminate()
            process.wait(timeout=10)
        openvr.shutdown()
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
