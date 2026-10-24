# SteamVR Colour Lab

**Spot colour banding in your VR headset and compare image quality.**

Colour banding is the visible striping in colours that should blend smoothly.
Colour Lab gives you gradients, dark colours and 8-bit/10-bit comparisons to
help you see it—and compare the results when you change your streaming settings.
You can control everything from inside VR.

## Agent instructions

`AGENTS.md` is the project contract; the nearest workspace `AGENTS.md` supplies
shared rules.

| Host | Entry point |
| --- | --- |
| **OpenCode** | `AGENTS.md`, `.opencode/agents/`, `.opencode/skills/` |
| **Cursor** | `.cursor/rules/project.mdc` |
| **Hermes** | `AGENTS.md`, `.agents/AGENTS.md`, `.agents/skills/` after `hermes skills trust` |
| **Codex** | `AGENTS.md`, `.agents/skills/` |
| **Claude Code** | `CLAUDE.md` |

Hermes delegates with `delegate_task`, not named presets. Paste the role contract
from [`.agents/skills/cavecrew/references/hermes-roles.md`](.agents/skills/cavecrew/references/hermes-roles.md)
into each child's `context`. Generated files and logs go to
`../builds/SteamVRColourLab`, outside the checkout.

**[Download for Windows](https://github.com/AngelDark92/SteamVRColourLab/releases/latest/download/SteamVRColourLab-Windows-x64.zip)**

Windows 64-bit · SteamVR · No Python installation needed

[Get started](#get-started) · [Try a comparison](#try-a-comparison) · [VR controls](#vr-controls) · [Help](#help) · [Technical reference](TECHNICAL_REFERENCE.md)

## Get started

1. Download the ZIP above and **extract the entire folder**.
2. Start SteamVR and connect your headset using your usual streaming app.
3. Close any other VR game, then open **SteamVRColourLab.exe**.
4. Use your controller pointer to select options in the menu in front of you.
   Hand input also works if your setup supports pointing and selecting in SteamVR.

Keep the extracted files together, including the `_internal` folder.
To look around without a headset, open **preview_windows.bat**.

## Try a comparison

The starting view shows **8-bit on top and 10-bit below**, using the same dark
gradient. Look for visible steps or stripes between shades.

- Use **Source** to change the comparison or pattern.
- Try different colour presets, especially dark greys and blues.
- Select **Hide menu** for a clear view. **OPEN OPTIONS** brings it back.
- For a closer comparison, select **A/B: 8-bit <-> 10-bit** on the Source tab:
  both images appear in the same place, one at a time.

When comparing streaming settings, keep the Colour Lab image the same and
change one streaming setting at a time. Save your settings to repeat a test later.

**The 8-bit/10-bit controls change the test image.** Your streaming app controls
the stream itself; Colour Lab cannot confirm its actual bit depth.

## VR controls

| Menu tab | What you can do |
| --- | --- |
| **Source** | Choose comparisons and patterns; toggle labels and motion. |
| **RGB / Hue** | Browse colour presets or choose your own colours. |
| **Geometry** | Adjust the panel's size and distance. Use **Recenter** to bring it in front of you. |
| **Session** | Add notes about your streaming setup. These are notes, not settings changes. |
| **Files** | Save a setup or load one you've saved before. |
| **Bitrate** | Run fullscreen streaming stress tests and optionally measure headset video payload over ADB. |
| **Telemetry** | Record PC/headset measurements and verify the codec from captured stream bytes. |

Select a number or text field to edit it inside VR. **Save run report** records
your test, and **Exit** closes the utility. Desktop controls are available too.

## Test streaming bitrate

Open **Bitrate** in VR or in the desktop controls. Choose static detail, moving
detail, high-contrast motion, or changing noise, and select a duration. **Start
fullscreen test** fills both eye buffers; panel size, distance and head direction
cannot leave an unstressed border. Changing noise is the strongest synthetic
load; it is not a typical game scene and reaching a target is not guaranteed.

Starting collapses the VR menu to **OPEN OPTIONS**, which follows your head.
Select it to reopen the controls wherever you are looking; **F1** also restores
the menu. Desktop **Minimize controls** keeps the window available on the taskbar.
**Stop / restore** returns to the previous colour test. The clock starts on the
first submitted scene frame with menus minimized. Close the SteamVR dashboard
if the test is waiting for scene focus; later menu occlusion or focus/tracking
interruption is recorded in the result.

The comparison target is only a label for your 500/600 Mbps runs. It does not
change the streamer, driver, codec or encoder settings. **Host encoder target**
is a requested budget, not the actual received bitrate.

The **Telemetry** tab saves continuous measurements while you run a workload.
The workload ID in the CSV identifies the test. Legacy `GXRStreamProbe` logs
can still produce per-frame exports; that older protocol is separate from the
new decoder probe. See [measurement details](TECHNICAL_REFERENCE.md#bitrate-tests).

## Record telemetry and verify a codec

PC recording starts automatically. Each session's `telemetry/` folder contains
`samples.csv`, `samples.jsonl`, a field description in `schema.json`, and newly
observed NVENC log lines. It records successful Colour Lab stereo submissions,
the available host encoder target and submit-to-lock latency, and headset
readings when connected. Unsupported readings stay empty. The host target is
a request; the app does not infer actual sent Mbps from it.

In **Telemetry**, leave **USB ADB only** selected, connect one headset by USB,
authorize USB debugging in the headset, then select **Connect / disconnect**.
Android platform-tools must be on `PATH` or supplied with `--adb PATH`. Battery
temperature, charge and available current thermal sensors are sampled every
five seconds without a Steam Link patch. Turn USB-only off to use an already
authorized ADB network transport; enter its serial on the desktop or Bitrate tab.

Decoder measurements and live byte verification require the updated **Codecs
Support** helper from the sibling `steamlink-patches` project. Its diagnostic
producer is guarded to exact Steam Link **2.0.20/5001712** and
**2.0.23/5002363**; headset validation of this new instrumentation is pending.
Repatch/install that version separately. Colour Lab connects and writes only
its own temporary diagnostic requests; it never installs an APK or restarts
SteamVR. Disconnect removes owned requests; a 30-second lease also stops
native collection after a lost connection.

The decoder probe measures accepted compressed input Mbps, accepted input
frames/s, dequeued output buffers/s, and queue-to-output residence time. The
last includes decoder buffering and scheduling. These are separate from network
traffic, radio loss and physically displayed frames.

Select **H.264**, **HEVC** or **AV1** in **Expected stream codec**, then press
**Verify** while streaming. Select the actual codec in your streamer first;
this dropdown sets the expectation to check. Verification requests a new
complete decoder-input sample, checks its length and SHA-256, then parses its
NAL/OBU framing and parameter/frame headers independently of settings labels.
It saves the bytes and JSON verdict under `bitrate/diagnostics/` on the PC.
Missing headers, stale/mismatched evidence or an unsupported patch produce
**inconclusive**, never a pass. Waiting for a sequence header/keyframe can take
several seconds. This verifies one accepted input sample before any helper
rewrite; it does not decode the picture or prove display quality.

Portable data stays in `runs/<session>/` beside the executable. Running source
directly defaults to `../builds/SteamVRColourLab/build/runs/`; `--output` selects
another location and `COLOURLAB_OUTPUT_ROOT` changes the external source root.

## Help

<details>
<summary><strong>I cannot see the panel or use the menu</strong></summary>

Check that SteamVR is running, your headset is connected and tracking, and
another VR game is not open. Face forward and select **Recenter**.
Use **OPEN OPTIONS** to restore a hidden menu, or press **F1** with the desktop
preview selected. If hand selection is unavailable, use a controller pointer.

</details>

<details>
<summary><strong>The app will not start</strong></summary>

Extract the full ZIP before launching it. Keep `_internal` beside the EXE.
A graphics driver with OpenGL 3.3 support is required. Update your graphics
driver if needed; **self_test_windows.bat** checks the local renderer without
a headset. See the [troubleshooting guide](TECHNICAL_REFERENCE.md#troubleshooting)
for specific errors.

</details>

<details>
<summary><strong>Keyboard shortcuts and saved files</strong></summary>

Click the desktop preview before using these shortcuts.

| Key | Action |
| --- | --- |
| **Space** | Switch between full-panel 8-bit and 10-bit. |
| **← / →** | Previous / next colour preset. |
| **R / F1** | Recenter / show or hide the VR menu. |
| **F5 / Esc** | Save a report / exit. |

Saved setups are in `settings`; reports and logs are in `runs`, beside the EXE.
Use **Files** to load a saved setup. Reports stay on your computer; review their
contents before sharing them.

</details>

---

[Technical reference](TECHNICAL_REFERENCE.md) · [Test results](TEST_RESULTS.md) · [Releases](https://github.com/AngelDark92/SteamVRColourLab/releases) · [License](LICENSE)
