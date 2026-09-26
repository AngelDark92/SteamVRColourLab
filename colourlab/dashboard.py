"""Visible in-scene VR controls plus an optional SteamVR dashboard tab.

SteamVR owns controller/hand laser pointers and select bindings. The scene
overlay explicitly enables laser input even when the dashboard is closed.
"""
from __future__ import annotations

import logging
import time

from PIL import Image, ImageDraw

from .dashboard_ui import DashboardUI
from .core import identity, matmul
from .overlay_texture import OverlayTexture


class Dashboard:
    KEY = "org.steamvrcolourlab.controls"

    def __init__(self, app, vr):
        self.app, self.vr = app, vr
        self.overlay = vr.VROverlay()
        self.handle = self.thumbnail = self.scene = 0
        self.textures = {}
        self.next_update = 0.0
        self.pointer_owner = None
        self.expanded = True
        self.compact_pressed = False
        self.anchor = None
        self.recenter_pending = True
        self.moves = self.clicks = 0
        self._last_status = None
        self.next_status = 0.0
        self.ui = DashboardUI(app)
        self.event = vr.VREvent_t()
        try:
            self.handle, self.thumbnail = self.overlay.createDashboardOverlay(self.KEY, "Colour Lab")
            self.scene = self.overlay.createOverlay(self.KEY + ".scene", "Colour Lab VR controls")
            self.overlay.setOverlayWidthInMeters(self.handle, 2.0)
            for handle in (self.handle, self.scene):
                self.overlay.setOverlayInputMethod(handle, vr.VROverlayInputMethod_Mouse)
                self.mouse_scale(handle, self.ui.WIDTH, self.ui.HEIGHT)
                self.overlay.setOverlayTextureColorSpace(handle, vr.ColorSpace_Gamma)
            self.overlay.setOverlayFlag(self.scene, vr.VROverlayFlags_MakeOverlaysInteractiveIfVisible, True)
            self.overlay.setOverlayTextureColorSpace(self.thumbnail, vr.ColorSpace_Gamma)
            icon = Image.new("RGBA", (256, 256), "#101925")
            draw = ImageDraw.Draw(icon)
            for i, colour in enumerate(("#65d8c5", "#77a7ff", "#e5abff")):
                draw.rounded_rectangle((32, 36 + i*64, 224, 84 + i*64), radius=8, fill=colour)
            self.upload(self.thumbnail, icon)
            self.ui.sync()
            image = self.ui.render()
            self.upload(self.handle, image)
            self.upload(self.scene, image)
            self.position_scene()
            self.overlay.showOverlay(self.scene)
            # Do not open the dashboard during the scene-app transition: the
            # runtime can immediately close it again. Our GUI is in the scene.
        except Exception:
            self.close()
            raise

    def mouse_scale(self, handle, width, height):
        scale = self.vr.HmdVector2_t()
        scale.v[0], scale.v[1] = width, height
        self.overlay.setOverlayMouseScale(handle, scale)

    def position_scene(self):
        local = identity()
        local[1][3] = -.05 if self.expanded else -1.0
        local[2][3] = -1.8
        world = matmul(self.anchor, local) if self.anchor is not None else local
        transform = self.vr.HmdMatrix34_t()
        for row in range(3):
            for col in range(4):
                transform.m[row][col] = world[row][col]
        if self.anchor is None:
            self.overlay.setOverlayTransformTrackedDeviceRelative(self.scene, self.vr.k_unTrackedDeviceIndex_Hmd, transform)
        else:
            self.overlay.setOverlayTransformAbsolute(self.scene, self.vr.TrackingUniverseStanding, transform)
        self.overlay.setOverlayWidthInMeters(self.scene, 1.8 if self.expanded else .45)
        # Physical aspect follows the logical button, while GPU storage stays
        # fixed: SteamVR's GL import cannot safely change an overlay's size.
        aspect = 1.0 if self.expanded else (360 / 96) / (self.ui.WIDTH / self.ui.HEIGHT)
        self.overlay.setOverlayTexelAspect(self.scene, aspect)

    def set_expanded(self, expanded):
        self.expanded = expanded
        self.ui.cancel_pointer()
        self.pointer_owner = None
        self.compact_pressed = False
        self.mouse_scale(self.scene, self.ui.WIDTH if expanded else 360, self.ui.HEIGHT if expanded else 96)
        self.position_scene()
        self.ui.dirty = True
        # Commit collapse/expand immediately, before processing another click.
        self.refresh_images()
        self.overlay.showOverlay(self.scene)
        self.app.log_event("vr_menu", {"expanded": expanded})

    def refresh_images(self):
        image = self.ui.render()
        self.upload(self.handle, image)
        if self.expanded:
            self.upload(self.scene, image)
        else:
            compact = Image.new("RGBA", (360, 96), "#101925")
            draw = ImageDraw.Draw(compact)
            draw.rounded_rectangle((3, 3, 357, 93), radius=14, fill="#176861", outline="#65d8c5", width=3)
            draw.text((180, 45), "OPEN OPTIONS", font=self.ui.title, anchor="mm", fill="#f4f9ff")
            # Never change the submitted dimensions of this overlay, even by
            # swapping GL names. Texel aspect restores the compact proportions.
            self.upload(self.scene, compact.resize((self.ui.WIDTH, self.ui.HEIGHT), Image.Resampling.LANCZOS))

    def status(self):
        return {"scene_visible": bool(self.overlay.isOverlayVisible(self.scene)),
                "dashboard_visible": bool(self.overlay.isOverlayVisible(self.handle)),
                "expanded": self.expanded, "pointer_moves": self.moves, "select_releases": self.clicks}

    def upload(self, handle, image):
        # Each overlay retains one fixed-size GL resource for its lifetime.
        if handle not in self.textures:
            self.textures[handle] = OverlayTexture(self.app.renderer.gl, self.vr)
        texture = self.textures[handle].update(image)
        self.overlay.setOverlayTexture(handle, texture)
        self.app.renderer.gl.Flush()
        self.app.renderer.gl.check("SteamVR overlay texture submission")

    def pump(self):
        vr = self.vr
        self.ui.sync()
        pose = self.app.vr.last_pose if self.app.vr else None
        if self.recenter_pending and pose is not None:
            self.anchor = [row[:] for row in pose]
            self.recenter_pending = False
            self.position_scene()
        # Drain both owned queues, but bound work if the runtime is flooding us.
        for handle in (self.scene, self.handle, self.thumbnail):
            for _ in range(256):
                available, event = self.overlay.pollNextOverlayEvent(handle, self.event)
                if not available:
                    break
                kind = event.eventType
                if kind == vr.VREvent_Quit:
                    self.app.stop("runtime_quit")
                elif kind == vr.VREvent_ImageFailed:
                    raise RuntimeError("SteamVR could not load the Colour Lab dashboard image.")
                elif kind == vr.VREvent_ImageLoaded:
                    self.app.log_event("vr_menu_image_loaded", {"surface": "scene" if handle == self.scene else "dashboard"})
                elif handle in (self.handle, self.scene):
                    if kind in (vr.VREvent_OverlayHidden, vr.VREvent_FocusLeave):
                        leaving_owner = (handle, event.trackedDeviceIndex, event.data.overlay.cursorIndex)
                        owns_press = self.pointer_owner is None or (
                            self.pointer_owner[0] == handle if kind == vr.VREvent_OverlayHidden
                            else self.pointer_owner == leaving_owner)
                        if owns_press:
                            self.ui.cancel_pointer()
                            self.pointer_owner = None
                            self.compact_pressed = False
                    elif kind == vr.VREvent_OverlayShown:
                        self.ui.dirty = True
                    elif kind in (vr.VREvent_MouseMove, vr.VREvent_MouseButtonDown, vr.VREvent_MouseButtonUp):
                        mouse = event.data.mouse
                        # SteamVR maps mouse coordinates through the submitted
                        # OpenGL texture orientation. Our bottom-up GPU upload
                        # already gives top-left widget coordinates here. A
                        # second Y flip mirrored clicks in the live headset.
                        compact = handle == self.scene and not self.expanded
                        x, y = mouse.x, mouse.y
                        # Do not let one hand release the other hand's press.
                        owner = (handle, event.trackedDeviceIndex, mouse.cursorIndex)
                        if self.pointer_owner is not None and owner != self.pointer_owner:
                            continue
                        if kind == vr.VREvent_MouseMove:
                            self.moves += 1
                            if not compact:
                                self.ui.move(x, y)
                        elif mouse.button == vr.VRMouseButton_Left:
                            down = kind == vr.VREvent_MouseButtonDown
                            if down:
                                self.pointer_owner = owner
                            if compact:
                                inside = 0 <= x < 360 and 0 <= y < 96
                                if down:
                                    self.compact_pressed = inside
                                elif self.compact_pressed and inside:
                                    self.set_expanded(True)
                                    self.recenter_pending = True
                                if not down:
                                    self.compact_pressed = False
                            else:
                                self.ui.pointer(x, y, down)
                            if not down:
                                self.clicks += 1
                                self.pointer_owner = None
        now = time.perf_counter()
        if self.ui.dirty and now >= self.next_update and (self.overlay.isOverlayVisible(self.scene) or self.overlay.isOverlayVisible(self.handle)):
            self.refresh_images()
            self.next_update = now + 1/30
        if now >= self.next_status:
            status = self.status()
            if status != self._last_status:
                self.app.log_event("vr_menu_status", status)
                self._last_status = status
            self.next_status = now + 2

    def close(self):
        # SteamVR owns the dashboard thumbnail. Destroying it directly raises
        # ThumbnailCantBeDestroyed; destroying its parent releases both.
        for name in ("scene", "handle"):
            handle = getattr(self, name)
            if handle:
                try:
                    self.overlay.destroyOverlay(handle)
                except Exception:
                    logging.exception("Could not destroy dashboard %s", name)
                setattr(self, name, 0)
        self.thumbnail = 0
        for texture in self.textures.values():
            texture.close()
        self.textures.clear()
