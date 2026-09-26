# SteamVR Colour Lab

**Spot colour banding in your VR headset and compare image quality.**

Colour banding is the visible striping in colours that should blend smoothly.
Colour Lab gives you gradients, dark colours and 8-bit/10-bit comparisons to
help you see it—and compare the results when you change your streaming settings.
You can control everything from inside VR.

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

Select a number or text field to edit it inside VR. **Save run report** records
your test, and **Exit** closes the utility. Desktop controls are available too.

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
