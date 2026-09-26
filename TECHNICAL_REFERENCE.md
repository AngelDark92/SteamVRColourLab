# SteamVR Colour Lab — technical reference

[← Quick start](README.md) · [Controls](#controls-inside-vr) · [Testing guide](#a-repeatable-streaming-test) · [Rendering details](#source-precision-and-important-limitations) · [Builds](#automatic-github-builds-and-versions)

Complete operating instructions, test methods, implementation details and developer references.

An independent utility for comparing **8-bit and 10-bit source quantisation**
through SteamVR, with repeatable settings and controls inside VR.

## Portable Windows package

Extract `dist/SteamVRColourLab-Windows-x64.zip` to a writable local folder and
run **SteamVRColourLab.exe** (or `start_windows.bat`). Keep the entire extracted
folder together, including `_internal`. The package includes Python, Tcl/Tk,
OpenVR, GLFW and Pillow: **no Python installation, pip, internet access or
administrator rights are needed to run it**. SteamVR and a working OpenGL 3.3
GPU driver are still required. It is a Windows x64 build.

Start SteamVR and connect the headset with your usual streaming application,
then launch Colour Lab. Stop other VR scene applications. The **VR options menu
appears directly in front of you inside the scene**. Point at it with your
controller/hand pointer and select. There is no need to open SteamVR's dashboard.
Desktop controls and a preview remain available too.

If the wireless headset is not ready, the app stays open and retries connection
every 3 seconds. Fatal errors in the portable EXE show a dialog with the error
class/code and log folder. The batch launcher also keeps a failed exit visible.
SteamVR requesting shutdown still closes Colour Lab and records `runtime_quit`.

`preview_windows.bat` runs without contacting SteamVR. `self_test_windows.bat`
checks actual OpenGL source-buffer precision without a headset. Neither is an
end-to-end streaming test. Normal startup runs the same precision check.

This app uses OpenVR directly; no change to the system OpenXR runtime is needed.
It does not capture the desktop or a browser to produce the headset test image.

## Controls inside VR

Point at a control and select it with your controller trigger or hand-select
action. The scene overlay explicitly enables SteamVR laser-pointer interaction
while the dashboard is closed. The app consumes overlay pointer events, without
hard-coded controller models or app-specific button bindings. **Hand tracking
works when SteamVR and your streaming driver provide a dashboard hand pointer
and select/pinch action.** A driver exposing only skeleton bones cannot supply
those clicks. If your hands cannot operate SteamVR's own dashboard, this app
cannot create that missing system input. Live interaction coverage is recorded in `TEST_RESULTS.md`; other input drivers
still need validation.

All application settings and actions are available in the VR menu (and the optional Colour Lab dashboard tab):

- **Source:** all 6 source modes, pattern, labels, swap, motion, position-matched
  8/10-bit A/B and automatic preset cycling.
- **RGB:** previous/next across all 48 presets, precise fractional start/end
  components, +/- steps and direct numeric entry.
- **Hue:** hue, saturation, minimum/maximum HSV values, generate endpoints and
  show the 12-colour atlas.
- **Geometry:** physical width, height and distance; Recenter is also available
  from every main page. Face the test direction before selecting it.
- **Session:** requested stream depth, streaming app, codec, bitrate and notes.
  These record conditions; they do not change SteamVR or streaming settings.
- **Files:** save a timestamped settings snapshot and load any saved snapshot,
  bundled example or settings file from a previous run report. Copy external
  settings JSON files into the portable `settings` folder to list them here.
  Loading a file stops automatic cycling to preserve the loaded configuration.
- **Save run report** and **Exit** are available on every main page. Exit asks
  for confirmation inside VR.

Select any numeric value to open the VR keypad. Text fields use an in-panel
keyboard. The first typed key replaces the current value; Apply commits and
Cancel leaves it unchanged. Use Keep text / append to extend an existing entry.
Invalid input leaves the last valid settings intact.
No desktop text fields, colour picker or file dialogs are required from VR.
The desktop colour picker remains a convenience alternative to numeric/HSV entry.

Select **Hide menu** before judging banding. A small **OPEN OPTIONS** button
below the test panel restores it from your headset. The menu stays fixed where
it was placed; Recenter also moves it in front of your current head pose. The
desktop **Show VR controls (F1)** button is a recovery option if you look away.
The optional Colour Lab tab also remains in the SteamVR dashboard.

The menu uses persistent GPU textures; highlights and setting edits update
existing texture pixels instead of asking SteamVR to reload a full raw image.
Its conventional UI pixels remain separate from the procedural float test
image and cannot establish source or stream precision.

Reports and saved snapshots stay in `runs` and `settings` beside the executable,
independent of the launcher's working directory. Settings are saved explicitly;
startup uses defaults unless `--config` is supplied. The VR Files page can load
previous snapshots without restarting.

## Controls and patterns

The default view contains the same dark-neutral ramp twice: **8-bit at the
top, 10-bit at the bottom**. These are regions of the same panel, seen by both
eyes, not different images assigned to the left and right eye.

| Control | Behaviour |
| --- | --- |
| Source mode | 8-bit, 10-bit, unquantised float reference, two-way comparison, three-way comparison, or 8-bit with fixed dithering. |
| Pattern | Horizontal, vertical or radial gradient; solid colour; continuous hue sweep; 12-colour gradient atlas. |
| Presets | 48 endpoint presets: dark and bright neutrals, blue-grey, warm-grey, primary/secondary colours and 24 dark hue variants. |
| Custom RGB | Enter arbitrary start and end RGB components as sRGB-encoded values from 0 to 1. Press Enter or Apply. Fractional inputs are retained. |
| Pick | Standard colour picker for convenient 8-bit endpoint entry. The gradient is still generated procedurally; this is not an imported 8-bit image. |
| Hue controls | Hue 0–360, saturation 0–1, minimum and maximum HSV value 0–1. Click **Make gradient from hue** to update ordinary ramp endpoints. |
| Atlas | Twelve evenly spaced hues, rotated by the hue control, with a dark-to-bright ramp in each cell. Uses saturation and minimum/maximum value, not the custom RGB endpoints. |
| Continuous hue sweep | Uses hue offset, saturation and maximum HSV value. Minimum value is not used by this pattern. |
| Geometry | Physical panel width, height and distance in metres. The panel remains world-fixed after recentering. |
| Labels / swap | Hide labels for a less cluttered test or exchange comparison order. Three-way default order is 8-bit, 10-bit, reference, from top to bottom. |
| Animate | Deterministic slow triangular motion through the gradient domain, with no random temporal noise. Setting changes and recentering reset its phase. Solid colour is not animated. |
| Automatic cycling | Visits all 48 endpoint presets every 8 seconds. Each preset uses the horizontal-gradient pattern. Disable it before a controlled single-colour comparison. |
| Save settings / Load settings | Read/write JSON for reproducing the exact pattern, colours, source mode, geometry and manually recorded conditions. |
| Save run report | Saves a diagnostic report and a separate replayable settings JSON under `runs`. |

**HSV value is a colour-component parameter, not physical luminance or nits.**
This is an SDR/sRGB source-precision test, not an HDR10/PQ test, wide-gamut test,
colourimeter or panel calibration tool. It does not load arbitrary image files.

### Keyboard shortcuts

These work when the **desktop preview window has keyboard focus**. The controls
window reserves normal keys for editing fields.

| Key | Action |
| --- | --- |
| 1 / 2 / 3 | Full-panel 8-bit / 10-bit / float reference. |
| 4 / 5 | Two-way / three-way comparison. |
| Space | Toggle full-panel 8-bit and 10-bit at the same screen position. From a comparison mode, the first press selects 8-bit. |
| Left / Right | Previous / next colour preset. |
| P | Next pattern. |
| X / L / M | Swap comparison order / toggle labels / toggle motion. |
| R / F1 / F5 / Esc | Recenter panel and menu / toggle VR menu / save report / exit. |

For a position-matched A/B, use **Space**, rather than judging the top and
bottom halves at different viewing angles. Swap the comparison order as a
secondary check. Full-panel A/B is not a blinded or randomised experiment.

## A repeatable streaming test

Start with `examples/dark_neutral_compare.json` or the defaults. Keep motion
off and source labels hidden during close inspection; both are optional.
Test a neutral ramp first, then the dark colour atlas or an endpoint preset.
For detailed single-colour inspection use a full-panel mode rather than the
smaller atlas cells.

Leave **source mode and colour settings fixed** when comparing the stream's
8-bit and 10-bit encoding options. Change the streaming option in the streaming
app / SteamVR, not in Colour Lab. Reconnect the stream after the change to
remove ambiguity about when it took effect. Record the actual streaming app,
codec, SteamVR version, target/observed bitrate, refresh rate, encoded resolution,
foveation, headset brightness and any dynamic-quality settings.

Then, in a separate comparison, leave the streaming settings fixed and use
Space to alternate the source between 8-bit and 10-bit. Do not change both
variables at once and attribute the result to only one of them.

The section named **Manually recorded streaming conditions** is metadata only.
Selecting "10" there does not change the source, streaming software, encoder,
headset or driver. The report deliberately retains
`"stream_depth_confirmed": false`.

Share the same application ZIP, a `settings-*.json` and the matching
`report-*.json`. For fixed render dimensions, start every run with the same
`--eye-size WIDTHxHEIGHT`; otherwise SteamVR's recommendation at launch is used
and logged. This fixes the source eye-buffer dimensions, **not** the encoder's
resolution. Keep panel geometry and the centred viewing position consistent;
recentring is an explicit user action, not a globally identical room pose.
Automatic cycling and its elapsed timer are recorded in a report but are not
restarted by loading a settings file.

## Source precision and important limitations

The image path controlled by this application is:

```
Procedural sRGB RGB gradient in a shader
  -> optional per-channel quantisation to 8 or 10 bits
  -> explicit sRGB-to-linear conversion
  -> GL_RGBA16F eye texture (16-bit float per channel)
  -> OpenVR Submit with ColorSpace_Linear
  -> SteamVR / streaming encoder / Wi-Fi / headset decoder / display
     (these downstream stages are outside this application's control)
```

For each encoded channel `s`, the intentional quantisation is:

```glsl
float levels = tenBit ? 1023.0 : 255.0;
s = floor(clamp(s, 0.0, 1.0) * levels + 0.5) / levels;
```

The reference skips this quantisation, but remains limited by shader arithmetic,
spatial sampling and float16 storage. It is not an infinite-precision reference.
Eight-bit with dithering uses a fixed, documented integer hash in panel UV
space and independent channel seeds; it is a comparison control, not a claim
about the encoder's dithering. All other modes contain no intentional dither.

There is no application-side tone mapping, automatic exposure, film grain,
sharpening, MSAA or 8-bit intermediate copy on the headset path. The desktop
preview is rendered separately and explicitly converted back to sRGB for a
conventional window; it does not feed the headset image.

At startup the app queries the allocated GL texture format and channel sizes,
renders a 4096-pixel full-range ramp, reads float values back, and requires
**256 distinct levels in 8-bit mode and 1024 in 10-bit mode**, with more than
1024 in the reference. The round-trip colour error is checked as well.
It stops with an error instead of silently using an 8-bit texture if this fails.
It also stops if SteamVR rejects the float texture.

This establishes source-buffer precision only. A successful OpenVR Submit is
not evidence that SteamVR, the encoder, decoder or panel preserves every level.
The app cannot confirm encoded bit depth, native panel depth, or the absence of
internal colour conversions. Scaling, filtering, foveation and compression may
change the contours after submission. The finite render resolution also means
a narrow panel need not display every nominal code value at once.

## Reports and privacy

`runs/<local-timestamp>/` contains a session JSON, timestamped settings events,
and an application log. Explicit reports add actual graphics API/driver
strings, tested texture precision, requested and recommended eye sizes,
headset model / refresh data when available, frame counts, the last tracked
head pose, panel anchor, manually entered conditions, and a shader SHA-256.
Reports use UTC for event timestamps. Review these files before sharing: the
pose, machine details and free-text notes may be information you prefer to
remove. No reports are uploaded by this application.

## Command line

Portable application package:

```bat
SteamVRColourLab.exe
SteamVRColourLab.exe --config examples\dark_colour_atlas.json
SteamVRColourLab.exe --eye-size 2048x2048
SteamVRColourLab.exe --desktop
SteamVRColourLab.exe --self-test
```

Developers running from source need full 64-bit Python 3.11 or newer with tkinter and pip:

```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

`--no-ui` hides only the desktop controls; the VR dashboard remains available.
`--output PATH` changes the log directory and `--settings-dir PATH` changes the
VR snapshot folder. `--frames N` is a finite-loop smoke
check, not a fixed-frame video export. It counts loop iterations, not confirmed
headset frames. There is no video encoder or screen-capture dependency here.

## Troubleshooting

**Portable executable will not start:** extract the entire ZIP, including
`_internal`, and run it from a writable local directory. Check the session
application log under `runs` if one was created.

**Source development: missing modules / tkinter:** install `requirements.txt`
into the same full Python environment used to run `app.py`. End users of the
portable package do not need to install these dependencies.

**No panel / waiting for valid tracking:** confirm SteamVR is running, the
headset is connected and awake, tracking is valid, and another scene application
has not taken focus. Face forward and recenter, then close the dashboard. The
status field distinguishes a tracking wait from successful submissions.

**Float texture rejected / TextureIsOnWrongDevice:** ensure Colour Lab runs on
the same discrete GPU as SteamVR, especially on multi-GPU laptops, and use
an appropriate graphics driver. The utility never silently falls back to
8-bit. Include the full compositor error and log in a developer report.

**OpenGL context could not be created:** use a local graphical session, a
working hardware graphics driver and OpenGL 3.3 support. Remote desktop or
software-driver configurations may not provide a usable VR graphics context.

**Colour changes appear to do nothing:** numeric entries need Enter or Apply.
For a regular ramp, click Make gradient from hue after editing HSV controls.
Atlas and hue-sweep patterns ignore RGB endpoints by design.

**The desktop looks banded:** this preview does not establish headset image
quality or bit depth. Inspect the actual headset scene.

## Automatic GitHub builds and versions

[Build status](https://github.com/AngelDark92/SteamVRColourLab/actions/workflows/build.yml)
and [Windows downloads](https://github.com/AngelDark92/SteamVRColourLab/releases/latest).

Every branch push and pull request runs the complete test suite on Linux with
Mesa software rendering and Xvfb, then builds the portable Windows x64 ZIP on
Windows. You can also use **Actions → Build and release → Run workflow**.
The workflow installs all build dependencies; no personal computer or custom
GitHub secret is needed. Branch and PR builds are downloadable workflow artifacts.

Successful builds on `main` automatically tag and publish a GitHub release when
commit subjects since the previous version contain one of these prefixes:

| Commit subject | Version bump | Example from 1.2.3 |
| --- | --- | --- |
| `fix: correct a bug` | Patch | `1.2.4` |
| `feat: add a feature` | Minor | `1.3.0` |
| `rework: redesign behavior` | Major | `2.0.0` |

Scopes such as `fix(ui): ...` also work. The highest requested bump wins once
per release (`rework` > `feat` > `fix`), including commits accumulated after a
failed or superseded build. Other prefixes still build and test but do not
create a new version. Only subjects count; prose in a commit body does not.
For squash merges, put the intended prefix in the final squash commit title.

Tags `vX.Y.Z` are the release version record; the initial baseline is `0.2.1`.
CI stamps the calculated version into the packaged app and `BUILD_INFO.json`,
which also records the exact source commit. The source version is the initial
fallback, so CI does not need to push version-only commits back to `main`.
`SteamVRColourLab.exe --version` prints the packaged version.
Reruns reuse the same tag and preserve already-published assets. Releases
include the ZIP and its SHA256 checksum; publication needs the workflow's
built-in `contents: write` permission.

CI verifies the archive, checksum, version, source commit, and relocated EXE
startup with external Python removed from PATH. Hosted Windows runners do not
prove GPU precision or headset interaction; those still require the local
`--self-test` and SteamVR checks below.

## Tests and builds (source archive)

On Windows, with dependencies installed and a local graphics session:

```bat
.venv\Scripts\python.exe -m unittest discover -v
.venv\Scripts\python.exe app.py --self-test
```

On a Linux development host, the tests use Mesa/EGL for the real renderer and
Tk/Xvfb for controls. They do not need SteamVR; install `requirements.txt` first:

```sh
xvfb-run -a python -m unittest discover -v
```

Build the `.pyz` with the included standard-library build tool:

```bat
.venv\Scripts\python.exe tools\build_zipapp.py
```

Build the portable Windows application with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/Build-Portable.ps1
```

Or double-click `build_portable_windows.bat`. The build machine needs full x64
Python with tkinter and pip and network access to install pinned dependencies.
Use `-Python C:\path\to\python.exe` to select it explicitly. The script uses an
isolated build environment, checks dependencies, and produces:

- `dist/SteamVRColourLab/SteamVRColourLab.exe` plus its runtime and launchers.
- `dist/SteamVRColourLab-Windows-x64.zip` and its `.sha256` checksum.

An existing output folder is retained under `build/portable/previous-*`.
Its `runs` and `settings` are also restored into the new local package after
creating the clean distributable ZIP, so personal data is not included in it. Build staging is retained for diagnosis and may be
removed after verification; keep the `venv-*` build environment for reuse.
The resulting executable is unsigned. See `TEST_RESULTS.md` for the exact
local checks and remaining headset validation. The legacy `.pyz` is still a
source/developer format and requires separately installed Python/dependencies.

## Source layout

```
app.py                         Event loop, CLI, logging, reports, keyboard input
colourlab/core.py              Validated settings, presets, colour / matrix math
colourlab/shaders.py           Actual procedural GLSL shaders, quantisation, labels
colourlab/gl.py                Typed OpenGL loader and verified float targets
colourlab/vr.py                OpenVR poses, stereo matrices and eye submissions
colourlab/ui.py                Optional desktop colour and comparison controls
colourlab/dashboard_ui.py      VR pages, keypad/keyboard and pointer hit testing
colourlab/dashboard.py         In-scene menu, compact reopen button, dashboard transport
colourlab/overlay_texture.py   Persistent GPU textures for VR controls
tools/Build-Portable.ps1       Isolated Windows executable and ZIP build
colourlab/diagnostics.py       Live source-buffer precision check
tests/                         Colour, rendering, UI and mocked OpenVR tests
tools/build_zipapp.py           Rebuilds the runnable Python archive
examples/                      Replayable test settings
```

## API references

The implementation follows these primary API definitions; these references do
not imply end-to-end validation of this particular build.

- Valve OpenVR: texture types, ColorSpace_Linear, pose and compositor APIs:
  https://github.com/ValveSoftware/openvr/blob/master/headers/openvr.h
- pyopenvr bindings and OpenGL renderer example:
  https://github.com/cmbruns/pyopenvr
- GLFW context / procedure-address API:
  https://www.glfw.org/docs/latest/group__context.html
- Pinned package releases:
  https://pypi.org/project/openvr/2.12.1401/
  https://pypi.org/project/glfw/2.10.0/
- Python on Windows, including tkinter / embeddable-package differences:
  https://docs.python.org/3/using/windows.html

See `LICENSE` and `THIRD_PARTY_NOTICES.md` for licensing.
