#!/usr/bin/env python3
"""SteamVR Colour Lab entry point. Run --help for desktop/test options."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import logging
import platform
import sys
import time
import traceback
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from colourlab import __version__, shaders
from colourlab.core import MODES, PATTERNS, PRESETS, Settings, apply_preset


def application_home() -> Path:
    """Writable portable data lives next to the EXE, never in _MEIPASS or cwd."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # zipimport's __file__ points *inside* the archive, which is not writable.
    archive = getattr(globals().get("__loader__"), "archive", None)
    return Path(archive or __file__).resolve().parent


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def exception_description(exc: Exception) -> str:
    """OpenVR exceptions often have an empty message but a useful class/code."""
    name = type(exc).__name__
    code = getattr(exc, "error_value", None)
    detail = str(exc).strip()
    return name + (f" (code {code})" if code is not None else "") + (f": {detail}" if detail else "")


def show_fatal_error(args, message: str, log_path: Path):
    """Keep double-click failures visible; automated invocations stay nonblocking."""
    if (not getattr(sys, "frozen", False) or sys.platform != "win32"
            or args.frames or args.self_test or args.desktop):
        return
    try:
        ctypes.windll.user32.MessageBoxW(
            None, f"SteamVR Colour Lab could not continue.\n\n{message}\n\nDiagnostic logs:\n{log_path}",
            "SteamVR Colour Lab — startup/runtime error", 0x10)
    except Exception:
        logging.exception("Could not display the fatal error dialog")


def dimensions(text: str) -> tuple[int, int]:
    try:
        width, height = map(int, text.lower().split("x"))
        if min(width, height) < 256 or max(width, height) > 8192:
            raise ValueError
        return width, height
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use WIDTHxHEIGHT, with dimensions between 256 and 8192.") from exc


class Application:
    def __init__(self, args):
        self.args = args
        self.home = application_home()
        self.settings_dir = args.settings_dir or self.home / "settings"
        self.settings = Settings.load(args.config) if args.config else Settings()
        self.initial_settings = self.settings.to_dict()
        self.running = True
        self.exit_reason = None
        self.window = None
        self.renderer = None
        self.vr = None
        self.vr_retry_at = None
        self.vr_status = "Not connected to SteamVR"
        self.ui = None
        self.dashboard = None
        self.glfw = None
        self.precision_check = {}
        self.metadata = {}
        self.frame_count = 0
        self.animation_start = time.perf_counter()
        self.cycle_start = None
        self.cycle_offset = 0
        self.cycle_step = -1
        self.preset_index = 0
        self.notice = ""
        self.notice_until = 0.0
        self.started_at = utc_now()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.run_dir = args.output / stamp
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.events = (self.run_dir / "events.jsonl").open("a", encoding="utf-8", buffering=1)
        logging.basicConfig(filename=self.run_dir / "application.log", level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s", force=True)
        self.log_event("starting", {"desktop_only": args.desktop, "settings": self.settings.to_dict()})

    def log_event(self, kind, data=None):
        self.events.write(json.dumps({"utc": utc_now(), "event": kind, "data": data or {}}, allow_nan=False) + "\n")

    def initialise(self):
        import glfw
        from colourlab.gl import GL, Renderer
        from colourlab.diagnostics import check_source_precision
        self.glfw = glfw
        glfw.set_error_callback(lambda code, text: logging.warning("GLFW %s: %s", code, text))
        if not glfw.init():
            raise RuntimeError("GLFW could not initialise. A local graphical session and working GPU driver are required.")
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.SAMPLES, 0)
        glfw.window_hint(glfw.SRGB_CAPABLE, glfw.FALSE)
        if self.args.self_test:
            glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
        self.window = glfw.create_window(1100, 640, "SteamVR Colour Lab — desktop preview, NOT a bit-depth verification", None, None)
        if not self.window:
            raise RuntimeError("Could not create an OpenGL 3.3 window. Update the GPU driver; do not use Remote Desktop.")
        glfw.make_context_current(self.window)
        # SteamVR WaitGetPoses paces VR frames; desktop vsync must not throttle it.
        glfw.swap_interval(1 if self.args.desktop else 0)
        glfw.set_key_callback(self.window, self.key)
        gl = GL(glfw.get_proc_address)
        self.renderer = Renderer(gl)
        self.precision_check = check_source_precision(self.renderer)
        self.metadata = {
            "app_version": __version__,
            "python": sys.version,
            "bundled_runtime": bool(getattr(sys, "frozen", False)),
            "platform": platform.platform(),
            "graphics": gl.info(),
            "source_precision_check": self.precision_check,
            "shader_sha256": hashlib.sha256((shaders.VERTEX + shaders.FRAGMENT).encode()).hexdigest(),
            "quantisation": "sRGB-encoded RGB: floor(clamp(s,0,1)*(2^bits-1)+0.5)/(2^bits-1)",
            "submission": "sRGB decode -> linear GL_RGBA16F -> OpenVR ColorSpace_Linear",
            "reference": "No intentional quantisation; still limited by float shader/float16 buffer precision",
            "stream_depth_control": "Not controlled, measured or confirmed by this application",
            "desktop_preview": "Convenience preview only; not a high-bit-depth measurement",
        }
        self.metadata["packages"] = {}
        for package in ("glfw", "openvr", "Pillow"):
            try:
                self.metadata["packages"][package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                self.metadata["packages"][package] = "metadata unavailable"
        self.preview_target = self.renderer.create_target(1100, 640)
        if not self.args.no_ui and not self.args.self_test:
            from colourlab.ui import Controls
            self.ui = Controls(self)
        if not self.args.desktop and not self.args.self_test:
            # Build usable controls before trying a headset that may be offline.
            glfw.poll_events()
            if self.ui:
                self.ui.pump()
            if self.running and not glfw.window_should_close(self.window):
                self.connect_vr()
        else:
            self.vr_status = "DESKTOP ONLY — not connected to SteamVR"
            self.metadata["vr"] = {"status": "not connected; desktop/self-test only"}
        if self.args.self_test:
            # Exercise the shipped font/image dependency too, without opening
            # SteamVR or changing the precision renderer's GPU pipeline.
            from colourlab.dashboard_ui import DashboardUI
            dashboard = DashboardUI(self)
            for page in dashboard.PAGES:
                dashboard.set_page(page)
                image = dashboard.render()
                if image.mode != "RGBA" or image.size != (1280, 800):
                    raise RuntimeError("Dashboard rendering self-test failed.")
            self.metadata["dashboard_render_check"] = "6 RGBA pages rendered; no SteamVR connection"
        self.write_session()
        self.log_event("initialised", self.metadata)
        print("Source precision check:", self.precision_check["unique_red_levels"])
        print("Run logs:", self.run_dir)
        self.animation_start = time.perf_counter()

    def write_session(self):
        (self.run_dir / "session.json").write_text(json.dumps({
            "started_at": self.started_at, "metadata": self.metadata,
            "initial_settings": self.initial_settings}, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    def connect_vr(self):
        """Retry only known temporary headset/startup errors, never runtime Quit."""
        import openvr
        from colourlab.vr import VRBridge
        transient_names = (
            "InitError_Init_HmdNotFound", "InitError_Init_Retry",
            "InitError_Init_HmdNotFoundPresenceFailed", "InitError_Driver_WirelessHmdNotConnected",
        )
        transient_errors = tuple(getattr(openvr.error_code, name) for name in transient_names)
        try:
            self.vr = VRBridge(self.renderer, getattr(self.args, "eye_size", None))
        except transient_errors as exc:
            detail = exception_description(exc)
            self.vr_retry_at = time.perf_counter() + 3.0
            self.vr_status = f"Waiting for headset / SteamVR: {detail}. Connect your headset; retrying every 3 seconds."
            self.metadata["vr"] = {"status": "waiting for headset", "error": detail, "retry_seconds": 3}
            self.log_event("vr_waiting", self.metadata["vr"])
            self.note(self.vr_status)
            if self.window:
                self.glfw.set_window_title(self.window, "SteamVR Colour Lab — waiting for headset / SteamVR")
            self.write_session()
            return False
        self.vr_retry_at = None
        self.metadata["vr"] = self.vr.info()
        # Late connections get the same visible controls as immediate startup.
        from colourlab.dashboard import Dashboard
        self.dashboard = Dashboard(self, self.vr.vr)
        self.metadata["vr_controls"] = {
            "interface": "Visible in-scene VR menu and SteamVR dashboard; native mouse/pointer events",
            "hand_tracking": "Requires pointer/select support from SteamVR and the streaming driver",
            "dashboard_pixels": [self.dashboard.ui.WIDTH, self.dashboard.ui.HEIGHT],
        }
        self.vr_status = "Connected to SteamVR — VR controls are visible in your headset."
        self.note(self.vr_status)
        if self.window:
            self.glfw.set_window_title(self.window, "SteamVR Colour Lab — F1: VR menu | Desktop preview only")
        self.write_session()
        self.log_event("vr_connected", self.metadata["vr"])
        return True

    def note(self, message: str):
        self.notice, self.notice_until = message, time.perf_counter() + 6
        if self.ui:
            self.ui.status.set(message)
        print(message)

    def change(self, settings: Settings, reason: str):
        settings.validate()
        if settings == self.settings:
            return
        self.settings = settings
        # Every change resets the deterministic motion phase.
        self.animation_start = time.perf_counter()
        self.log_event("settings", {"reason": reason, "settings": settings.to_dict(), "motion_phase_reset": True})
        if self.window:
            self.glfw.set_window_title(self.window, f"{MODES[settings.mode]} | {PATTERNS[settings.pattern]} | Desktop preview only")

    def recenter(self):
        if self.vr:
            self.vr.recenter_pending = True
        if self.dashboard:
            self.dashboard.recenter_pending = True
        self.animation_start = time.perf_counter()
        self.log_event("recenter_requested")
        self.note("Panel will recenter at the next valid headset pose; motion phase reset.")

    def show_vr_menu(self):
        if self.dashboard:
            self.dashboard.set_expanded(True)
            self.dashboard.recenter_pending = True

    def toggle_vr_menu(self):
        if self.dashboard:
            self.dashboard.set_expanded(not self.dashboard.expanded)

    def set_cycle(self, enabled: bool):
        self.cycle_start = time.perf_counter() if enabled else None
        self.cycle_offset, self.cycle_step = self.preset_index, -1
        self.log_event("auto_cycle", {"enabled": enabled, "interval_seconds": 8, "starting_preset": self.preset_index})

    def next_preset(self, step: int):
        names = list(PRESETS)
        self.preset_index = (self.preset_index + step) % len(names)
        name = names[self.preset_index]
        self.change(apply_preset(self.settings, name), "preset " + name)
        if self.ui:
            self.ui.preset.set(name)
            self.ui.refresh()

    def settings_files(self):
        """VR file picker: local snapshots, bundled examples and replay reports."""
        paths = list(self.settings_dir.glob("*.json"))
        paths += list((self.home / "examples").glob("*.json"))
        paths += list(self.args.output.glob("*/settings-*.json"))
        return sorted(set(paths), key=lambda path: (str(path.parent), path.name), reverse=True)

    def save_settings_snapshot(self):
        self.settings_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = self.settings_dir / ("settings-" + stamp + ".json")
        self.settings.save(path)
        self.log_event("settings_saved", {"file": str(path)})
        self.note("Saved settings: " + path.name)
        return path

    def save_report(self, *, apply_ui=True):
        if apply_ui and self.ui and not self.ui.apply():
            return
        stamp = datetime.now().strftime("%H%M%S-%f")
        path = self.run_dir / ("report-" + stamp + ".json")
        data = {
            "utc": utc_now(), "metadata": self.metadata, "settings": self.settings.to_dict(),
            "motion_seconds": time.perf_counter() - self.animation_start if self.settings.animate else 0,
            "application_frames": self.frame_count,
            "vr_frames_submitted": self.vr.submitted_frames if self.vr else 0,
            "vr_status": self.vr.last_submit if self.vr else self.vr_status,
            "last_headset_pose": self.vr.last_pose if self.vr else None,
            "panel_anchor": self.vr.anchor if self.vr else None,
            "automatic_colour_cycle_enabled": self.cycle_start is not None,
            "stream_depth_requested_is_user_entered": True,
            "stream_depth_confirmed": False,
        }
        try:
            path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            # This separate file can be passed straight to --config on another PC.
            config_path = self.run_dir / ("settings-" + stamp + ".json")
            self.settings.save(config_path)
            self.log_event("report", {"report_file": path.name, "settings_file": config_path.name})
            self.note("Saved report + replayable settings: " + str(self.run_dir))
        except OSError as exc:
            self.note("Could not save report: " + str(exc))

    def key(self, window, key, scancode, action, mods):
        g = self.glfw
        if action != g.PRESS:
            return
        if key == g.KEY_ESCAPE:
            self.stop("escape")
            return
        if key == g.KEY_F1:
            self.toggle_vr_menu()
            return
        if key == g.KEY_R:
            self.recenter()
            return
        if key == g.KEY_F5:
            self.save_report()
            return
        if key in (g.KEY_RIGHT, g.KEY_LEFT):
            self.next_preset(1 if key == g.KEY_RIGHT else -1)
            return
        s = self.settings
        mode_keys = {g.KEY_1: "8bit", g.KEY_2: "10bit", g.KEY_3: "reference", g.KEY_4: "compare", g.KEY_5: "three"}
        if key in mode_keys:
            s = replace(s, mode=mode_keys[key])
        elif key == g.KEY_SPACE:
            s = replace(s, mode="10bit" if s.mode == "8bit" else "8bit")
        elif key == g.KEY_L:
            s = replace(s, labels=not s.labels)
        elif key == g.KEY_X:
            s = replace(s, swap=not s.swap)
        elif key == g.KEY_M:
            s = replace(s, animate=not s.animate)
        elif key == g.KEY_P:
            names = list(PATTERNS)
            s = replace(s, pattern=names[(names.index(s.pattern) + 1) % len(names)])
        else:
            return
        self.change(s, "keyboard")
        if self.ui:
            self.ui.refresh()

    def stop(self, reason="user_requested"):
        self.running = False
        self.exit_reason = reason

    def run(self):
        self.initialise()
        if self.args.self_test:
            print(json.dumps(self.precision_check, indent=2))
            print(self.metadata["dashboard_render_check"])
            return
        next_ui, next_preview = 0.0, 0.0
        start, next_status = time.perf_counter(), 0.0
        status_frames, status_start = 0, start
        fps = 0.0
        while self.running and not self.glfw.window_should_close(self.window):
            now = time.perf_counter()
            self.glfw.poll_events()
            if self.ui and now >= next_ui:
                self.ui.pump()
                next_ui = now + 1/30
            if not self.running:
                break
            if self.vr is None and self.vr_retry_at is not None and now >= self.vr_retry_at:
                self.connect_vr()
            if self.cycle_start is not None:
                step = int((now - self.cycle_start) // 8)
                if step != self.cycle_step:
                    self.cycle_step = step
                    self.preset_index = (self.cycle_offset + step - 1) % len(PRESETS)
                    self.next_preset(1)
            # Poll independently of scene focus/tracking. SteamVR dashboards
            # can own input while the scene compositor reports no focus.
            if self.dashboard:
                self.dashboard.pump()
            if not self.running:
                break
            seconds = time.perf_counter() - self.animation_start if self.settings.animate else 0.0
            if self.vr:
                if not self.vr.render(self.settings, seconds):
                    # No-focus/tracking errors need not be frame-paced by VR.
                    time.sleep(.005)
                if self.vr.wants_quit:
                    self.exit_reason = "runtime_quit"
                    break
            if now >= next_preview:
                self.renderer.draw(self.preview_target, self.settings, seconds=seconds)
                width, height = self.glfw.get_framebuffer_size(self.window)
                self.renderer.preview(self.preview_target, width, height)
                self.glfw.swap_buffers(self.window)
                next_preview = now + 1/30
            elif not self.vr:
                time.sleep(.002)
            self.frame_count += 1
            status_frames += 1
            if now >= next_status:
                self.renderer.gl.check("frame rendering")
                elapsed = now - status_start
                if elapsed > 0:
                    fps = status_frames / elapsed
                status_frames, status_start = 0, now
                if self.ui and now > self.notice_until:
                    text = self.vr.last_submit if self.vr else self.vr_status
                    self.ui.status.set(f"{text}\n{fps:.0f} loop iterations/s • Source check: 256 / 1024 levels passed")
                next_status = now + 1
            if self.args.frames and self.frame_count >= self.args.frames:
                self.exit_reason = "frame_limit"
                break
        self.log_event("finished", {"application_frames": self.frame_count,
                                    "vr_submitted_frames": self.vr.submitted_frames if self.vr else 0,
                                    "exit_reason": self.exit_reason or "preview_window_closed"})

    def close(self):
        # Cleanup ordering matters: SteamVR -> GL resources -> context/window.
        for obj in (self.dashboard, self.vr, self.renderer, self.ui):
            if obj:
                try:
                    obj.close()
                except Exception:
                    logging.exception("Shutdown error")
        if self.glfw:
            if self.window:
                self.glfw.destroy_window(self.window)
            self.glfw.terminate()
        if self.events:
            self.events.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Native SteamVR colour and source-precision test. No change to streaming settings.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--desktop", action="store_true", help="Preview without connecting to SteamVR; not an end-to-end test")
    parser.add_argument("--config", type=Path, help="Load a saved settings JSON")
    parser.add_argument("--eye-size", type=dimensions, help="Override per-eye render dimensions, e.g. 2048x2048; otherwise use SteamVR recommendation")
    parser.add_argument("--output", type=Path, default=application_home() / "runs", help="Folder for local session logs and reports; defaults beside the executable")
    parser.add_argument("--settings-dir", type=Path, help="VR save/load folder; defaults to settings beside the executable")
    parser.add_argument("--no-ui", action="store_true", help="Hide desktop controls; VR dashboard and preview shortcuts remain available")
    parser.add_argument("--self-test", action="store_true", help="Validate actual source buffer precision and exit; no SteamVR required")
    parser.add_argument("--frames", type=int, default=0, help="Exit after N loop iterations (smoke tests); 0 runs until closed")
    args = parser.parse_args(argv)
    if args.frames < 0:
        parser.error("--frames must be nonnegative")
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        parser.error("Use the 64-bit application build (or 64-bit Python for source development).")
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required for source development.")
    app = None
    message = None
    try:
        app = Application(args)
        app.run()
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        message = exception_description(exc)
        try:
            logging.exception("Fatal application error")
            print("\nERROR:", message, file=sys.stderr)
            traceback.print_exc()
            if app:
                app.log_event("fatal_error", {"message": message})
                print("Diagnostic logs:", app.run_dir, file=sys.stderr)
        except Exception:
            # Disk-full/logging failures must not hide the original error dialog.
            pass
    finally:
        if app:
            try:
                app.close()
            except Exception:
                if message is None:
                    raise
                # A failing log flush during cleanup must not replace the error.
    # Release SteamVR and graphics before waiting for a desktop acknowledgement.
    show_fatal_error(args, message, app.run_dir if app else args.output)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
