"""Pointer UI and actual pyopenvr marshaling with a fake overlay runtime.

These checks never initialize SteamVR and do not claim headset input proof.
"""
import ctypes
import json
import unittest
from collections import defaultdict, deque
from dataclasses import fields, replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import openvr

from colourlab.core import MODES, PATTERNS, PRESETS, Settings, identity
from colourlab.dashboard import Dashboard
from colourlab.dashboard_ui import DashboardUI
from tests.test_portable import TemporaryApplicationTests


def point(ui, key):
    button = next(button for button in ui.buttons if button.key == key)
    left, top, right, bottom = button.rect
    return (left + right) / 2, (top + bottom) / 2


def click(ui, key):
    x, y = point(ui, key)
    ui.pointer(x, y, True)
    ui.pointer(x, y, False)


def enter(ui, field, text):
    click(ui, field)
    for char in text:
        click(ui, "key:" + char)
    click(ui, "apply")


class DashboardControlTests(TemporaryApplicationTests):
    def setUp(self):
        super().setUp()
        self.ui = DashboardUI(self.app)

    def page(self, name):
        click(self.ui, "page:" + name)

    def test_every_settings_field_can_be_changed_using_pointer_controls(self):
        original = self.app.settings.to_dict()
        click(self.ui, "mode:10bit")
        click(self.ui, "pattern")
        for key in ("labels", "swap", "animate"):
            click(self.ui, key)
        self.page("RGB")
        for key in ("start_rgb", "end_rgb"):
            for component in range(3):
                click(self.ui, f"{key}.{component}:plus")
        self.page("Hue")
        for key in ("hue", "saturation", "value_min", "value_max"):
            click(self.ui, key + ":plus")
        self.page("Geometry")
        for key in ("panel_width", "panel_height", "panel_distance"):
            click(self.ui, key + ":plus")
        self.page("Session")
        click(self.ui, "stream_depth_requested")
        for key in ("streaming_app", "codec", "bitrate_mbps", "notes"):
            enter(self.ui, key, "test123")
        current = self.app.settings.to_dict()
        changed = {key for key in current if original[key] != current[key]}
        self.assertEqual(changed, {field.name for field in fields(Settings)})

    def test_all_source_modes_and_patterns_are_reachable(self):
        for mode in MODES:
            click(self.ui, "mode:" + mode)
            self.assertEqual(self.app.settings.mode, mode)
        seen = set()
        for _ in PATTERNS:
            click(self.ui, "pattern")
            seen.add(self.app.settings.pattern)
        self.assertEqual(seen, set(PATTERNS))

    def test_numeric_keypad_keeps_fractional_precision(self):
        self.page("RGB")
        text = "0.012345678901234567"
        enter(self.ui, "start_rgb.0", text)
        self.assertEqual(self.app.settings.start_rgb[0], float(text))
        # Merely inspecting a saved number must not re-quantize it.
        click(self.ui, "start_rgb.0")
        click(self.ui, "apply")
        self.assertEqual(self.app.settings.start_rgb[0], float(text))

    def test_invalid_numeric_edit_and_cancel_preserve_live_configuration(self):
        self.page("RGB")
        original = self.app.settings.to_dict()
        for text in ("-", "1e999", "-1", "2"):
            with self.subTest(text=text):
                enter(self.ui, "start_rgb.0", text)
                self.assertIsNotNone(self.ui.editor)
                self.assertTrue(self.ui.message.startswith("Input error:"))
                self.assertEqual(self.app.settings.to_dict(), original)
                click(self.ui, "cancel")
                self.assertIsNone(self.ui.editor)
        click(self.ui, "start_rgb.0")
        click(self.ui, "key:7")
        click(self.ui, "cancel")
        self.assertEqual(self.app.settings.to_dict(), original)

    def test_session_metadata_and_presets_preserve_independent_source_choices(self):
        self.app.change(replace(self.app.settings, mode="dither8", panel_distance=4.2), "test")
        self.ui.sync()
        self.page("Session")
        click(self.ui, "stream_depth_requested")
        enter(self.ui, "codec", "hevc")
        self.assertEqual(self.app.settings.mode, "dither8")
        self.assertEqual(self.app.settings.panel_distance, 4.2)
        self.page("RGB")
        click(self.ui, "preset:next")
        self.assertEqual(self.app.settings.start_rgb, list(PRESETS.values())[1][0])
        self.assertEqual(self.app.settings.codec, "hevc")
        self.assertEqual(self.app.settings.stream_depth_requested, "8")
        self.assertEqual(self.app.settings.mode, "dither8")
        self.assertEqual(self.app.settings.panel_distance, 4.2)

    def test_append_keeps_existing_notes_and_sync_keeps_local_feedback(self):
        self.app.change(replace(self.app.settings, notes="original"), "test")
        self.app.note("Old status")
        self.ui.sync()
        self.page("Session")
        click(self.ui, "notes")
        click(self.ui, "append")
        click(self.ui, "space")
        click(self.ui, "key:a")
        click(self.ui, "apply")
        self.ui.sync()
        self.assertEqual(self.app.settings.notes, "original a")
        self.assertEqual(self.ui.message, "Applied.")

    def test_snapshot_load_and_report_ignore_stale_desktop_draft(self):
        desktop = SimpleNamespace(apply=Mock(side_effect=AssertionError("Stale draft applied")),
                                  refresh=Mock(), cycle=SimpleNamespace(set=Mock()),
                                  status=SimpleNamespace(set=Mock()), close=Mock())
        self.app.ui = desktop
        self.app.change(replace(self.app.settings, notes="saved in VR", mode="10bit"), "test")
        wanted = self.app.settings.to_dict()
        self.page("Files")
        click(self.ui, "save")
        saved = list(self.app.settings_dir.glob("*.json"))
        self.assertEqual(len(saved), 1)
        self.app.change(replace(self.app.settings, mode="8bit"), "test")
        self.app.set_cycle(True)
        click(self.ui, "file:" + str(saved[0]))
        self.assertIsNone(self.app.cycle_start)
        self.assertEqual(self.app.settings.to_dict(), wanted)
        click(self.ui, "report")
        report = next(self.app.run_dir.glob("report-*.json"))
        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["settings"],
                         json.loads(json.dumps(wanted)))
        desktop.apply.assert_not_called()

    def test_invalid_snapshot_keeps_settings_and_active_cycle(self):
        invalid = self.home / "invalid.json"
        invalid.write_text('{"panel_distance": -100}', encoding="utf-8")
        original = self.app.settings.to_dict()
        self.app.set_cycle(True)
        with self.assertRaises(ValueError):
            self.ui.load(invalid)
        self.assertIsNotNone(self.app.cycle_start)
        self.assertEqual(self.app.settings.to_dict(), original)

    def test_release_outside_and_focus_cancellation_do_not_activate(self):
        x, y = point(self.ui, "mode:10bit")
        self.ui.pointer(x, y, True)
        self.ui.pointer(-10, -10, False)
        self.assertEqual(self.app.settings.mode, "compare")
        self.ui.pointer(x, y, True)
        self.ui.cancel_pointer()
        self.ui.pointer(x, y, False)
        self.assertEqual(self.app.settings.mode, "compare")
        self.assertIsNone(self.ui.hit(float("nan"), 0))

    def test_recenter_cycle_and_exit_are_available_in_vr(self):
        self.app.vr = SimpleNamespace(recenter_pending=False, close=Mock())
        click(self.ui, "recenter")
        self.assertTrue(self.app.vr.recenter_pending)
        click(self.ui, "cycle")
        self.assertIsNotNone(self.app.cycle_start)
        click(self.ui, "quit")
        self.assertTrue(self.app.running)
        click(self.ui, "quit:cancel")
        click(self.ui, "quit")
        click(self.ui, "quit:confirm")
        self.assertFalse(self.app.running)


class FakeOverlayTexture:
    """Only the GPU is faked here; OpenVR still marshals its actual Texture_t."""

    def __init__(self, vr, name):
        self.texture = vr.Texture_t()
        self.texture.handle = name
        self.texture.eType = vr.TextureType_OpenGL
        self.texture.eColorSpace = vr.ColorSpace_Gamma
        self.image = None
        self.closed = 0

    def update(self, image):
        if self.image is not None and image.size != self.image.size:
            raise AssertionError("A submitted overlay texture must never be resized")
        self.image = image.copy()
        return self.texture

    def close(self):
        self.closed += 1


class FakeOverlay:
    """Use installed pyopenvr wrappers for texture and event marshalling."""
    pollNextOverlayEvent = openvr.IVROverlay.pollNextOverlayEvent
    setOverlayTexture = openvr.IVROverlay.setOverlayTexture
    setOverlayTexelAspect = openvr.IVROverlay.setOverlayTexelAspect
    setOverlayMouseScale = openvr.IVROverlay.setOverlayMouseScale
    setOverlayTransformAbsolute = openvr.IVROverlay.setOverlayTransformAbsolute
    setOverlayTransformTrackedDeviceRelative = openvr.IVROverlay.setOverlayTransformTrackedDeviceRelative
    setOverlayFlag = openvr.IVROverlay.setOverlayFlag

    def __init__(self):
        self.queues = defaultdict(deque)
        self.uploads, self.destroyed, self.calls = [], [], []
        self.visible = defaultdict(bool)
        self.scales, self.input_methods, self.widths, self.transforms = {}, {}, {}, {}
        self.texture_sources = {}
        self.submitted_sizes, self.texel_aspects = {}, {}
        self.polls = 0
        self.fail_width = False
        self.function_table = SimpleNamespace(pollNextOverlayEvent=self.poll_native,
                                               setOverlayTexture=self.texture_native,
                                               setOverlayTexelAspect=self.aspect_native,
                                               setOverlayMouseScale=self.scale_native,
                                               setOverlayTransformAbsolute=self.absolute_native,
                                               setOverlayTransformTrackedDeviceRelative=self.relative_native,
                                               setOverlayFlag=self.flag_native)

    def createDashboardOverlay(self, key, name):
        self.calls.append(("create", key, name))
        return 41, 42

    def createOverlay(self, key, name):
        self.calls.append(("create_scene", key, name))
        return 43

    def setOverlayWidthInMeters(self, handle, width):
        if self.fail_width:
            raise RuntimeError("init failed")
        self.widths[handle] = width

    def setOverlayInputMethod(self, handle, method):
        self.input_methods[handle] = method

    def setOverlayTextureColorSpace(self, handle, colour):
        self.calls.append(("colour", handle, colour))

    def scale_native(self, handle, pointer):
        scale = ctypes.cast(pointer, ctypes.POINTER(openvr.HmdVector2_t)).contents
        self.scales[handle] = tuple(scale.v)
        return 0

    def flag_native(self, handle, flag, enabled):
        self.calls.append(("flag", handle, flag, enabled))
        return 0

    def aspect_native(self, handle, aspect):
        self.texel_aspects[handle] = aspect
        return 0

    def transform_native(self, kind, handle, origin, pointer):
        transform = ctypes.cast(pointer, ctypes.POINTER(openvr.HmdMatrix34_t)).contents
        self.transforms[handle] = (kind, origin, [list(row) for row in transform.m])
        self.calls.append((kind, handle, origin))
        return 0

    def absolute_native(self, handle, origin, pointer):
        return self.transform_native("absolute", handle, origin, pointer)

    def relative_native(self, handle, device, pointer):
        return self.transform_native("relative", handle, device, pointer)

    def texture_native(self, handle, pointer):
        texture = ctypes.cast(pointer, ctypes.POINTER(openvr.Texture_t)).contents
        image = self.texture_sources[texture.handle].image
        if self.submitted_sizes.setdefault(handle, image.size) != image.size:
            raise AssertionError("Changing submitted dimensions on an existing overlay fails in SteamVR")
        self.uploads.append((handle, image.width, image.height, 4, image.tobytes(),
                             texture.handle, texture.eType, texture.eColorSpace))
        return 0

    def poll_native(self, handle, pointer, size):
        assert size == ctypes.sizeof(openvr.VREvent_t)
        self.polls += 1
        if not self.queues[handle]:
            return False
        ctypes.memmove(pointer, ctypes.byref(self.queues[handle].popleft()), size)
        return True

    def isOverlayVisible(self, handle):
        return self.visible[handle]

    def showOverlay(self, handle):
        self.visible[handle] = True
        self.calls.append(("show_scene", handle))

    def showDashboard(self, key):
        self.calls.append(("show", key))

    def destroyOverlay(self, handle):
        if handle == 42:
            raise AssertionError("SteamVR owns the dashboard thumbnail")
        self.destroyed.append(handle)

    def event(self, kind, x=0, y=0, device=1, cursor=0, handle=41, button=None):
        event = openvr.VREvent_t()
        event.eventType = kind
        event.trackedDeviceIndex = device
        if kind == openvr.VREvent_FocusLeave:
            event.data.overlay.overlayHandle = handle
            event.data.overlay.cursorIndex = cursor
        else:
            event.data.mouse.x, event.data.mouse.y = x, y
            event.data.mouse.cursorIndex = cursor
            event.data.mouse.button = openvr.VRMouseButton_Left if button is None else button
        self.queues[handle].append(event)


class DashboardTransportTests(TemporaryApplicationTests):
    def setUp(self):
        super().setUp()
        self.overlay = FakeOverlay()
        self.overlay_patch = patch.object(openvr, "VROverlay", return_value=self.overlay)
        self.overlay_patch.start()
        self.addCleanup(self.overlay_patch.stop)
        self.app.renderer = SimpleNamespace(gl=SimpleNamespace(Flush=Mock(), check=Mock()), close=Mock())
        texture_patch = patch("colourlab.dashboard.OverlayTexture", side_effect=self.new_texture)
        texture_patch.start()
        self.addCleanup(texture_patch.stop)
        self.dashboard = Dashboard(self.app, openvr)
        self.app.dashboard = self.dashboard
        self.addCleanup(self.dashboard.close)

    def new_texture(self, gl, vr):
        self.assertIs(gl, self.app.renderer.gl)
        name = 101 + len(self.overlay.texture_sources)
        texture = FakeOverlayTexture(vr, name)
        self.overlay.texture_sources[name] = texture
        return texture

    def send_click(self, key, device=1, cursor=0, handle=41):
        x, y = point(self.dashboard.ui, key)
        # Live SteamVR maps this GL submission to top-left widget coordinates.
        # The image upload flips storage rows; input must not be flipped again.
        self.overlay.event(openvr.VREvent_MouseButtonDown, x, y, device, cursor, handle)
        self.overlay.event(openvr.VREvent_MouseButtonUp, x, y, device, cursor, handle)
        self.dashboard.pump()

    def test_native_opengl_texture_and_mouse_scale_match_ui(self):
        for handle in (41, 43):
            with self.subTest(handle=handle):
                self.assertEqual(self.overlay.scales[handle], (1280, 800))
                self.assertEqual(self.overlay.input_methods[handle], openvr.VROverlayInputMethod_Mouse)
                main = next(upload for upload in self.overlay.uploads if upload[0] == handle)
                self.assertEqual(main[1:4], (1280, 800, 4))
                self.assertEqual(len(main[4]), 1280 * 800 * 4)
                self.assertEqual(main[4][:4], bytes((16, 25, 37, 255)))
                texture = self.dashboard.textures[handle]
                self.assertEqual(texture.image.tobytes(), main[4])
                self.assertEqual(main[5:], (texture.texture.handle, openvr.TextureType_OpenGL,
                                            openvr.ColorSpace_Gamma))

    def test_setting_changes_reuse_native_texture_handles_without_image_reload(self):
        handles = {handle: texture.texture.handle for handle, texture in self.dashboard.textures.items()}
        self.send_click("mode:10bit", handle=43)
        self.dashboard.next_update = 0
        self.send_click("mode:8bit", handle=41)
        self.assertEqual(len(self.overlay.texture_sources), 3)
        self.assertEqual({handle: texture.texture.handle for handle, texture in self.dashboard.textures.items()}, handles)
        for overlay_handle in (41, 43):
            updates = [upload for upload in self.overlay.uploads if upload[0] == overlay_handle]
            self.assertGreaterEqual(len(updates), 3)
            self.assertEqual({upload[5] for upload in updates}, {handles[overlay_handle]})
            self.assertNotEqual(updates[0][4], updates[1][4])
        self.app.renderer.gl.Flush.assert_called()

    def test_scene_controls_start_visible_and_interactive_without_opening_dashboard(self):
        self.assertTrue(self.overlay.isOverlayVisible(43))
        self.assertFalse(self.overlay.isOverlayVisible(41))
        self.assertNotIn(("show", Dashboard.KEY), self.overlay.calls)
        self.assertIn(("flag", 43, openvr.VROverlayFlags_MakeOverlaysInteractiveIfVisible, True),
                      self.overlay.calls)
        kind, device, transform = self.overlay.transforms[43]
        self.assertEqual((kind, device), ("relative", openvr.k_unTrackedDeviceIndex_Hmd))
        self.assertAlmostEqual(transform[2][3], -1.8)
        self.assertEqual(self.overlay.widths[43], 1.8)

    def test_empty_tuple_event_queue_exits_and_does_not_upload_clean_ui(self):
        count = len(self.overlay.uploads)
        self.dashboard.pump()
        self.assertEqual(self.overlay.polls, 3)
        self.assertEqual(len(self.overlay.uploads), count)

    def test_native_top_left_coordinates_and_either_hand_activate_controls(self):
        self.send_click("mode:10bit", device=1, cursor=0, handle=43)
        self.assertEqual(self.app.settings.mode, "10bit")
        self.send_click("mode:8bit", device=2, cursor=1)
        self.assertEqual(self.app.settings.mode, "8bit")

    def test_top_navigation_and_bottom_action_use_direct_native_y_coordinates(self):
        self.assertLess(point(self.dashboard.ui, "page:RGB")[1], self.dashboard.ui.HEIGHT / 2)
        self.send_click("page:RGB", handle=43)
        self.assertEqual(self.dashboard.ui.page, "RGB")
        self.assertGreater(point(self.dashboard.ui, "hide_menu")[1], self.dashboard.ui.HEIGHT / 2)
        self.send_click("hide_menu", handle=43)
        self.assertFalse(self.dashboard.expanded)

    def test_other_surface_cannot_release_same_controller_owned_click(self):
        x, y = point(self.dashboard.ui, "mode:10bit")
        self.overlay.event(openvr.VREvent_MouseButtonDown, x, y, handle=41)
        self.dashboard.pump()
        self.overlay.event(openvr.VREvent_MouseButtonUp, x, y, handle=43)
        self.dashboard.pump()
        self.assertEqual(self.app.settings.mode, "compare")
        self.assertEqual(self.dashboard.pointer_owner, (41, 1, 0))
        self.overlay.event(openvr.VREvent_MouseButtonUp, x, y, handle=41)
        self.dashboard.pump()
        self.assertEqual(self.app.settings.mode, "10bit")

    def test_other_hand_cannot_release_owned_click(self):
        x, y = point(self.dashboard.ui, "mode:10bit")
        self.overlay.event(openvr.VREvent_MouseButtonDown, x, y, device=1, cursor=0)
        self.overlay.event(openvr.VREvent_MouseButtonUp, x, y, device=2, cursor=1)
        self.dashboard.pump()
        self.assertEqual(self.app.settings.mode, "compare")
        self.overlay.event(openvr.VREvent_MouseButtonUp, x, y, device=1, cursor=0)
        self.dashboard.pump()
        self.assertEqual(self.app.settings.mode, "10bit")

    def test_focus_loss_and_hidden_overlay_cancel_pending_click(self):
        x, y = point(self.dashboard.ui, "mode:10bit")
        for event_kind in (openvr.VREvent_FocusLeave, openvr.VREvent_OverlayHidden):
            with self.subTest(event=event_kind):
                self.overlay.event(openvr.VREvent_MouseButtonDown, x, y)
                self.overlay.event(event_kind)
                self.overlay.event(openvr.VREvent_MouseButtonUp, x, y)
                self.dashboard.pump()
                self.assertEqual(self.app.settings.mode, "compare")
                self.assertIsNone(self.dashboard.pointer_owner)

    def test_unrelated_surface_device_or_cursor_focus_leave_keeps_owned_press(self):
        for handle, device, cursor in ((41, 1, 7), (43, 2, 7), (43, 1, 8)):
            with self.subTest(handle=handle, device=device, cursor=cursor):
                self.app.change(replace(self.app.settings, mode="compare"), "test")
                self.dashboard.ui.sync()
                x, y = point(self.dashboard.ui, "mode:10bit")
                self.overlay.event(openvr.VREvent_MouseButtonDown, x, y, device=1, cursor=7, handle=43)
                self.dashboard.pump()
                self.overlay.event(openvr.VREvent_FocusLeave, device=device, cursor=cursor, handle=handle)
                self.dashboard.pump()
                self.assertEqual(self.dashboard.pointer_owner, (43, 1, 7))
                self.overlay.event(openvr.VREvent_MouseButtonUp, x, y, device=1, cursor=7, handle=43)
                self.dashboard.pump()
                self.assertEqual(self.app.settings.mode, "10bit")

    def test_owned_focus_leave_uses_overlay_cursor_field_and_cancels_press(self):
        x, y = point(self.dashboard.ui, "mode:10bit")
        self.overlay.event(openvr.VREvent_MouseButtonDown, x, y, device=1, cursor=7, handle=43)
        self.overlay.event(openvr.VREvent_FocusLeave, device=1, cursor=7, handle=43)
        self.overlay.event(openvr.VREvent_MouseButtonUp, x, y, device=1, cursor=7, handle=43)
        self.dashboard.pump()
        self.assertEqual(self.app.settings.mode, "compare")
        self.assertIsNone(self.dashboard.pointer_owner)

    def test_dirty_hidden_ui_is_uploaded_when_visible(self):
        count = len(self.overlay.uploads)
        self.overlay.visible[41] = self.overlay.visible[43] = False
        self.send_click("mode:10bit")
        self.assertEqual(len(self.overlay.uploads), count)
        self.overlay.visible[43] = True
        self.dashboard.pump()
        self.assertEqual(len(self.overlay.uploads), count + 2)
        self.dashboard.pump()
        self.assertEqual(len(self.overlay.uploads), count + 2)

    def test_hide_menu_leaves_compact_native_button_and_select_reopens_it(self):
        self.send_click("hide_menu", handle=43)
        self.assertFalse(self.dashboard.expanded)
        self.assertTrue(self.overlay.isOverlayVisible(43))
        self.assertFalse(self.overlay.isOverlayVisible(41))
        self.assertEqual(self.overlay.scales[43], (360, 96))
        self.assertEqual(self.overlay.scales[41], (1280, 800))
        self.assertEqual(self.overlay.widths[43], .45)
        self.assertEqual(self.overlay.uploads[-1][0:4], (43, 1280, 800, 4))
        self.assertAlmostEqual(self.overlay.texel_aspects[43] * (1280 / 800), 360 / 96)
        self.overlay.event(openvr.VREvent_MouseButtonDown, 180, 48, handle=43)
        self.overlay.event(openvr.VREvent_MouseButtonUp, 180, 48, handle=43)
        self.dashboard.pump()
        self.assertTrue(self.dashboard.expanded)
        self.assertEqual(self.overlay.scales[43], (1280, 800))
        self.assertEqual(self.overlay.uploads[-1][0:4], (43, 1280, 800, 4))
        self.assertEqual(self.overlay.texel_aspects[43], 1.0)
        self.assertIsNone(self.dashboard.pointer_owner)
        self.assertTrue(self.dashboard.recenter_pending)

    def test_compact_button_requires_press_and_release_inside_same_surface(self):
        self.dashboard.set_expanded(False)
        self.overlay.event(openvr.VREvent_MouseButtonUp, 180, 48, handle=43)
        self.dashboard.pump()
        self.assertFalse(self.dashboard.expanded)
        self.overlay.event(openvr.VREvent_MouseButtonDown, 180, 48, handle=43)
        self.overlay.event(openvr.VREvent_MouseButtonUp, -10, 48, handle=43)
        self.dashboard.pump()
        self.assertFalse(self.dashboard.expanded)

    def test_repeated_hide_reopen_keeps_overlay_dimensions_and_native_texture_names_constant(self):
        scene = self.dashboard.textures[43]
        # Match the reported sequence: enable motion, then hide and reopen.
        self.send_click("animate", handle=43)
        self.assertTrue(self.app.settings.animate)
        for cycle in range(5):
            with self.subTest(cycle=cycle):
                self.send_click("hide_menu", handle=43)
                self.assertFalse(self.dashboard.expanded)
                self.assertIs(self.dashboard.textures[43], scene)
                compact_pixels = self.overlay.uploads[-1][4]
                self.assertEqual(self.overlay.uploads[-1][0:4], (43, 1280, 800, 4))
                self.assertEqual(self.overlay.uploads[-1][5], scene.texture.handle)
                self.assertAlmostEqual(self.overlay.texel_aspects[43] * (1280 / 800), 360 / 96)
                self.assertEqual(self.overlay.scales[43], (360, 96))
                self.overlay.event(openvr.VREvent_MouseButtonDown, 180, 48, handle=43)
                self.overlay.event(openvr.VREvent_MouseButtonUp, 180, 48, handle=43)
                self.dashboard.pump()
                self.assertTrue(self.dashboard.expanded)
                self.assertIs(self.dashboard.textures[43], scene)
                self.assertEqual(self.overlay.uploads[-1][5], scene.texture.handle)
                self.assertNotEqual(self.overlay.uploads[-1][4], compact_pixels)
                self.assertEqual(self.overlay.texel_aspects[43], 1.0)
                self.assertEqual(self.overlay.scales[43], (1280, 800))
                self.assertEqual(len(self.overlay.texture_sources), 3)
                self.assertTrue(self.app.settings.animate)
        scene_uploads = [upload for upload in self.overlay.uploads if upload[0] == 43]
        for upload in scene_uploads:
            self.assertEqual(upload[1:3], (1280, 800))
            self.assertEqual(upload[5], scene.texture.handle)
        textures = list(self.dashboard.textures.values())
        self.assertTrue(all(texture.closed == 0 for texture in textures))
        self.dashboard.close()
        self.dashboard.close()
        self.assertEqual(self.overlay.destroyed, [43, 41])
        self.assertTrue(all(texture.closed == 1 for texture in textures))
        self.assertFalse(self.dashboard.textures)

    def test_first_pose_anchors_controls_in_world_and_recenter_uses_latest_pose(self):
        pose = identity()
        pose[1][3] = 1.6
        self.app.vr = SimpleNamespace(last_pose=pose, recenter_pending=False, close=Mock())
        self.dashboard.pump()
        kind, origin, transform = self.overlay.transforms[43]
        self.assertEqual((kind, origin), ("absolute", openvr.TrackingUniverseStanding))
        self.assertAlmostEqual(transform[1][3], 1.55)
        self.assertAlmostEqual(transform[2][3], -1.8)
        self.app.vr.last_pose[0][3] = 2.0
        self.dashboard.pump()
        self.assertEqual(self.dashboard.anchor[0][3], 0.0)
        self.assertEqual(self.overlay.transforms[43][2], transform)
        self.app.recenter()
        self.dashboard.pump()
        self.assertAlmostEqual(self.overlay.transforms[43][2][0][3], 2.0)
        self.assertFalse(self.dashboard.recenter_pending)

    def test_image_loaded_and_scene_input_status_are_recorded(self):
        self.overlay.event(openvr.VREvent_ImageLoaded, handle=43)
        self.overlay.event(openvr.VREvent_ImageLoaded, handle=41)
        self.overlay.event(openvr.VREvent_MouseMove, 5, 5, handle=43)
        self.send_click("mode:10bit", handle=43)
        events = [json.loads(line) for line in (self.app.run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        surfaces = {event["data"]["surface"] for event in events if event["event"] == "vr_menu_image_loaded"}
        self.assertEqual(surfaces, {"scene", "dashboard"})
        status = next(event["data"] for event in events if event["event"] == "vr_menu_status")
        self.assertEqual(status, {"scene_visible": True, "dashboard_visible": False, "expanded": True,
                                  "pointer_moves": 1, "select_releases": 1})

    def test_runtime_image_failure_is_reported(self):
        self.overlay.event(openvr.VREvent_ImageFailed)
        with self.assertRaisesRegex(RuntimeError, "dashboard image"):
            self.dashboard.pump()

    def test_thumbnail_quit_is_drained(self):
        self.overlay.event(openvr.VREvent_Quit, handle=42)
        self.dashboard.pump()
        self.assertFalse(self.app.running)

    def test_close_releases_scene_and_dashboard_once_without_destroying_thumbnail(self):
        textures = list(self.dashboard.textures.values())
        self.dashboard.close()
        self.dashboard.close()
        self.assertCountEqual(self.overlay.destroyed, [41, 43])
        self.assertEqual(self.dashboard.thumbnail, 0)
        self.assertFalse(self.dashboard.textures)
        self.assertTrue(all(texture.closed == 1 for texture in textures))

    def test_initialization_failure_cleans_up_partial_dashboard(self):
        self.overlay.fail_width = True
        with self.assertRaisesRegex(RuntimeError, "init failed"):
            Dashboard(self.app, openvr)
        self.assertCountEqual(self.overlay.destroyed, [41, 43])


if __name__ == "__main__":
    unittest.main()
