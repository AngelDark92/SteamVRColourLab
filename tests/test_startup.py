"""Recoverable startup and visible fatal errors; never connects to SteamVR."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import openvr

import app as entry
from tests.test_portable import TemporaryApplicationTests


class StartupRecoveryTests(TemporaryApplicationTests):
    def setUp(self):
        super().setUp()
        self.app.args.desktop = False
        self.app.args.self_test = False
        self.app.args.frames = 4
        self.app.args.eye_size = None
        self.app.renderer = Mock()
        self.app.window = object()
        self.app.preview_target = object()
        self.app.glfw = Mock()
        self.app.glfw.window_should_close.return_value = False
        self.app.glfw.get_framebuffer_size.return_value = (1100, 640)
        self.app.ui = Mock()

    def bridge(self):
        bridge = Mock(submitted_frames=0, wants_quit=False)
        bridge.info.return_value = {"api": "fake OpenVR scene application"}
        bridge.render.return_value = True
        return bridge

    def dashboard(self):
        return Mock(ui=SimpleNamespace(WIDTH=1280, HEIGHT=800), expanded=True)

    def events(self):
        return [json.loads(line) for line in (self.app.run_dir / "events.jsonl").read_text().splitlines()]

    def test_initialise_creates_preview_and_pumps_controls_before_headset_attempt(self):
        self.app.args.no_ui = False
        glfw, renderer, controls, gl = self.app.glfw, self.app.renderer, self.app.ui, Mock()
        glfw.create_window.return_value = self.app.window
        gl.info.return_value = {"renderer": "fake GPU"}
        renderer.create_target.return_value = self.app.preview_target
        order = []
        renderer.create_target.side_effect = lambda *args: order.append("preview") or self.app.preview_target
        controls.pump.side_effect = lambda: order.append("controls pumped")

        def disconnected(*args):
            order.append("headset attempt")
            raise openvr.error_code.InitError_Driver_WirelessHmdNotConnected(215)

        with patch.dict(entry.sys.modules, {"glfw": glfw}), \
             patch("colourlab.gl.GL", return_value=gl), \
             patch("colourlab.gl.Renderer", return_value=renderer), \
             patch("colourlab.diagnostics.check_source_precision", return_value={"unique_red_levels": [256, 1024]}), \
             patch("colourlab.ui.Controls", return_value=controls), \
             patch("colourlab.vr.VRBridge", side_effect=disconnected):
            self.app.initialise()
        self.assertEqual(order, ["preview", "controls pumped", "headset attempt"])
        self.assertTrue(self.app.running)
        self.assertIsNone(self.app.vr)

    def test_transient_disconnect_retries_then_attaches_controls_and_updates_session(self):
        failure = openvr.error_code.InitError_Driver_WirelessHmdNotConnected(215)
        bridge, dashboard = self.bridge(), self.dashboard()
        with patch("colourlab.vr.VRBridge", side_effect=[failure, bridge]) as constructor, \
             patch("colourlab.dashboard.Dashboard", return_value=dashboard) as menu, \
             patch.object(entry.time, "perf_counter", return_value=10):
            self.assertFalse(self.app.connect_vr())
            self.assertIsNone(self.app.vr)
            self.assertEqual(self.app.vr_retry_at, 13)
            self.assertIn("InitError_Driver_WirelessHmdNotConnected (code 215)", self.app.vr_status)
            waiting = json.loads((self.app.run_dir / "session.json").read_text())
            self.assertEqual(waiting["metadata"]["vr"]["status"], "waiting for headset")
            self.assertTrue(self.app.connect_vr())
        self.assertEqual(constructor.call_count, 2)
        self.assertIsNone(self.app.vr_retry_at)
        self.assertIs(self.app.vr, bridge)
        self.assertIs(self.app.dashboard, dashboard)
        menu.assert_called_once_with(self.app, bridge.vr)
        session = json.loads((self.app.run_dir / "session.json").read_text())
        self.assertEqual(session["metadata"]["vr"], bridge.info())
        self.assertIn("in-scene", session["metadata"]["vr_controls"]["interface"])
        self.assertEqual([event["event"] for event in self.events()], ["starting", "vr_waiting", "vr_connected"])

    def test_only_known_temporary_errors_are_retried(self):
        for error_type, code in (
            (openvr.error_code.InitError_Init_HmdNotFound, 108),
            (openvr.error_code.InitError_Init_Retry, 115),
            (openvr.error_code.InitError_Init_HmdNotFoundPresenceFailed, 126),
        ):
            with self.subTest(code=code), patch("colourlab.vr.VRBridge", side_effect=error_type(code)):
                self.assertFalse(self.app.connect_vr())
        failure = openvr.error_code.InitError_Init_VRClientDLLNotFound(102)
        with patch("colourlab.vr.VRBridge", side_effect=failure), \
             patch("colourlab.dashboard.Dashboard") as menu:
            with self.assertRaises(type(failure)):
                self.app.connect_vr()
        menu.assert_not_called()

    def test_waiting_keeps_preview_controls_and_finite_frame_limit_responsive(self):
        failure = openvr.error_code.InitError_Init_HmdNotFound(108)
        self.app.initialise = Mock(side_effect=self.app.connect_vr)
        with patch("colourlab.vr.VRBridge", side_effect=failure) as constructor, \
             patch.object(entry.time, "perf_counter", return_value=10), \
             patch.object(entry.time, "sleep"):
            self.app.run()
        constructor.assert_called_once()
        self.app.ui.pump.assert_called_once()
        self.assertEqual(self.app.glfw.poll_events.call_count, 4)
        self.app.renderer.draw.assert_called_once()
        self.assertEqual(self.app.frame_count, 4)
        self.assertEqual(self.events()[-1]["data"]["exit_reason"], "frame_limit")

    def test_loop_connects_after_retry_deadline_and_does_not_reconnect_after_quit(self):
        bridge, dashboard = self.bridge(), self.dashboard()
        bridge.wants_quit = True
        self.app.vr_retry_at = 13
        self.app.initialise = Mock()
        with patch("colourlab.vr.VRBridge", return_value=bridge) as constructor, \
             patch("colourlab.dashboard.Dashboard", return_value=dashboard), \
             patch.object(entry.time, "perf_counter", return_value=13):
            self.app.run()
        constructor.assert_called_once()
        self.app.ui.pump.assert_called_once()
        dashboard.pump.assert_called_once()
        self.assertEqual(self.events()[-1]["data"]["exit_reason"], "runtime_quit")

    def test_recenter_and_menu_shortcuts_target_the_in_scene_controls(self):
        self.app.vr = self.bridge()
        self.app.dashboard = self.dashboard()
        self.app.dashboard.recenter_pending = False
        self.app.show_vr_menu()
        self.app.dashboard.set_expanded.assert_called_once_with(True)
        self.assertTrue(self.app.dashboard.recenter_pending)
        self.app.toggle_vr_menu()
        self.app.dashboard.set_expanded.assert_called_with(False)
        self.app.dashboard.recenter_pending = False
        self.app.recenter()
        self.assertTrue(self.app.vr.recenter_pending)
        self.assertTrue(self.app.dashboard.recenter_pending)


class FatalErrorTests(unittest.TestCase):
    def test_empty_openvr_error_has_class_and_numeric_code(self):
        failure = openvr.error_code.InitError_Driver_WirelessHmdNotConnected(215)
        self.assertEqual(entry.exception_description(failure),
                         "InitError_Driver_WirelessHmdNotConnected (code 215)")

    def test_frozen_interactive_failure_is_visible_after_cleanup(self):
        app = Mock(run_dir="C:/Colour Lab/runs/example")
        app.run.side_effect = openvr.error_code.InitError_Init_VRClientDLLNotFound(102)
        actions = []
        app.close.side_effect = lambda: actions.append("closed")
        windll = Mock()
        windll.user32.MessageBoxW.side_effect = lambda *args: actions.append("shown")
        with patch.object(entry, "Application", return_value=app), \
             patch.object(entry.sys, "frozen", True, create=True), \
             patch.object(entry.sys, "platform", "win32"), \
             patch.object(entry.ctypes, "windll", windll, create=True), \
             patch.object(entry.logging, "exception"), patch.object(entry.traceback, "print_exc"):
            self.assertEqual(entry.main([]), 1)
        self.assertEqual(actions, ["closed", "shown"])
        message = windll.user32.MessageBoxW.call_args.args[1]
        self.assertIn("InitError_Init_VRClientDLLNotFound (code 102)", message)
        self.assertIn(str(app.run_dir), message)

    def test_automated_failures_never_show_blocking_dialog(self):
        for argv in (["--frames", "1"], ["--self-test"], ["--desktop"]):
            with self.subTest(argv=argv):
                app = Mock()
                app.run.side_effect = RuntimeError("failure")
                windll = Mock()
                with patch.object(entry, "Application", return_value=app), \
                     patch.object(entry.sys, "frozen", True, create=True), \
                     patch.object(entry.sys, "platform", "win32"), \
                     patch.object(entry.ctypes, "windll", windll, create=True), \
                     patch.object(entry.logging, "exception"), patch.object(entry.traceback, "print_exc"):
                    self.assertEqual(entry.main(argv), 1)
                windll.user32.MessageBoxW.assert_not_called()
                app.close.assert_called_once()

    def test_failed_fatal_logging_preserves_original_error_and_dialog_after_cleanup(self):
        for cleanup_fails in (False, True):
            with self.subTest(cleanup_fails=cleanup_fails):
                app = Mock(run_dir="C:/Colour Lab/runs/example")
                app.run.side_effect = OSError("original startup failure")
                app.log_event.side_effect = OSError("disk full writing event")
                actions = []

                def close():
                    actions.append("closed")
                    if cleanup_fails:
                        raise OSError("disk full flushing log")

                app.close.side_effect = close
                windll = Mock()
                windll.user32.MessageBoxW.side_effect = lambda *args: actions.append("shown")
                with patch.object(entry, "Application", return_value=app), \
                     patch.object(entry.sys, "frozen", True, create=True), \
                     patch.object(entry.sys, "platform", "win32"), \
                     patch.object(entry.ctypes, "windll", windll, create=True), \
                     patch.object(entry.logging, "exception"), patch.object(entry.traceback, "print_exc"):
                    self.assertEqual(entry.main([]), 1)
                self.assertEqual(actions, ["closed", "shown"])
                app.log_event.assert_called_once_with("fatal_error", {"message": "OSError: original startup failure"})
                message = windll.user32.MessageBoxW.call_args.args[1]
                self.assertIn("OSError: original startup failure", message)
                self.assertNotIn("disk full", message)


if __name__ == "__main__":
    unittest.main()
