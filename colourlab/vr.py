"""SteamVR scene submission through OpenVR. No desktop capture is involved."""
from __future__ import annotations

from .core import from_openvr, identity, matmul, panel_model, rigid_inverse


class VRBridge:
    def __init__(self, renderer, eye_size=None):
        import openvr  # The desktop-only mode does not load an OpenVR runtime.
        self.vr = openvr
        self.renderer = renderer
        self.active = False
        self.anchor = None
        self.last_pose = None
        self.recenter_pending = True
        self.submitted_frames = 0
        self.last_submit = "not submitted"
        self.last_error = ""
        self.wants_quit = False
        try:
            self.system = openvr.init(openvr.VRApplication_Scene)
            self.active = True
            self.compositor = openvr.VRCompositor()
            self.compositor.setTrackingSpace(openvr.TrackingUniverseStanding)
            self.recommended_size = tuple(self.system.getRecommendedRenderTargetSize())
            size = eye_size or self.recommended_size
            self.targets = [renderer.create_target(*size) for _ in range(2)]
            self.textures = []
            for target in self.targets:
                texture = openvr.Texture_t()
                texture.handle = target.texture
                texture.eType = openvr.TextureType_OpenGL
                texture.eColorSpace = openvr.ColorSpace_Linear
                self.textures.append(texture)
            self.poses = (openvr.TrackedDevicePose_t * openvr.k_unMaxTrackedDeviceCount)()
            self.event = openvr.VREvent_t()
            self.update_eye_matrices()
        except Exception:
            self.close()
            raise

    def update_eye_matrices(self):
        self.projection = [from_openvr(self.system.getProjectionMatrix(eye, 0.05, 100.0)) for eye in (0, 1)]
        self.eye_view = [rigid_inverse(from_openvr(self.system.getEyeToHeadTransform(eye))) for eye in (0, 1)]

    def info(self):
        vr = self.vr
        def property_value(name, kind="String"):
            try:
                prop = getattr(vr, name)
                value = getattr(self.system, f"get{kind}TrackedDeviceProperty")(vr.k_unTrackedDeviceIndex_Hmd, prop)
                return value.decode("utf-8", "replace") if isinstance(value, bytes) else value
            except Exception:
                return "unavailable"
        return {
            "api": "OpenVR scene application",
            "headset_model": property_value("Prop_ModelNumber_String"),
            "tracking_system": property_value("Prop_TrackingSystemName_String"),
            "refresh_hz": property_value("Prop_DisplayFrequency_Float", "Float"),
            "recommended_eye_size_at_launch": self.recommended_size,
            "actual_eye_size": [self.targets[0].width, self.targets[0].height],
            "submitted_format": "GL_RGBA16F",
            "submitted_colour_space": "ColorSpace_Linear (sRGB-decoded values)",
            "actual_stream_bit_depth": "unknown; not exposed or inferred by this app",
            "actual_stream_bitrate": "unknown; record independently",
            "panel_native_bit_depth": "unknown; not inferred",
        }

    def poll(self):
        vr = self.vr
        while self.system.pollNextEvent(self.event):
            kind = self.event.eventType
            if kind == getattr(vr, "VREvent_Quit", 700):
                self.wants_quit = True
            elif kind in (getattr(vr, "VREvent_IpdChanged", 105), getattr(vr, "VREvent_LensDistortionChanged", 110)):
                self.update_eye_matrices()

    def render(self, settings, seconds: float) -> bool:
        vr = self.vr
        self.poll()
        if self.wants_quit:
            return False
        try:
            self.poses, _ = self.compositor.waitGetPoses(self.poses, None)
        except vr.error_code.CompositorError_DoNotHaveFocus:
            self.last_submit = "paused: another VR application has focus"
            return False
        pose = self.poses[vr.k_unTrackedDeviceIndex_Hmd]
        if not pose.bPoseIsValid:
            self.last_submit = "waiting for valid headset tracking"
            return False
        self.last_pose = from_openvr(pose.mDeviceToAbsoluteTracking)
        if self.recenter_pending or self.anchor is None:
            self.anchor = [row[:] for row in self.last_pose]
            self.recenter_pending = False
        model = panel_model(self.anchor, settings)
        head_view = rigid_inverse(self.last_pose)
        for eye, target in enumerate(self.targets):
            view = matmul(self.eye_view[eye], head_view)
            mvp = matmul(self.projection[eye], matmul(view, model))
            self.renderer.draw(target, settings, mvp, seconds)
        self.renderer.gl.Flush()
        try:
            # Both eyes receive the whole panel. Comparison does NOT assign
            # 8-bit to one eye and 10-bit to the other (which would cause rivalry).
            for eye, texture in enumerate(self.textures):
                self.compositor.submit(eye, texture)
        except vr.error_code.CompositorError_DoNotHaveFocus:
            self.last_submit = "paused: another VR application has focus"
            return False
        except Exception as exc:
            self.last_error = repr(exc)
            raise RuntimeError(
                "SteamVR rejected the floating-point eye texture. No 8-bit fallback was used. "
                "Confirm that Python runs on the same GPU as SteamVR and that your driver is current. "
                f"Original compositor error: {exc}"
            ) from exc
        # OpenVR may itself queue GL work; flush again after Submit.
        self.renderer.gl.Flush()
        self.submitted_frames += 1
        self.last_submit = "RGBA16F submitted; stream depth remains unverified"
        return True

    def close(self):
        if self.active:
            # The runtime must release its references before GL textures disappear.
            self.vr.shutdown()
            self.active = False
