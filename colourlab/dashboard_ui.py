"""Pointer-only controls shared by SteamVR's controller and hand pointers.

This RGBA dashboard is separate from the procedural float eye buffers. Editing,
including numeric/text entry and choosing saved files, needs no desktop dialog.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .core import MODES, PATTERNS, PRESETS, Settings, hue_endpoints


@dataclass
class Button:
    key: str
    rect: tuple[int, int, int, int]
    label: str
    action: object
    selected: bool = False

    def contains(self, x, y):
        a, b, c, d = self.rect
        return a <= x < c and b <= y < d


class DashboardUI:
    WIDTH, HEIGHT = 1280, 800
    PAGES = ("Source", "RGB", "Hue", "Geometry", "Session", "Files")
    # One source of UI limits; Settings.validate remains authoritative.
    NUMBERS = {
        "hue": ("Hue (degrees)", 0, 360, 1),
        "saturation": ("Saturation", 0, 1, .05),
        "value_min": ("Minimum HSV value", 0, 1, .005),
        "value_max": ("Maximum HSV value", 0, 1, .005),
        "panel_width": ("Panel width (metres)", .2, 10, .1),
        "panel_height": ("Panel height (metres)", .2, 10, .1),
        "panel_distance": ("Panel distance (metres)", .5, 10, .1),
    }

    def __init__(self, app):
        self.app = app
        self.page = "Source"
        self.buttons = []
        self.lines = []
        self.hover = None
        self.pressed = None
        self.editor = None
        self.shift = False
        self.replace_text = False
        self.files = []
        self.file_page = 0
        self.message = "Point and select in VR. Hide menu to inspect; OPEN OPTIONS brings it back."
        self.dirty = True
        self._state = None
        self._notice = ""
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        try:
            self.font = ImageFont.truetype(str(fonts / "segoeui.ttf"), 23)
            self.small = ImageFont.truetype(str(fonts / "segoeui.ttf"), 20)
            self.title = ImageFont.truetype(str(fonts / "segoeuib.ttf"), 32)
        except OSError:
            self.font = ImageFont.load_default(size=23)
            self.small = ImageFont.load_default(size=20)
            self.title = ImageFont.load_default(size=32)
        self.rebuild()

    def sync(self):
        state = (repr(self.app.settings), self.app.preset_index,
                 self.app.cycle_start is not None, self.app.notice)
        if state != self._state:
            self._state = state
            if self.app.notice and self.app.notice != self._notice:
                self.message = self.app.notice
            self._notice = self.app.notice
            self.rebuild()

    def button(self, key, rect, label, action, selected=False):
        self.buttons.append(Button(key, rect, label, action, selected))

    def line(self, x, y, text):
        self.lines.append((x, y, text))

    def set_page(self, page):
        self.page = page
        self.editor = None
        if page == "Files":
            self.refresh_files()
        self.rebuild()

    def change(self, **values):
        self.app.change(replace(self.app.settings, **values).validate(), "VR controls")
        if self.app.ui:
            self.app.ui.refresh()

    def cycle(self, field, choices, step=1):
        current = getattr(self.app.settings, field)
        self.change(**{field: choices[(choices.index(current) + step) % len(choices)]})

    def toggle(self, field):
        self.change(**{field: not getattr(self.app.settings, field)})

    def toggle_cycle(self):
        self.app.set_cycle(self.app.cycle_start is None)
        if self.app.ui:
            self.app.ui.cycle.set(self.app.cycle_start is not None)

    def field_value(self, field):
        if "." in field:
            name, component = field.split(".")
            return getattr(self.app.settings, name)[int(component)]
        return getattr(self.app.settings, field)

    def set_field(self, field, value):
        if "." in field:
            name, component = field.split(".")
            rgb = list(getattr(self.app.settings, name))
            rgb[int(component)] = value
            self.change(**{name: tuple(rgb)})
        else:
            self.change(**{field: value})

    def nudge(self, field, amount, low, high):
        self.set_field(field, round(max(low, min(high, self.field_value(field) + amount)), 12))

    def edit(self, field, label, numeric=True):
        value = self.field_value(field)
        text = repr(value) if numeric else value
        self.editor = {"field": field, "label": label, "numeric": numeric, "text": text}
        self.replace_text = True
        self.message = ""
        self.rebuild()

    def type_key(self, text):
        if self.replace_text:
            self.editor["text"] = ""
            self.replace_text = False
        limit = 64 if self.editor["numeric"] else 4000
        self.editor["text"] = (self.editor["text"] + text)[:limit]

    def backspace(self):
        self.editor["text"] = "" if self.replace_text else self.editor["text"][:-1]
        self.replace_text = False

    def clear_text(self):
        self.editor["text"] = ""
        self.replace_text = False

    def append_text(self):
        self.replace_text = False

    def cancel_edit(self):
        self.editor = None

    def apply_edit(self):
        value = self.editor["text"]
        if self.editor["numeric"]:
            value = float(value)
        self.set_field(self.editor["field"], value)
        self.editor = None
        self.message = "Applied."

    def make_hue(self):
        s = self.app.settings
        a, b = hue_endpoints(s.hue, s.saturation, s.value_min, s.value_max)
        self.change(start_rgb=a, end_rgb=b, pattern="horizontal")

    def refresh_files(self):
        self.files = self.app.settings_files()
        self.file_page = min(self.file_page, max(0, (len(self.files) - 1) // 5))

    def file_step(self, step):
        count = max(1, math.ceil(len(self.files) / 5))
        self.file_page = (self.file_page + step) % count

    def save(self):
        path = self.app.save_settings_snapshot()
        self.message = "Saved " + path.name
        self.refresh_files()

    def load(self, path):
        # Validate before replacing the live settings. Loading stops automatic
        # cycling so the chosen configuration is not overwritten 8 seconds later.
        settings = Settings.load(path)
        self.app.set_cycle(False)
        self.app.change(settings, "VR loaded " + path.name)
        if self.app.ui:
            self.app.ui.cycle.set(False)
            self.app.ui.refresh()
        self.message = "Loaded " + path.name

    def numeric_row(self, field, label, y, low, high, step):
        self.line(32, y + 16, label)
        self.button(field + ":minus", (470, y, 550, y + 58), "-",
                    lambda: self.nudge(field, -step, low, high))
        self.button(field, (564, y, 1054, y + 58), format(self.field_value(field), ".12g") + "   Edit",
                    lambda: self.edit(field, label))
        self.button(field + ":plus", (1068, y, 1148, y + 58), "+",
                    lambda: self.nudge(field, step, low, high))

    def rebuild(self):
        self.buttons, self.lines = [], []
        self.dirty = True
        if self.editor:
            self.build_editor()
            return
        for i, page in enumerate(self.PAGES):
            self.button("page:" + page, (24 + i*207, 82, 219 + i*207, 140), page,
                        lambda p=page: self.set_page(p), page == self.page)
        s = self.app.settings
        if self.page == "Source":
            for i, (key, label) in enumerate(MODES.items()):
                x, y = 24 + (i % 2)*624, 160 + (i // 2)*70
                self.button("mode:" + key, (x, y, x+608, y+60), label,
                            lambda k=key: self.change(mode=k), s.mode == key)
            self.button("pattern", (24, 378, 1256, 438), "Pattern: " + PATTERNS[s.pattern] + "   >",
                        lambda: self.cycle("pattern", list(PATTERNS)))
            for i, (field, label) in enumerate((("labels", "Labels"), ("swap", "Swap order"), ("animate", "Motion"))):
                x = 24 + i*416
                self.button(field, (x, 458, x+398, 518), label + (": ON" if getattr(s, field) else ": OFF"),
                            lambda f=field: self.toggle(f), getattr(s, field))
            self.button("ab", (24, 538, 630, 600), "A/B: 8-bit <-> 10-bit",
                        lambda: self.change(mode="10bit" if s.mode == "8bit" else "8bit"))
            self.button("cycle", (648, 538, 1256, 600), "Cycle presets: " + ("ON" if self.app.cycle_start is not None else "OFF"),
                        self.toggle_cycle, self.app.cycle_start is not None)
            self.line(30, 620, "Changes apply immediately. Hide menu to inspect the float test image.")
        elif self.page == "RGB":
            self.button("preset:prev", (24, 156, 132, 214), "<", lambda: self.app.next_preset(-1))
            self.line(154, 172, "Preset: " + list(PRESETS)[self.app.preset_index])
            self.button("preset:next", (1148, 156, 1256, 214), ">", lambda: self.app.next_preset(1))
            for i, field in enumerate(("start_rgb", "end_rgb")):
                for component, channel in enumerate("RGB"):
                    self.numeric_row(field + "." + str(component), ("Start " if i == 0 else "End ") + channel,
                                     230 + (i*3 + component)*68, 0, 1, .001)
        elif self.page in ("Hue", "Geometry"):
            fields = list(self.NUMBERS)[:4] if self.page == "Hue" else list(self.NUMBERS)[4:]
            for i, field in enumerate(fields):
                label, low, high, step = self.NUMBERS[field]
                self.numeric_row(field, label, 170 + i*88, low, high, step)
            if self.page == "Hue":
                self.button("make_hue", (24, 542, 630, 604), "Make gradient from hue", self.make_hue)
                self.button("atlas", (648, 542, 1256, 604), "Show 12-colour atlas", lambda: self.change(pattern="atlas"))
                self.line(32, 622, "HSV value is a colour component, not physical brightness or nits.")
            else:
                self.line(32, 466, "Face the test direction, then select Recenter below.")
                self.line(32, 510, "The panel stays world-fixed. Width, height and distance apply immediately.")
        elif self.page == "Session":
            self.line(32, 160, "Manually recorded conditions only. These do not change the stream or source.")
            self.button("stream_depth_requested", (24, 208, 1256, 268),
                        "Requested stream bits: " + s.stream_depth_requested + "   >",
                        lambda: self.cycle("stream_depth_requested", ["unknown", "8", "10"]))
            for i, (field, label) in enumerate((("streaming_app", "Streaming app / version"), ("codec", "Codec"),
                                              ("bitrate_mbps", "Bitrate target / observed"), ("notes", "Notes / SteamVR version"))):
                y = 290 + i*84
                self.button(field, (24, y, 1256, y+66), label + ": " + (getattr(s, field) or "Select to edit"),
                            lambda f=field, l=label: self.edit(f, l, False))
        elif self.page == "Files":
            self.button("save", (24, 160, 630, 218), "Save settings snapshot", self.save)
            self.button("refresh_files", (648, 160, 1256, 218), "Refresh saved files", self.refresh_files)
            for i, path in enumerate(self.files[self.file_page*5:self.file_page*5+5]):
                y = 234 + i*66
                # Parent disambiguates timestamped run directories and examples.
                self.button("file:" + str(path), (24, y, 1256, y+58), path.parent.name + " / " + path.name,
                            lambda p=path: self.load(p))
            self.button("files:prev", (24, 582, 230, 642), "< Previous", lambda: self.file_step(-1))
            self.line(268, 600, f"Page {self.file_page+1} / {max(1, math.ceil(len(self.files)/5))}   Select a file to load")
            self.button("files:next", (1050, 582, 1256, 642), "Next >", lambda: self.file_step(1))
        elif self.page == "Quit":
            self.line(32, 220, "Exit Colour Lab and end this test session?")
            self.button("quit:confirm", (24, 328, 630, 404), "Exit application", self.app.stop)
            self.button("quit:cancel", (648, 328, 1256, 404), "Keep testing", lambda: self.set_page("Source"))
        for i, (key, label, action) in enumerate((("recenter", "Recenter", self.app.recenter),
                                                   ("report", "Save run report", lambda: self.app.save_report(apply_ui=False)),
                                                   ("hide_menu", "Hide menu", lambda: self.app.toggle_vr_menu()),
                                                   ("quit", "Exit...", lambda: self.set_page("Quit")))):
            x = 24 + i*312
            self.button(key, (x, 668, x+296, 724), label, action)

    def build_editor(self):
        e = self.editor
        self.line(32, 92, e["label"] + (" - numeric entry" if e["numeric"] else " - text entry"))
        self.line(32, 130, self.message if self.message.startswith("Input error:") else
                  "First key replaces the current value. Apply commits; Cancel leaves it unchanged.")
        # The whole saved value remains intact; show its tail while typing.
        self.line(32, 198, ("..." if len(e["text"]) > 82 else "") + e["text"][-82:] + "|")
        rows = ["789", "456", "123", "0.-", "e+"] if e["numeric"] else [
            "1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm", ".,:;!?/-_@" if not self.shift else "()[]{}=+%#"]
        for row, chars in enumerate(rows):
            width = 100 if not e["numeric"] else 220
            for col, ch in enumerate(chars):
                text = ch.upper() if self.shift else ch
                x, y = 32 + col*(width+12), 258 + row*72
                self.button("key:" + text, (x, y, x+width, y+60), text, lambda c=text: self.type_key(c))
        if not e["numeric"]:
            self.button("shift", (920, 474, 1220, 534), "Shift", self.toggle_shift, self.shift)
            self.button("space", (32, 624, 400, 684), "Space", lambda: self.type_key(" "))
        self.button("append", (420, 624, 788, 684), "Keep text / append", self.append_text)
        self.button("backspace", (818, 624, 1030, 684), "Backspace", self.backspace)
        self.button("clear", (1042, 624, 1254, 684), "Clear", self.clear_text)
        self.button("apply", (32, 706, 400, 768), "Apply", self.apply_edit, True)
        self.button("cancel", (420, 706, 788, 768), "Cancel", self.cancel_edit)

    def toggle_shift(self):
        self.shift = not self.shift

    def hit(self, x, y):
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        return next((button for button in self.buttons if button.contains(x, y)), None)

    def move(self, x, y):
        button = self.hit(x, y)
        hover = button.key if button else None
        if hover != self.hover:
            self.hover = hover
            self.dirty = True

    def cancel_pointer(self):
        self.pressed, self.hover = None, None
        self.dirty = True

    def pointer(self, x, y, down):
        self.move(x, y)
        if down:
            self.pressed = self.hover
            self.dirty = True
            return
        pressed, self.pressed = self.pressed, None
        if pressed and pressed == self.hover:
            button = self.hit(x, y)
            try:
                button.action()
            except (ValueError, TypeError, OSError) as exc:
                self.message = "Input error: " + str(exc)
            self.rebuild()

    @staticmethod
    def fit(draw, text, font, width):
        text = str(text).replace("\n", " ").replace("\r", " ")
        if draw.textlength(text, font=font) <= width:
            return text
        # Bounded work even for a 4000-character note.
        low, high = 0, len(text)
        while low < high:
            mid = (low + high + 1) // 2
            if draw.textlength(text[:mid] + "...", font=font) <= width:
                low = mid
            else:
                high = mid - 1
        return text[:low] + "..."

    def render(self):
        image = Image.new("RGBA", (self.WIDTH, self.HEIGHT), "#101925")
        draw = ImageDraw.Draw(image)
        draw.text((28, 22), "SteamVR Colour Lab", font=self.title, fill="#f2f8ff")
        draw.text((764, 32), "IN-VR CONTROLS  /  Source precision test", font=self.small, fill="#94b1c7")
        for x, y, text in self.lines:
            draw.text((x, y), self.fit(draw, text, self.font, self.WIDTH-x-24), font=self.font, fill="#d0deed")
        for button in self.buttons:
            fill = "#176861" if button.selected else "#233548"
            if button.key == self.hover:
                fill = "#278879" if button.selected else "#395876"
            draw.rounded_rectangle(button.rect, radius=9, fill=fill,
                                   outline="#65d8c5" if button.key == self.hover else "#466075", width=2)
            x, y, right, bottom = button.rect
            text = self.fit(draw, button.label, self.font, right-x-26)
            draw.text(((x+right)/2, (y+bottom)/2-2), text, anchor="mm", font=self.font, fill="#f4f9ff")
        if not self.editor:
            draw.text((28, 744), self.fit(draw, self.message, self.small, 1220), font=self.small, fill="#a8d9d1")
        self.dirty = False
        return image
