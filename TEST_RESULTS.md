# Validation results — 0.2.1

85 automated tests passed, including 4 real-GPU tests. Live headset testing
confirmed the new in-scene menu, correct click positions and removal of flashing.
A subsequent hide-menu texture resize crash was fixed by keeping the submitted
graphics dimensions unchanged for both the full menu and compact button. The
final portable EXE passed 12 live SteamVR hide/open cycles with Motion ON (818
submitted frames, exit 0, no errors); the user then confirmed motion, hide/open,
readability and aligned clicks in the headset. A relocated ZIP copy passed GPU
self-test and desktop launch with external Python excluded. Startup now waits
for temporary headset connection errors and reports permanent errors visibly. See
`validation/SCENE-MENU-FIX-20260925.md` for evidence and remaining limits.

---

# Historical validation — 0.2.0

**60 automated tests passed on Windows.** The portable ZIP built successfully;
a relocated copy passed GPU source-precision, dashboard-rendering and desktop
Tk/GLFW checks with installed Python excluded from its search environment.

Detailed Windows portable and dashboard validation is recorded in
`validation/PORTABLE-VR-VALIDATION.md`. Headset interaction has not yet been
validated; mocked overlay events do not establish live controller or hand input.

---

# Historical validation results — 0.1.0 (original Linux source build)

Validation was performed on the supplied source, not on a substitute renderer.
The raw output is included under `validation/`.

## Executed checks

**33 automated tests passed.**

The host was Linux x86-64 with CPython 3.13.5. Real OpenGL rendering used
Mesa 25.0.7 llvmpipe (software renderer), GLSL 4.50, and a surfaceless EGL
context. Tk control tests used a real Tk window under Xvfb.

| Check | Observed result |
| --- | --- |
| Actual GL texture format | GL_RGBA16F, 16 bits for each RGBA channel. |
| Full-range 8-bit source ramp | 256 distinct red-channel values in a 4096-pixel row. |
| Full-range 10-bit source ramp | 1024 distinct red-channel values in the same row. |
| Float reference ramp | 4010 distinct values in the same row. Float16 storage is finite precision. |
| Maximum sRGB round-trip error | Below 0.000316 in each source mode (test threshold: 0.0006). |
| Colours | All 48 presets exercised against expected quantised values. |
| Pattern combinations | All 6 patterns × 6 modes × labels on/off rendered; all values finite and within range. |
| Comparison order | Verified two-way, three-way, swapped order, and repeated vertical ramp domains. |
| Dithering | Repeated rendering was identical; values stayed bounded and averages close to the requested solid input. |
| Motion | Time changed animated patterns; a static pattern ignored elapsed time. |
| Settings and colour math | Validation, JSON round trips, sRGB conversion, code-level counts, half-up quantisation, hue endpoints and transforms passed. |
| Desktop controls | Fractional RGB, invalid input handling, HSV / atlas controls, preset navigation index, and independent streaming metadata passed. |
| Mocked OpenVR integration | Eye handles and ColorSpace_Linear tags, stereo transforms, world anchoring, recentering, invalid tracking, shutdown and float-texture rejection passed. |
| Python source compilation | All app, library, test and build-tool files compiled successfully. |
| Packaged .pyz entry point | `--help` worked. Invalid negative `--frames` correctly returned exit status 2. |

## Not executed / not established

No Windows computer, SteamVR runtime, hardware OpenGL GPU or headset was
available for integration validation. OpenVR orchestration tests use a fake
runtime; they do not establish compositor format acceptance, headset visibility,
tracking comfort, stereo appearance or real-time performance.

The complete app loop through the GLFW Python binding was not launched here:
its package was not preinstalled and dependency downloads were unavailable in
the sandbox. The real renderer was instead executed through EGL, and the UI
was exercised directly in Tk. No Windows batch file or optional PyInstaller
`.exe` build was executed. The package contains no bundled Windows executable.

There was no measurement of streaming bit depth, encoder output, Wi-Fi,
headset decoder, panel, optics, or visually perceived banding. Passing the
source-buffer test only establishes precision before those downstream stages.

## First hardware validation

Run `self_test_windows.bat` on the test PC, then `start_windows.bat` with
SteamVR and the Wi-Fi headset connected. Confirm the float-buffer check passes,
that both eyes show the full panel, and that status reports successful float
texture submissions. Recenter and compare Space-key A/B before testing streaming
settings. Save and share the report plus settings, noting the app is a 0.1.0
experimental build. There is deliberately no silent 8-bit fallback.
