"""Desktop controls. Values entered here drive the native VR scene directly."""
from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from dataclasses import replace
from pathlib import Path

from .core import MODES, PATTERNS, PRESETS, Settings, apply_preset, hue_endpoints


class Controls:
    def __init__(self, app):
        self.app = app
        self._last_settings = None
        self.root = tk.Tk()
        self.root.title("SteamVR Colour Lab — controls")
        height = min(900, self.root.winfo_screenheight() - 80)
        self.root.geometry(f"690x{max(640, height)}")
        self.root.minsize(650, 600)
        self.root.protocol("WM_DELETE_WINDOW", self.app.stop)
        self.root.bind("<Escape>", lambda _: self.app.stop())
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 17, "bold"))
        style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        canvas = tk.Canvas(self.root, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(canvas, padding=16)
        item = canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(item, width=e.width))
        def scroll(event):
            # Do not steal the wheel from editable or dropdown inputs.
            if event.widget.winfo_class() in ("TCombobox", "TSpinbox", "Entry", "TEntry"):
                return
            units = -1 if getattr(event, "num", 0) == 4 else 1
            if getattr(event, "delta", 0):
                units = -1 if event.delta > 0 else 1
            canvas.yview_scroll(units * 3, "units")
        for event_name in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind(event_name, scroll)
        b = self.body
        b.columnconfigure(0, weight=1)
        ttk.Label(b, text="SteamVR Colour Lab", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(b, text="Source precision test • linear RGBA16F eye buffers").grid(row=1, column=0, sticky="w", pady=(2, 10))
        self.status = tk.StringVar(value="Initialising…")
        ttk.Label(b, textvariable=self.status, wraplength=570).grid(row=2, column=0, sticky="ew", pady=(0, 10))

        display = self.section(b, "1  Source and pattern", 3)
        self.mode = tk.StringVar()
        self.pattern = tk.StringVar()
        self.combo(display, "Source mode", self.mode, MODES.values(), 0, self.apply)
        self.combo(display, "Pattern", self.pattern, PATTERNS.values(), 1, self.apply)
        options = ttk.Frame(display)
        options.grid(row=2, column=0, columnspan=3, sticky="w", pady=5)
        self.labels, self.swap, self.animate = tk.BooleanVar(), tk.BooleanVar(), tk.BooleanVar()
        for label, var in (("Show labels", self.labels), ("Swap comparison order", self.swap), ("Animate", self.animate)):
            ttk.Checkbutton(options, text=label, variable=var, command=self.apply).pack(side="left", padx=(0, 12))

        colours = self.section(b, "2  Colours — sRGB-encoded numbers, 0 to 1", 4)
        self.preset = tk.StringVar(value=next(iter(PRESETS)))
        self.combo(colours, "Preset", self.preset, PRESETS.keys(), 0, self.choose_preset)
        self.rgb_vars = []
        for row, label in ((1, "Start RGB"), (2, "End RGB")):
            ttk.Label(colours, text=label).grid(row=row, column=0, sticky="w", pady=3)
            entries = ttk.Frame(colours)
            entries.grid(row=row, column=1, sticky="ew")
            variables = [tk.StringVar() for _ in range(3)]
            self.rgb_vars.append(variables)
            for idx, var in enumerate(variables):
                entry = ttk.Entry(entries, textvariable=var, width=11)
                entry.grid(row=0, column=idx, padx=(0, 5), sticky="ew")
                entries.columnconfigure(idx, weight=1)
                entry.bind("<Return>", self.apply)
            ttk.Button(colours, text="Pick…", command=lambda n=row-1: self.pick_colour(n)).grid(row=row, column=2, padx=(5, 0))
        ttk.Label(colours, text="Numeric fields retain fractional values. The colour picker is an 8-bit convenience input.",
                  wraplength=550).grid(row=3, column=0, columnspan=3, sticky="w", pady=(5, 2))
        ttk.Button(colours, text="Apply custom RGB", command=self.apply).grid(row=4, column=1, sticky="w", pady=4)

        hue = self.section(b, "3  Hue controls / atlas", 5)
        self.hsv_vars = {}
        labels = (("hue", "Hue (0–360°)", 0, 360, 1), ("saturation", "Saturation", 0, 1, .05),
                  ("value_min", "Minimum value", 0, 1, .005), ("value_max", "Maximum value", 0, 1, .005))
        for row, (key, text, low, high, increment) in enumerate(labels):
            ttk.Label(hue, text=text).grid(row=row, column=0, sticky="w", pady=2)
            variable = tk.StringVar()
            self.hsv_vars[key] = variable
            entry = ttk.Spinbox(hue, from_=low, to=high, increment=increment, textvariable=variable, width=12, command=self.apply)
            entry.grid(row=row, column=1, sticky="w", pady=2)
            entry.bind("<Return>", self.apply)
        ttk.Button(hue, text="Make gradient from hue", command=self.make_hue).grid(row=4, column=0, pady=5, sticky="w")
        ttk.Button(hue, text="Show 12-colour atlas", command=self.show_atlas).grid(row=4, column=1, pady=5, sticky="w")

        geometry = self.section(b, "4  Panel geometry and reproducibility", 6)
        self.geometry_vars = {}
        row = ttk.Frame(geometry)
        row.grid(row=0, column=0, columnspan=3, sticky="w")
        for index, (key, label) in enumerate((("panel_width", "Width m"), ("panel_height", "Height m"), ("panel_distance", "Distance m"))):
            variable = tk.StringVar()
            self.geometry_vars[key] = variable
            ttk.Label(row, text=label).grid(row=0, column=index*2, padx=(0, 4))
            entry = ttk.Entry(row, textvariable=variable, width=7)
            entry.grid(row=0, column=index*2+1, padx=(0, 10))
            entry.bind("<Return>", self.apply)
        buttons = ttk.Frame(geometry)
        buttons.grid(row=1, column=0, columnspan=3, sticky="w", pady=6)
        for text, command in (("Apply", self.apply), ("Recenter", app.recenter), ("Save settings…", self.save),
                              ("Load settings…", self.load), ("Save run report", app.save_report)):
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=(0, 4))
        self.cycle = tk.BooleanVar(value=False)
        ttk.Checkbutton(geometry, text="Cycle all colour presets every 8 seconds", variable=self.cycle,
                        command=lambda: app.set_cycle(self.cycle.get())).grid(row=2, column=0, columnspan=3, sticky="w")
        ttk.Button(geometry, text="Show VR controls (F1)", command=lambda: app.show_vr_menu()).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=5)

        notes = self.section(b, "5  Manually recorded streaming conditions (not controlled by the app)", 7)
        self.note_vars = {}
        self.depth = tk.StringVar()
        self.combo(notes, "Requested stream bits", self.depth, ("unknown", "8", "10"), 0, self.apply)
        for row, (name, text) in enumerate((("streaming_app", "Streaming app / version"), ("codec", "Codec"),
                                           ("bitrate_mbps", "Bitrate target / observed"),
                                           ("notes", "Notes / SteamVR version")), 1):
            variable = tk.StringVar()
            self.note_vars[name] = variable
            ttk.Label(notes, text=text).grid(row=row, column=0, sticky="w", pady=2)
            entry = ttk.Entry(notes, textvariable=variable)
            entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=2)
            entry.bind("<Return>", self.apply)
        ttk.Label(b, text="Preview-window keys: 1=8-bit  2=10-bit  3=reference  4=compare  5=three\n"
                             "Space=A/B  ←/→=preset  P=pattern  X=swap  L=labels  M=motion\n"
                             "R=recenter  F1=VR menu  F5=save report  Esc=quit\n"
                             "Close the SteamVR dashboard before judging banding. Desktop preview is not 10-bit proof.",
                  wraplength=575).grid(row=8, column=0, sticky="w", pady=(8, 0))
        self.refresh()

    @staticmethod
    def section(parent, text, row):
        frame = ttk.LabelFrame(parent, text=text, padding=9, style="Section.TLabelframe")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(1, weight=1)
        return frame

    @staticmethod
    def combo(frame, label, var, values, row, command):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
        box = ttk.Combobox(frame, values=list(values), textvariable=var, state="readonly")
        box.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
        box.bind("<<ComboboxSelected>>", command)
        return box

    def read(self):
        data = self.app.settings.to_dict()
        data["mode"] = next(k for k, v in MODES.items() if v == self.mode.get())
        data["pattern"] = next(k for k, v in PATTERNS.items() if v == self.pattern.get())
        data["start_rgb"] = tuple(float(v.get()) for v in self.rgb_vars[0])
        data["end_rgb"] = tuple(float(v.get()) for v in self.rgb_vars[1])
        for key, variable in {**self.hsv_vars, **self.geometry_vars}.items():
            data[key] = float(variable.get())
        for key, variable in self.note_vars.items():
            data[key] = variable.get()
        for name in ("labels", "swap", "animate"):
            data[name] = getattr(self, name).get()
        data["stream_depth_requested"] = self.depth.get()
        return Settings.from_dict(data)

    def apply(self, event=None):
        try:
            self.app.change(self.read(), "controls")
            return True
        except (ValueError, StopIteration) as exc:
            self.status.set("Input error: " + str(exc))
            return False

    def refresh(self):
        s = self.app.settings
        self._last_settings = s
        self.mode.set(MODES[s.mode])
        self.pattern.set(PATTERNS[s.pattern])
        for variables, values in zip(self.rgb_vars, (s.start_rgb, s.end_rgb)):
            for var, value in zip(variables, values):
                var.set(repr(value))
        for key, variable in {**self.hsv_vars, **self.geometry_vars, **self.note_vars}.items():
            value = getattr(s, key)
            variable.set(repr(value) if isinstance(value, (float, int)) else value)
        for name in ("labels", "swap", "animate"):
            getattr(self, name).set(getattr(s, name))
        self.depth.set(s.stream_depth_requested)

    def choose_preset(self, event=None):
        self.app.preset_index = list(PRESETS).index(self.preset.get())
        self.app.change(apply_preset(self.app.settings, self.preset.get()), "preset")
        self.refresh()

    def pick_colour(self, endpoint):
        if not self.apply():
            return
        values = self.app.settings.start_rgb if endpoint == 0 else self.app.settings.end_rgb
        initial = "#" + "".join(f"{round(v*255):02x}" for v in values)
        colour, _ = colorchooser.askcolor(color=initial, parent=self.root)
        if colour:
            values = tuple(v / 255.0 for v in colour)
            key = "start_rgb" if endpoint == 0 else "end_rgb"
            self.app.change(replace(self.app.settings, **{key: values}), "colour picker")
            self.refresh()

    def make_hue(self):
        if not self.apply():
            return
        s = self.app.settings
        a, b = hue_endpoints(s.hue, s.saturation, s.value_min, s.value_max)
        self.app.change(replace(s, start_rgb=a, end_rgb=b, pattern="horizontal"), "hue gradient")
        self.refresh()

    def show_atlas(self):
        if self.apply():
            self.app.change(replace(self.app.settings, pattern="atlas"), "hue atlas")
            self.refresh()

    def save(self):
        if not self.apply():
            return
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".json", filetypes=[("Settings", "*.json")])
        if path:
            try:
                self.app.settings.save(Path(path))
                self.app.note("Saved settings: " + path)
            except OSError as exc:
                self.status.set("Cannot save settings: " + str(exc))

    def load(self):
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("Settings", "*.json")])
        if path:
            try:
                self.app.change(Settings.load(Path(path)), "loaded " + Path(path).name)
                self.refresh()
            except (OSError, ValueError, TypeError) as exc:
                self.status.set("Cannot load settings: " + str(exc))

    def pump(self):
        if self.app.settings != self._last_settings:
            self.refresh()
        self.root.update_idletasks()
        self.root.update()

    def close(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
