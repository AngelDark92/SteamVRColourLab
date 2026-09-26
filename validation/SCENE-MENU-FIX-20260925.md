# In-scene VR controls and startup recovery — 2026-09-25

Version 0.2.1. The previous 0.2.0 build offered a dashboard tab only. The user
reported abrupt closure and no usable GUI in the headset.

## Diagnosis and corrections

- Earlier source log contains InitError_Driver_WirelessHmdNotConnected. Startup
  now keeps preview/controls open and retries these known temporary connection
  errors every 3 seconds. Permanent errors are not silently retried.
- The user's packaged run at 20:15 initialized and submitted 6981 frames. At
  20:16 Steam Link sent client shutdown and SteamVR sent Quit to all applications.
  Colour Lab obeyed it. Windows logged a RADAR_PRE_LEAK memory heuristic, not an
  APPCRASH for the EXE. No native EXE crash was reproduced, and no native crash
  cause is claimed. New logs record explicit exit reasons; fatal portable errors
  show exception type/code and log path after cleanup.
- The GUI now appears as an ordinary world-positioned overlay inside the scene,
  with SteamVR laser input explicitly enabled while the dashboard is closed.
  All settings, numeric/text editing, presets, saving/loading and reports use it.
  Hide menu leaves an OPEN OPTIONS button below the test panel. Recenter moves
  the menu, and desktop Show VR controls / F1 can recover it.
- The first live in-scene test proved click/settings events and hide/reopen, but
  the user observed flashing. Replacing raw image reloads with persistent GL_RGBA8
  textures and TexSubImage2D updates removed the flashing in the user's retest.
  Scene RGBA16F test rendering and source shaders remain unchanged.
- The GPU-texture path uses bottom-up pixels but receives pointer coordinates
  already oriented for the displayed menu on this runtime. Removing an extra Y
  inversion fixed mirrored clicks. User confirmed correct click positions and
  no flashing in the corrected-input source run. This is live evidence; the earlier
  generic bottom-left mouse assumption was not valid for this submission path.
- Hiding the GPU menu exposed GL_INVALID_VALUE (0x0501): reusing the same GL
  name for 1280x800 and 360x96 storage broke the shared texture path. The user's
  subsequent portable run enabled Motion at 18:34:58 UTC, then hid the menu at
  18:35:01 UTC and failed immediately afterward. A separate-resource attempt
  also failed at SetOverlayTexture: changing the overlay's dimensions, even
  with a different GL name, is unsafe on this runtime. The final approach keeps
  one 1280x800 resource per scene/menu overlay throughout its lifetime. The compact
  image is resampled into that storage; SteamVR texel aspect restores its 360:96
  display proportions, with unchanged logical mouse scale. Resize attempts fail
  before GL calls, and GL errors are checked immediately after submission.
- Thumbnail cleanup now destroys its dashboard parent only; SteamVR owns the
  thumbnail, and direct destruction previously logged ThumbnailCantBeDestroyed.
- Rebuild restores prior runs/settings into the active output after making the
  clean ZIP. User data stays out of the distributable.

## Evidence

- `validation/launch-repro`: old portable EXE connected and completed 180 frames.
- `validation/scene-menu-smoke`: scene_visible=true, dashboard_visible=false,
  180 pointer moves at the sampled status, 240 submitted frames.
- `validation/scene-interaction`: 5400 submitted frames, 13 select releases,
  settings changes and hide/reopen recorded. User reported clicking worked but
  raw texture updates caused flashing; this intermediate transport is retired.
- `validation/gpu-menu-interaction`: user confirmed upright, non-flashing text;
  mirrored Y input found and corrected in the subsequent run.
- `validation/gpu-input-corrected`: user confirmed correct clicking, no flashing;
  hiding the menu then raised GL 0x0501. This intermediate build is superseded.
- `dist/SteamVRColourLab/runs/20260925-203428-963253`: same hide-menu failure
  after Motion was enabled. This user run is retained across rebuilds.
- `validation/scene-final-unit-tests.txt`: 85 automated tests passed, including
  4 real-GPU tests. Repeated native-event menu tests cover Motion plus 5 hide/open
  cycles, fixed-size texture storage, ownership and cleanup. GPU tests verify
  pixels/orientation, same-size storage reuse, rejected resizing and unchanged
  RGBA16F source precision. Independent cache-lifecycle review found no issues.
- `validation/portable-menu-cycles-final`: first packaged regression reproduced
  GL 0x0501 at the compact SetOverlayTexture call despite different GL names.
  This size-switching attempt is retired; its EXE hash and logs are retained.

- `validation/portable-fixed-size-menu/result.json`: final EXE completed 12
  real SteamVR hide/open cycles with Motion ON, 24 transitions and 818 submitted
  frames; exit 0, no fatal errors. Input was synthetic OpenVR overlay events;
  rendering/submission used the actual packaged application and connected headset.
- `validation/portable-headset-final`: the same EXE was then tested manually.
  User confirmed Motion, Hide menu and OPEN OPTIONS all work; the app remains
  running with readable text and pointer alignment on both full and compact UI.
  It completed 5400 submitted frames, recorded 9 select releases, then exited
  normally at the requested frame limit with no fatal errors.
- `validation/portable-final-checks.json`: ZIP extracted to a different folder;
  self-test and desktop 8-frame launch both exited 0 with external Python absent
  from PATH and Python environment overrides removed. The ZIP contains no runs
  or saved settings. Its extracted EXE matches the live-tested EXE byte for byte.
- Full `tools/Build-Portable.ps1` succeeded. `validation/scene-final-build.txt`
  retains the build output; the final ZIP hash beside the archive includes the
  subsequently updated validation documentation.

Final EXE SHA256: `7a5da401b091908f90d148713fba114ab11d4ceadb35b99550d4e3fcbc0c0d48`.

## Reproduce the packaged menu regression

With explicit permission, SteamVR already running, headset connected, and other
Colour Lab instances closed:

```powershell
.venv/Scripts/python.exe tools/check_vr_menu.py --exe dist/SteamVRColourLab/SteamVRColourLab.exe --output validation/new-menu-check
```

This manual validation helper requires development Python, but the EXE under
test does not. It checks overlay ownership before sending input, changes only
Colour Lab's unsaved controls, and records all output in a new directory.

## Boundaries

The connected headset reports an Oculus Quest2 identity through the installed
SteamVR routing; this does not establish its physical model. Controller/hand
pointer events are runtime-managed; no driver, device permission, streaming
setting or global SteamVR configuration was changed. Universal raw-skeleton
input and downstream 10-bit preservation remain outside the validation claim.

The old output is retained as a backup with user data. Build/relocation staging
from the earlier turn remains because automatic deletion approval was blocked.
Current build staging is retained as diagnostic evidence alongside it; it may be
removed once scoped cleanup is permitted. No unrelated files were removed.
`validation/scene-cleanup-inventory.json` inventories the complete affected
workspace (no nested Git repositories), preserved build inputs and backups,
and disposable staging/relocation copies: 161181922 bytes retained, 0 reclaimed.
The earlier automatic approval review rejected scoped deletion as "blocked by
policy"; no alternate deletion mechanism was used. Cleanup remains deferred
until scoped deletion is permitted. Regeneration commands are in the inventory.
