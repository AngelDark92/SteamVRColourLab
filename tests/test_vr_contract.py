"""OpenVR orchestration tests with a fake runtime. NOT a headset integration test."""
import ctypes as C
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from colourlab.core import Settings, identity
from colourlab.vr import VRBridge


class Matrix34(C.Structure):
    _fields_ = [("m", (C.c_float * 4) * 3)]


def matrix(x=0, y=0, z=0):
    out = Matrix34()
    for i in range(3):
        out.m[i][i] = 1
    out.m[0][3], out.m[1][3], out.m[2][3] = x, y, z
    return out


class Pose(C.Structure):
    _fields_ = [("mDeviceToAbsoluteTracking", Matrix34), ("bPoseIsValid", C.c_bool)]


class Event(C.Structure):
    _fields_ = [("eventType", C.c_uint)]


class FocusError(Exception):
    pass


class Runtime:
    def __init__(self):
        self.submissions = []
        self.shutdown_called = False
        self.valid = True
        self.fail = False
        self.pose = matrix(0, 1.6, 0)
        self.module = SimpleNamespace(
            VRApplication_Scene=1, TrackingUniverseStanding=1,
            TextureType_OpenGL=1, ColorSpace_Linear=2, Texture_t=SimpleNamespace,
            TrackedDevicePose_t=Pose, VREvent_t=Event, k_unMaxTrackedDeviceCount=64,
            k_unTrackedDeviceIndex_Hmd=0, init=lambda kind: self,
            VRCompositor=lambda: self, shutdown=self.shutdown,
            error_code=SimpleNamespace(CompositorError_DoNotHaveFocus=FocusError),
        )
    def shutdown(self): self.shutdown_called = True
    def setTrackingSpace(self, space): self.space = space
    def getRecommendedRenderTargetSize(self): return (2048, 2048)
    def getProjectionMatrix(self, eye, near, far): return SimpleNamespace(m=identity())
    def getEyeToHeadTransform(self, eye): return matrix(-.032 if eye == 0 else .032)
    def pollNextEvent(self, event): return False
    def waitGetPoses(self, poses, game):
        poses[0].bPoseIsValid = self.valid
        poses[0].mDeviceToAbsoluteTracking = self.pose
        return poses, None
    def submit(self, eye, texture):
        if self.fail: raise RuntimeError("TextureUsesUnsupportedFormat")
        self.submissions.append((eye, texture.eType, texture.eColorSpace, texture.handle))


class FakeRenderer:
    def __init__(self):
        self.targets, self.draws = [], []
        self.gl = SimpleNamespace(Flush=lambda: None)
    def create_target(self, width, height):
        t = SimpleNamespace(texture=len(self.targets)+1, width=width, height=height)
        self.targets.append(t)
        return t
    def draw(self, target, settings, mvp, seconds):
        self.draws.append((target, settings, mvp, seconds))


class VRContractTests(unittest.TestCase):
    def setUp(self):
        self.runtime = Runtime()
        self.renderer = FakeRenderer()
        self.patch = patch.dict(sys.modules, {"openvr": self.runtime.module})
        self.patch.start()
        self.bridge = VRBridge(self.renderer)
    def tearDown(self):
        self.bridge.close()
        self.patch.stop()

    def test_both_eyes_receive_linear_float_target_handles(self):
        self.assertTrue(self.bridge.render(Settings(), 0))
        self.assertEqual(self.runtime.submissions, [(0, 1, 2, 1), (1, 1, 2, 2)])
        self.assertEqual(self.bridge.submitted_frames, 1)
        self.assertEqual(len(self.renderer.draws), 2)
        self.assertAlmostEqual(self.renderer.draws[0][2][0][3], .032, places=6)
        self.assertAlmostEqual(self.renderer.draws[1][2][0][3], -.032, places=6)

    def test_tracking_invalid_does_not_submit(self):
        self.runtime.valid = False
        self.assertFalse(self.bridge.render(Settings(), 0))
        self.assertEqual(self.runtime.submissions, [])

    def test_rejected_float_texture_does_not_fallback(self):
        self.runtime.fail = True
        with self.assertRaisesRegex(RuntimeError, "No 8-bit fallback"):
            self.bridge.render(Settings(), 0)
        self.assertEqual(len(self.renderer.targets), 2)

    def test_anchor_remains_world_fixed_until_recenter(self):
        self.bridge.render(Settings(), 0)
        self.runtime.pose = matrix(1, 1.6, 0)
        self.bridge.render(Settings(), 0)
        self.assertAlmostEqual(self.bridge.anchor[0][3], 0)
        self.bridge.recenter_pending = True
        self.bridge.render(Settings(), 0)
        self.assertAlmostEqual(self.bridge.anchor[0][3], 1)

    def test_close_shuts_down_runtime(self):
        self.bridge.close()
        self.assertTrue(self.runtime.shutdown_called)
        self.assertFalse(self.bridge.active)


if __name__ == "__main__":
    unittest.main()
