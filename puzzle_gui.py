"""A persistent editor for the Jane Street arc puzzle (no solving logic)."""

import argparse
import copy
import colorsys
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from PIL import Image, ImageDraw, ImageTk


DEFAULT_STATE = Path(__file__).with_name("puzzle_state.json")
DATA_DIRECTORY = Path(__file__).resolve().parent / "grids"
ARC_CYCLE = (None, "tl", "tr", "br", "bl")


def arc_endpoints(row, column, orientation):
    """Return exact grid corners and tangent vectors pointing into the arc."""
    return {
        "tl": (((row, column + 1), (0, 1)), ((row + 1, column), (1, 0))),
        "tr": (((row, column), (0, 1)), ((row + 1, column + 1), (-1, 0))),
        "br": (((row, column + 1), (-1, 0)), ((row + 1, column), (0, -1))),
        "bl": (((row, column), (1, 0)), ((row + 1, column + 1), (0, -1))),
    }[orientation]


def smooth_arc_groups(state):
    """Join arcs only when their inward tangents at a shared corner oppose."""
    corners, parent = {}, {}
    for r, row in enumerate(state["cells"]):
        for c, cell in enumerate(row):
            if cell["arc"] is None:
                continue
            arc = (r, c)
            parent[arc] = arc
            for corner, tangent in arc_endpoints(r, c, cell["arc"]):
                corners.setdefault(corner, []).append((arc, tangent))

    def find(arc):
        while parent[arc] != arc:
            parent[arc] = parent[parent[arc]]
            arc = parent[arc]
        return arc

    for entries in corners.values():
        for i, (first, tangent) in enumerate(entries):
            for second, other in entries[i + 1:]:
                if tangent == (-other[0], -other[1]):
                    parent[find(second)] = find(first)
    roots = {}
    groups = {}
    for arc in parent:
        root = find(arc)
        groups[arc] = roots.setdefault(root, len(roots))
    neighbors = {group: set() for group in roots.values()}
    conflicts = set()
    for corner, entries in corners.items():
        for i, (first, tangent) in enumerate(entries):
            for second, other in entries[i + 1:]:
                if tangent == (-other[0], -other[1]):
                    continue
                a, b = groups[first], groups[second]
                if a == b:
                    # A smooth chain can return to its own end with a sharp join.
                    conflicts.add(corner)
                else:
                    neighbors[a].add(b)
                    neighbors[b].add(a)
    palette = ["#d62728", "#1769aa", "#8b35b5", "#008577", "#b56300",
               "#c1277b", "#596a15", "#5646a5"]
    assigned = {}
    for group in sorted(neighbors, key=lambda g: (-len(neighbors[g]), g)):
        forbidden = {assigned[n] for n in neighbors[group] if n in assigned}
        index = next(i for i in range(len(palette) + 1) if i not in forbidden)
        if index == len(palette):
            rgb = colorsys.hsv_to_rgb((index * .61803398875) % 1, .8, .65)
            palette.append("#" + "".join(f"{round(v * 255):02x}" for v in rgb))
        assigned[group] = index
    colors = {arc: palette[assigned[group]] for arc, group in groups.items()}
    return groups, colors, conflicts


def determine_regions(state):
    """Connect cell fragments across full edges, never through a corner alone.

    Fragment 0 is the quarter-disc (or an unsplit cell), fragment 1 its
    complement. An arc is dangling exactly when its fragments reconnect.
    """
    parent = {}
    for r, row in enumerate(state["cells"]):
        for c, cell in enumerate(row):
            for side in range(2 if cell["arc"] else 1):
                parent[(r, c, side)] = (r, c, side)

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def edge_fragment(r, c, edge):
        arc = state["cells"][r][c]["arc"]
        inside_edges = {"tl": "NW", "tr": "NE", "br": "SE", "bl": "SW"}
        return (r, c, 0 if arc is None or edge in inside_edges[arc] else 1)

    for r, row in enumerate(state["cells"]):
        for c, cell in enumerate(row):
            if c + 1 < state["columns"]:
                parent[find(edge_fragment(r, c, "E"))] = find(edge_fragment(r, c + 1, "W"))
            if r + 1 < state["rows"]:
                parent[find(edge_fragment(r, c, "S"))] = find(edge_fragment(r + 1, c, "N"))
    roots, regions = {}, {}
    for fragment in parent:
        root = find(fragment)
        regions[fragment] = roots.setdefault(root, len(roots))
    adjacency = {region: set() for region in roots.values()}
    invalid_arcs = []
    for r, row in enumerate(state["cells"]):
        for c, cell in enumerate(row):
            if cell["arc"]:
                a, b = regions[(r, c, 0)], regions[(r, c, 1)]
                if a == b:
                    invalid_arcs.append((r, c))
                else:
                    adjacency[a].add(b)
                    adjacency[b].add(a)
    palette = ["#f8d0d0", "#c9ddfa", "#f4dfb2", "#d9cdf4",
               "#c7e9df", "#f3cde7", "#e4e9bc", "#cce8ef"]
    assigned = {}
    for region in sorted(adjacency, key=lambda n: (-len(adjacency[n]), n)):
        used = {assigned[n] for n in adjacency[region] if n in assigned}
        index = next(i for i in range(len(palette) + 1) if i not in used)
        if index == len(palette):
            rgb = colorsys.hsv_to_rgb((index * .61803398875) % 1, .22, .97)
            palette.append("#" + "".join(f"{round(v * 255):02x}" for v in rgb))
        assigned[region] = index
    colors = {fragment: palette[assigned[region]] for fragment, region in regions.items()}
    return regions, colors, invalid_arcs


@dataclass(frozen=True)
class RegionArea:
    """Exact area: whole_cells + arc_outsides + (insides - outsides) * pi/4."""

    whole_cells: int = 0
    arc_insides: int = 0
    arc_outsides: int = 0

    @property
    def constant(self):
        return self.whole_cells + self.arc_outsides

    @property
    def pi_quarters(self):
        return self.arc_insides - self.arc_outsides

    @property
    def is_integer(self):
        return self.arc_insides == self.arc_outsides

    @property
    def integer_area(self):
        return self.constant if self.is_integer else None

    def __str__(self):
        if self.is_integer:
            return str(self.constant)
        coefficient = abs(self.pi_quarters)
        term = "π/4" if coefficient == 1 else f"{coefficient}π/4"
        if self.constant == 0:
            return term if self.pi_quarters > 0 else f"−{term}"
        sign = "+" if self.pi_quarters > 0 else "−"
        return f"{self.constant} {sign} {term}"


def determine_region_areas(state, regions=None):
    """Return region IDs mapped to exact cell-fragment counts, without floats.

    By default determine connectivity first. Passing an existing fragment-to-
    region mapping avoids repeating that work. Dangling-arc validity remains
    separate: a region may have integer area while containing both arc sides.
    """
    if regions is None:
        regions = determine_regions(state)[0]
    counts = {}
    for (r, c, side), region in regions.items():
        tally = counts.setdefault(region, [0, 0, 0])
        if state["cells"][r][c]["arc"] is None:
            tally[0] += 1
        elif side == 0:
            tally[1] += 1
        else:
            tally[2] += 1
    return {region: RegionArea(*tally) for region, tally in counts.items()}


def region_area_positions(state, regions):
    """Choose one interior label anchor per region, preferring roomy cells."""
    candidates = {}
    for (r, c, side), region in regions.items():
        cell = state["cells"][r][c]
        arc = cell["arc"]
        if arc is None:
            x, y, width, priority = .5, .5, .85, 3
            if cell["number"] is not None:
                y = .78
        else:
            # Reflect points from a top-left-centered quarter circle.
            offset = .30 if side == 0 else .86
            x = 1 - offset if arc in ("tr", "br") else offset
            y = 1 - offset if arc in ("bl", "br") else offset
            width, priority = (.55, 2) if side == 0 else (.26, 1)
        rank = (priority, cell["number"] is None)
        if region not in candidates or rank > candidates[region][0]:
            candidates[region] = (rank, (r, c, x, y, width))
    return {region: candidate[1] for region, candidate in candidates.items()}


def render_grid(state, cell_size, arc_colors=None, region_colors=None):
    """Draw at four times the display resolution for smooth circular edges."""
    scale, margin = 4, 16
    rows, columns = state["rows"], state["columns"]
    width = round(columns * cell_size + 2 * margin)
    height = round(rows * cell_size + 2 * margin)
    image = Image.new("RGB", (width * scale, height * scale), "#e9edf1")
    painter = ImageDraw.Draw(image)

    def box(x0, y0, x1, y1):
        return tuple(round(v * scale) for v in (x0, y0, x1, y1))

    # Paint all backgrounds first so neighboring cells cannot cover arc ends.
    for r, row in enumerate(state["cells"]):
        for c, cell in enumerate(row):
            x, y = margin + c * cell_size, margin + r * cell_size
            painter.rectangle(box(x, y, x + cell_size, y + cell_size),
                              fill=(region_colors[(r, c, 1 if cell["arc"] else 0)]
                                    if region_colors is not None else
                                    "#c5e5c8" if cell["green"] else "white"))
            if region_colors is not None and cell["arc"]:
                corner = cell["arc"]
                cx = x + (corner in ("tr", "br")) * cell_size
                cy = y + (corner in ("bl", "br")) * cell_size
                start = {"tl": 0, "tr": 90, "br": 180, "bl": 270}[corner]
                polygon = [(round(cx * scale), round(cy * scale))]
                for step in range(129):
                    angle = math.radians(start + 90 * step / 128)
                    polygon.append((round((cx + cell_size * math.cos(angle)) * scale),
                                    round((cy + cell_size * math.sin(angle)) * scale)))
                painter.polygon(polygon, fill=region_colors[(r, c, 0)])
            if region_colors is not None and cell["green"]:
                # Preserve the puzzle's green-cell markings under the overlay.
                painter.rectangle(box(x + 5, y + 5, x + 11, y + 11),
                                  fill="#83bd8b", outline="#35683c", width=scale)
    for r in range(1, rows):
        y = margin + r * cell_size
        painter.line(box(margin, y, margin + columns * cell_size, y),
                     fill="#89939e", width=scale)
    for c in range(1, columns):
        x = margin + c * cell_size
        painter.line(box(x, margin, x, margin + rows * cell_size),
                     fill="#89939e", width=scale)
    for r, row in enumerate(state["cells"]):
        for c, cell in enumerate(row):
            corner = cell["arc"]
            if corner is None:
                continue
            cx = margin + (c + (corner in ("tr", "br"))) * cell_size
            cy = margin + (r + (corner in ("bl", "br"))) * cell_size
            start = {"tl": 0, "tr": 90, "br": 180, "bl": 270}[corner]
            color = (arc_colors or {}).get((r, c), "black")
            # Pillow's arc stroke lies inside its bounding ellipse, shifting
            # endpoints for different centers. A centered polyline keeps the
            # radius and shared grid-corner endpoints exact.
            points = []
            for step in range(129):
                angle = math.radians(start + 90 * step / 128)
                points.append((round((cx + cell_size * math.cos(angle)) * scale),
                               round((cy + cell_size * math.sin(angle)) * scale)))
            painter.line(points, fill=color, width=3 * scale, joint="curve")
            radius = 1.5 * scale
            for px, py in (points[0], points[-1]):
                painter.ellipse((px - radius, py - radius, px + radius, py + radius),
                                fill=color)
    painter.line([ (round(x * scale), round(y * scale)) for x, y in
                  ((margin, margin), (margin + columns * cell_size, margin),
                   (margin + columns * cell_size, margin + rows * cell_size),
                   (margin, margin + rows * cell_size), (margin, margin))],
                 fill="black", width=4 * scale, joint="curve")
    return image.resize((width, height), Image.Resampling.LANCZOS)


def grid_name(value):
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value)
            or value.upper() in {"CON", "PRN", "AUX", "NUL",
                                 *(f"COM{i}" for i in range(1, 10)),
                                 *(f"LPT{i}" for i in range(1, 10))}):
        raise argparse.ArgumentTypeError("Use up to 64 letters, digits, hyphens, or underscores, starting with a letter or digit; avoid reserved Windows names.")
    return value


def parse_grid_size(value):
    parts = re.split(r"\s*[xX×]\s*", value.strip())
    if len(parts) not in (1, 2):
        raise ValueError("Enter a size such as 10 or 8x12 (rows x columns).")
    try:
        rows = int(parts[0])
        columns = int(parts[-1])
    except ValueError:
        raise ValueError("Enter a size such as 10 or 8x12 (rows x columns).") from None
    if not (1 <= rows <= 50 and 1 <= columns <= 50):
        raise ValueError("Use 1–50 rows and columns.")
    return rows, columns


def read_state(path):
    try:
        return validate_state(json.loads(path.read_text(encoding="utf-8")))
    except (KeyError, TypeError) as exc:
        raise ValueError("Invalid saved puzzle data.") from exc


def prepare_grid(name, size=None):
    path = DATA_DIRECTORY / f"{name}.json"
    if path.exists():
        state = read_state(path)
        if size is not None and (state["rows"], state["columns"]) != size:
            raise ValueError("That name already has a different grid size. Use its saved size or choose another name.")
    else:
        if size is None:
            raise ValueError("A grid size is required for a new puzzle.")
        rows, columns = size
        state = {"version": 1, "rows": rows, "columns": columns,
                 "cells": blank_grid(rows, columns)}
        validate_state(state)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    return path


def choose_grid(root):
    dialog = tk.Toplevel(root)
    dialog.title("Open puzzle grid")
    dialog.resizable(False, False)
    form = ttk.Frame(dialog, padding=20)
    form.pack(fill="both", expand=True)
    name, size = tk.StringVar(), tk.StringVar(value="10")
    ttk.Label(form, text="Puzzle name").grid(row=0, column=0, sticky="w", padx=(0, 12))
    entry = ttk.Entry(form, textvariable=name, width=32)
    entry.grid(row=0, column=1, pady=5)
    ttk.Label(form, text="Grid size").grid(row=1, column=0, sticky="w")
    ttk.Entry(form, textvariable=size, width=32).grid(row=1, column=1, pady=5)
    ttk.Label(form, text="For example: 10 for a square, or 8x12 for rows x columns.").grid(row=2, column=0, columnspan=2, pady=5)
    result = []

    def open_grid(event=None):
        try:
            chosen = grid_name(name.get().strip())
            path = prepare_grid(chosen, parse_grid_size(size.get()))
            result.append((chosen, path))
            dialog.destroy()
        except (ValueError, OSError, argparse.ArgumentTypeError) as exc:
            messagebox.showerror("Could not open grid", str(exc), parent=dialog)

    ttk.Button(form, text="Open grid", command=open_grid).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
    dialog.bind("<Return>", open_grid)
    dialog.bind("<Escape>", lambda event: dialog.destroy())
    entry.focus_set()
    root.wait_window(dialog)
    return result[0] if result else None


def blank_grid(rows, columns):
    return [[{"green": False, "number": None, "arc": None}
             for _ in range(columns)] for _ in range(rows)]


def validate_state(state):
    rows, columns = state["rows"], state["columns"]
    if type(rows) is not int or type(columns) is not int or not (1 <= rows <= 50 and 1 <= columns <= 50):
        raise ValueError("Grid dimensions must be integers between 1 and 50.")
    cells = state["cells"]
    if len(cells) != rows or any(len(row) != columns for row in cells):
        raise ValueError("Cell data does not match the grid dimensions.")
    for row in cells:
        for cell in row:
            if type(cell["green"]) is not bool:
                raise ValueError("Invalid green-cell value.")
            number = cell["number"]
            if number is not None and (type(number) is not int or number < 0):
                raise ValueError("Clues must be nonnegative integers.")
            if cell["arc"] not in (None, "tl", "tr", "br", "bl"):
                raise ValueError("Invalid arc orientation.")
            if cell["green"] and cell["arc"] is not None:
                raise ValueError("Green cells cannot contain arcs.")
    return state


class PuzzleEditor:
    def __init__(self, root, path, name=None):
        self.root, self.path = root, path
        self.state = {"version": 1, "rows": 10, "columns": 10,
                      "cells": blank_grid(10, 10)}
        load_error = None
        if path.exists():
            try:
                self.state = validate_state(json.loads(path.read_text(encoding="utf-8")))
            except (ValueError, KeyError, TypeError, OSError) as exc:
                load_error = str(exc)
        self.undo_stack, self.redo_stack = [], []
        self.smooth_colors = None
        self.region_colors = None
        self.area_labels = None
        self.selected = None
        self.fresh_entry = True
        self.mode = tk.StringVar(value="arc")
        self.status = tk.StringVar()
        root.title(f"Jane Street — Arc Puzzle Editor — {name or path.stem}")
        root.geometry("850x850")
        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        for label, value in [("Green cells (Ctrl+1)", "green"), ("Digits (Ctrl+2)", "digit"), ("Arcs (Ctrl+3)", "arc")]:
            ttk.Radiobutton(toolbar, text=label, value=value, variable=self.mode,
                            command=self.mode_changed).pack(side="left", padx=5)
        self.undo_button = ttk.Button(toolbar, text="Undo", command=self.undo)
        self.undo_button.pack(side="left", padx=(20, 4))
        self.redo_button = ttk.Button(toolbar, text="Redo", command=self.redo)
        self.redo_button.pack(side="left", padx=4)
        ttk.Button(toolbar, text="Save", command=self.save).pack(side="right")
        dimensions = ttk.Frame(root, padding=(8, 0, 8, 8))
        dimensions.pack(fill="x")
        ttk.Label(dimensions, text=f"{self.state['rows']}x{self.state['columns']} grid").pack(side="left", padx=(4, 12))
        ttk.Button(dimensions, text="Check smooth arcs", command=self.check_smooth_arcs).pack(side="left", padx=4)
        ttk.Button(dimensions, text="Determine regions", command=self.check_regions).pack(side="left", padx=4)
        ttk.Button(dimensions, text="Compute region areas", command=self.compute_region_areas).pack(side="left", padx=4)
        ttk.Button(dimensions, text="Clear colors", command=self.clear_arc_colors).pack(side="left", padx=4)
        ttk.Label(root, text="Green: click to toggle • Digits: select a cell and type • "
                  "Arcs: click to cycle through four curves, then no arc\n"
                  "Backspace edits a clue • Delete clears the current mode’s mark • "
                  "Right-click removes a mark • Ctrl+Z / Ctrl+Y undo / redo",
                  padding=(12, 0, 12, 8)).pack(fill="x")
        frame = ttk.Frame(root)
        frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(frame, background="#e9edf1", highlightthickness=0, takefocus=True)
        vertical = ttk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        ttk.Label(root, textvariable=self.status, padding=8).pack(fill="x")
        self.canvas.bind("<Configure>", lambda event: self.draw())
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<Button-3>", lambda event: self.click(event, erase=True))
        self.canvas.bind("<Key>", self.key)
        root.bind("<Control-z>", lambda event: self.undo())
        root.bind("<Control-y>", lambda event: self.redo())
        root.bind("<Control-Shift-Z>", lambda event: self.redo())
        root.bind("<Control-s>", lambda event: self.save())
        for number, mode in enumerate(("green", "digit", "arc"), start=1):
            root.bind(f"<Control-Key-{number}>",
                      lambda event, chosen=mode: self.set_mode(chosen))
        root.bind("<Escape>", self.clear_selection)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.draw()
        self.status.set(f"Autosave: {self.path}")
        if load_error:
            messagebox.showwarning("Could not load saved puzzle",
                                   f"{load_error}\nThe saved file has not been overwritten.")

    def mode_changed(self):
        self.fresh_entry = True
        self.canvas.focus_set()

    def set_mode(self, mode):
        self.mode.set(mode)
        self.mode_changed()
        return "break"

    def clear_selection(self, event=None):
        self.selected = None
        self.fresh_entry = True
        self.draw()
        return "break"

    def commit(self, previous):
        if previous == self.state:
            return
        self.undo_stack.append(previous)
        self.redo_stack.clear()
        self.smooth_colors = None
        self.region_colors = None
        self.area_labels = None
        self.draw()
        self.save()

    def save(self):
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(self.state, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, self.path)
            self.status.set(f"Saved automatically — {self.path.name}")
            return True
        except OSError as exc:
            self.status.set(f"Save failed: {exc}")
            return False

    def close(self):
        # Every edit is already saved; closing an untouched invalid file preserves it.
        self.root.destroy()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(copy.deepcopy(self.state))
            self.state = self.undo_stack.pop()
            self.after_history()
        return "break"

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(copy.deepcopy(self.state))
            self.state = self.redo_stack.pop()
            self.after_history()
        return "break"

    def after_history(self):
        self.smooth_colors = None
        self.region_colors = None
        self.area_labels = None
        self.selected = None
        self.fresh_entry = True
        self.draw()
        self.save()

    def check_smooth_arcs(self):
        groups, self.smooth_colors, conflicts = smooth_arc_groups(self.state)
        self.draw()
        message = f"{len(set(groups.values()))} smooth arc pieces across {len(groups)} arcs."
        if conflicts:
            message += (f" {len(conflicts)} sharp self-joins: a smooth chain returns to itself; "
                        "its two ends cannot have different colors while keeping the chain one color.")
        self.status.set(message)

    def check_regions(self):
        regions, self.region_colors, invalid_arcs = determine_regions(self.state)
        areas = determine_region_areas(self.state, regions)
        self.draw()
        count = len(set(regions.values()))
        if invalid_arcs:
            cells = ", ".join(f"({r + 1}, {c + 1})" for r, c in invalid_arcs)
            self.status.set(f"{count} regions — INVALID: both sides of an arc reconnect in cells (row, column): {cells}.")
        else:
            self.status.set(f"{count} regions — every arc separates distinct regions. "
                            f"{sum(area.is_integer for area in areas.values())}/{count} regions have integer area.")

    def compute_region_areas(self):
        regions, self.region_colors, invalid_arcs = determine_regions(self.state)
        areas = determine_region_areas(self.state, regions)
        self.area_labels = [(position, str(areas[region]))
                            for region, position in region_area_positions(self.state, regions).items()]
        self.draw()
        self.status.set(f"Areas computed for {len(areas)} regions; "
                        f"{sum(area.is_integer for area in areas.values())} have integer area. "
                        f"{len(invalid_arcs)} arcs have both sides in one region. Blue labels show areas.")

    def clear_arc_colors(self):
        self.smooth_colors = None
        self.region_colors = None
        self.area_labels = None
        self.draw()
        self.status.set("Analysis colors cleared.")

    def draw(self):
        self.canvas.delete("all")
        rows, columns = self.state["rows"], self.state["columns"]
        self.size = max(36, min(80, (self.canvas.winfo_width() - 32) / columns,
                                (self.canvas.winfo_height() - 32) / rows))
        size, margin = self.size, 16
        self.canvas.configure(scrollregion=(0, 0, columns * size + 32, rows * size + 32))
        self.grid_image = ImageTk.PhotoImage(render_grid(self.state, size, self.smooth_colors,
                                                        self.region_colors), master=self.canvas)
        self.canvas.create_image(0, 0, image=self.grid_image, anchor="nw")
        for r, row in enumerate(self.state["cells"]):
            for c, cell in enumerate(row):
                x, y = margin + c * size, margin + r * size
                if cell["number"] is not None:
                    self.canvas.create_text(x + size / 2, y + size / 2,
                        text=str(cell["number"]), font=("Segoe UI", max(10, int(size * .24)), "bold"))
                if self.selected == (r, c):
                    self.canvas.create_rectangle(x + 3, y + 3, x + size - 3, y + size - 3,
                                                 outline="#e89520", width=3)
        for (r, c, x, y, width), area in self.area_labels or []:
            self.canvas.create_text(margin + (c + x) * size, margin + (r + y) * size,
                                    text=area, fill="#174377",
                                    font=("Segoe UI", max(7, min(11, int(size * .14)))),
                                    width=max(16, int(width * size)), justify="center")
        self.undo_button.configure(state="normal" if self.undo_stack else "disabled")
        self.redo_button.configure(state="normal" if self.redo_stack else "disabled")

    def click(self, event, erase=False):
        self.canvas.focus_set()
        x, y = self.canvas.canvasx(event.x) - 16, self.canvas.canvasy(event.y) - 16
        r, c = int(y // self.size), int(x // self.size)
        if not (0 <= r < self.state["rows"] and 0 <= c < self.state["columns"]):
            return
        self.selected = (r, c)
        self.fresh_entry = True
        previous = copy.deepcopy(self.state)
        cell = self.state["cells"][r][c]
        mode = self.mode.get()
        if mode == "green":
            cell["green"] = False if erase else not cell["green"]
            if cell["green"]:
                cell["arc"] = None
        elif mode == "digit":
            if erase:
                cell["number"] = None
        elif erase:
            cell["arc"] = None
        elif not cell["green"]:
            cell["arc"] = ARC_CYCLE[(ARC_CYCLE.index(cell["arc"]) + 1) % len(ARC_CYCLE)]
        self.commit(previous)
        self.draw()

    def key(self, event):
        if event.keysym == "Escape":
            return self.clear_selection(event)
        if self.selected is None or event.state & 4:
            return
        r, c = self.selected
        if event.keysym in ("Left", "Right", "Up", "Down"):
            dr, dc = {"Left": (0, -1), "Right": (0, 1), "Up": (-1, 0), "Down": (1, 0)}[event.keysym]
            self.selected = (max(0, min(self.state["rows"] - 1, r + dr)),
                             max(0, min(self.state["columns"] - 1, c + dc)))
            self.fresh_entry = True
            self.draw()
            return "break"
        previous = copy.deepcopy(self.state)
        cell = self.state["cells"][r][c]
        if event.keysym == "Delete":
            cell[{"digit": "number", "arc": "arc", "green": "green"}[self.mode.get()]] = False if self.mode.get() == "green" else None
            self.fresh_entry = True
        elif self.mode.get() == "digit":
            if event.keysym == "BackSpace":
                text = str(cell["number"])[:-1] if cell["number"] is not None else ""
                cell["number"] = int(text) if text else None
                self.fresh_entry = False
            elif event.char in "0123456789" and event.char:
                prefix = "" if self.fresh_entry or cell["number"] is None else str(cell["number"])
                cell["number"] = int(prefix + event.char)
                self.fresh_entry = False
        self.commit(previous)
        return "break"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?", type=grid_name,
                        help="Puzzle name; omit to open the name-and-size prompt")
    parser.add_argument("--state", type=Path,
                        help="JSON file to load and automatically save")
    args = parser.parse_args()
    if args.name and args.state:
        parser.error("Use a puzzle name or --state, rather than both.")
    root = tk.Tk()
    root.withdraw()
    try:
        if args.state:
            path = args.state.resolve()
            if path.exists():
                read_state(path)
            choice = (path.stem, path)
        elif args.name:
            size = None
            if not (DATA_DIRECTORY / f"{args.name}.json").exists():
                value = simpledialog.askstring("New puzzle", f"Grid size for '{args.name}' (10 or 8x12):",
                                               parent=root, initialvalue="10")
                if value is None:
                    root.destroy()
                    return
                size = parse_grid_size(value)
            choice = (args.name, prepare_grid(args.name, size))
        else:
            choice = choose_grid(root)
        if choice is None:
            root.destroy()
            return
        name, path = choice
        PuzzleEditor(root, path, name=name)
        root.deiconify()
        root.mainloop()
    except (ValueError, OSError) as exc:
        messagebox.showerror("Could not open puzzle", str(exc), parent=root)
        root.destroy()


if __name__ == "__main__":
    main()
