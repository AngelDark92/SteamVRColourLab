# Third-party notices

The portable Windows build bundles its runtime and native libraries. Keep the
entire output directory and its license files when redistributing it.
The application source is covered by the accompanying LICENSE.

- CPython: PSF and component licenses; `licenses/CPython-LICENSE.txt`;
  https://docs.python.org/3/license.html
- Tcl/Tk (tkinter): component licenses in `licenses` and runtime data;
  https://www.tcl-lang.org/software/tcltk/license.html
- pyopenvr / openvr: BSD; `licenses/openvr/licenses/LICENSE`;
  https://github.com/cmbruns/pyopenvr
- Valve OpenVR SDK (included by pyopenvr): BSD-3-Clause;
  `licenses/OpenVR-v2.12.14-LICENSE.txt`;
  https://github.com/ValveSoftware/openvr/blob/master/LICENSE
- pyGLFW / glfw: MIT; `licenses/glfw/LICENSE.txt`;
  https://github.com/FlorianRhiem/pyGLFW
- GLFW native library (included by its wheel): zlib/libpng;
  `licenses/GLFW-3.4-LICENSE.txt`;
  https://www.glfw.org/license.html
- Pillow and bundled image/font libraries: HPND and component licenses in
  `licenses/Pillow/licenses/LICENSE`; https://python-pillow.github.io/
- PyInstaller bootloader: GPL with a distribution exception permitting this
  application license; `licenses/PyInstaller/licenses/COPYING.txt`;
  https://pyinstaller.org/en/stable/license.html

Dashboard text uses the host Windows Segoe UI font when available. No Windows
font file is copied or redistributed. Pillow's included fallback font is used
otherwise. The test gradients and source labels are generated procedurally.

SteamVR itself is not bundled. SteamVR is a Valve trademark. This is an
independent test utility, not a Valve product, certification tool, or calibrated
display instrument. The legacy `.pyz` contains application source only and
requires separately installed dependencies.
