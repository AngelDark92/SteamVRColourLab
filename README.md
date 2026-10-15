# SteamVR Colour Lab

**Spot colour banding in your VR headset and compare image quality.**

Colour banding is the visible striping in colours that should blend smoothly.
Colour Lab gives you gradients, dark colours and 8-bit/10-bit comparisons to
help you see it—and compare the results when you change your streaming settings.
You can control everything from inside VR.

## Agent instructions

This repository carries instruction files for several agent hosts. Each host reads
a different subset:

| Host | Reads | Ignores |
| --- | --- | --- |
| **Hermes** | `AGENTS.md`, `.agents/AGENTS.md`, `.agents/skills/` when the checkout is trusted | `.github/agents/`, `.codex/` |
| **Codex / Copilot** | `.github/agents/`, `.codex/` | `AGENTS.md` skills mechanics |
| **Claude Code** | `CLAUDE.md` | Hermes `delegate_task` notes |

Before first use from Hermes, trust the checkout once so the project skills in
`.agents/skills/` load:

```sh
hermes skills trust
```

Delegated work from Hermes uses the `delegate_task` tool, not the Codex
`cavecrew-*` presets. Paste the role contract from
[`.agents/skills/cavecrew/references/hermes-role-contracts.md`](.agents/skills/cavecrew/references/hermes-role-contracts.md)
into each child's `context`. Generated build files, packages and logs always go
to `../builds/SteamVRColourLab`, outside the checkout.

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

For actual headset Mbps, install/enable the compatible diagnostic
**GXRStreamProbe** Steam Link build separately, authorize ADB on the headset,
then select **Connect headset probe** before starting a test. Standard Steam
Link does not expose these counters. Android platform-tools must be on `PATH`
or supplied with `--adb PATH`; enter a device serial if more than one authorized
ADB device is connected. The app never installs an APK or restarts SteamVR.

The tab shows rolling one-second compressed-video Mbps and access units per
second from the headset's monotonic timestamps. It excludes audio, FEC,
retransmissions and network overhead. Missing probe data appears as unavailable.
After a measured test, `runs/<session>/bitrate/<test-id>/` contains `summary.json`,
`frames.csv` and `bitrate-windows.csv`; the raw tagged log is alongside it. The
summary excludes five seconds of settling and two seconds of teardown, and
checks cumulative counters for missing log rows. Decoder outputs and render
releases are separate from received frames; neither establishes physical display
presentation. See [measurement details](TECHNICAL_REFERENCE.md#bitrate-tests).

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
