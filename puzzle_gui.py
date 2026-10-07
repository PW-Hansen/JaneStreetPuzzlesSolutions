"""A persistent Jane Street arc puzzle editor with clue-local region analysis."""

import argparse
import copy
import colorsys
import json
import math
import os
import re
import threading
from queue import Empty, Queue
from dataclasses import dataclass, field
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from PIL import Image, ImageDraw, ImageTk


DEFAULT_STATE = Path(__file__).with_name("puzzle_state.json")
DATA_DIRECTORY = Path(__file__).resolve().parent / "grids"
ARC_CYCLE = (None, "tl", "tr", "br", "bl")


def allowed_arc_configurations(state, row, column):
    """Intersect the persistent master domain with explicit puzzle markings."""
    cell = state["cells"][row][column]
    domains = state.get("arc_domains")
    allowed = domains[row][column] if domains is not None else ARC_CYCLE
    if cell["green"]:
        return (None,) if None in allowed else ()
    if cell["arc"] is not None:
        return (cell["arc"],) if cell["arc"] in allowed else ()
    return tuple(orientation for orientation in ARC_CYCLE if orientation in allowed)


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
    fragments_by_region = {region: set() for region in adjacency}
    invalid_by_region = {region: set() for region in adjacency}
    for fragment, region in regions.items():
        fragments_by_region[region].add(fragment)
    for r, c in invalid_arcs:
        invalid_by_region[regions[(r, c, 0)]].add((r, c))
    objects = {region: Region.from_fragments(region, fragments, state,
                                            invalid_by_region[region])
               for region, fragments in fragments_by_region.items()}
    return {fragment: objects[region] for fragment, region in regions.items()}, colors, invalid_arcs


@dataclass(frozen=True)
class Region:
    """A connected region that computes and stores its exact area value."""

    id: int
    fragments: frozenset[tuple[int, int, int]]
    whole_cells: int = 0
    arc_insides: int = 0
    arc_outsides: int = 0
    invalid_arcs: frozenset[tuple[int, int]] = frozenset()
    area: int | str = field(init=False)
    smooth_pieces: int | None = field(init=False, default=None, compare=False)
    score: int | None = field(init=False, default=None, compare=False)

    def __post_init__(self):
        object.__setattr__(self, "area", self.determine_area())

    @property
    def is_valid(self):
        return self.determine_validity()

    def has_valid_arc_separation(self):
        """Check only that the region does not contain both sides of an arc."""
        return not self.invalid_arcs and not any(
            side == 0 and (r, c, 1) in self.fragments
            for r, c, side in self.fragments)

    def invalidity_reasons(self):
        """Return reasons this region fails arc-separation or area rules."""
        reasons = []
        if not self.has_valid_arc_separation():
            reasons.append("The region contains both sides of an arc.")
        if not self.is_integer:
            reasons.append("The region has non-integer area: arc inside and outside counts differ.")
        return tuple(reasons)

    def determine_validity(self):
        """Check region geometry and exact area; clue scores are not checked."""
        return not self.invalidity_reasons()

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
        return self.area if self.is_integer else None

    def determine_area(self):
        """Return an integer or an exact symbolic string, never a float."""
        if self.is_integer:
            return self.constant
        coefficient = abs(self.pi_quarters)
        term = "π/4" if coefficient == 1 else f"{coefficient}π/4"
        if self.constant == 0:
            return term if self.pi_quarters > 0 else f"−{term}"
        sign = "+" if self.pi_quarters > 0 else "−"
        return f"{self.constant} {sign} {term}"

    def determine_smooth_pieces(self, state):
        """Count smooth connected pieces of this region's entire perimeter."""
        boundary = []
        for r, c, side in sorted(self.fragments):
            cell = state["cells"][r][c]
            arc = cell["arc"]
            if arc and (r, c, 1 - side) not in self.fragments:
                boundary.append(arc_endpoints(r, c, arc))
            inside_edges = {"tl": "NW", "tr": "NE", "br": "SE", "bl": "SW"}
            for edge, on_border, endpoints in (
                ("N", r == 0, (((r, c), (1, 0)), ((r, c + 1), (-1, 0)))),
                ("S", r == state["rows"] - 1,
                 (((r + 1, c), (1, 0)), ((r + 1, c + 1), (-1, 0)))),
                ("W", c == 0, (((r, c), (0, 1)), ((r + 1, c), (0, -1)))),
                ("E", c == state["columns"] - 1,
                 (((r, c + 1), (0, 1)), ((r + 1, c + 1), (0, -1)))),
            ):
                owner = 0 if arc is None or edge in inside_edges[arc] else 1
                if on_border and side == owner:
                    boundary.append(endpoints)
        parent = list(range(len(boundary)))

        def find(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        corners = {}
        for index, endpoints in enumerate(boundary):
            for corner, tangent in endpoints:
                corners.setdefault(corner, []).append((index, tangent))
        for entries in corners.values():
            for i, (first, tangent) in enumerate(entries):
                for second, other in entries[i + 1:]:
                    if tangent == (-other[0], -other[1]):
                        parent[find(second)] = find(first)
        pieces = len({find(index) for index in range(len(boundary))})
        object.__setattr__(self, "smooth_pieces", pieces)
        return pieces

    def determine_score(self, state):
        """Store area times smooth perimeter pieces; invalid regions have no score."""
        pieces = self.determine_smooth_pieces(state)
        score = self.area * pieces if self.determine_validity() else None
        object.__setattr__(self, "score", score)
        return score

    @classmethod
    def from_fragments(cls, region_id, fragments, state, invalid_arcs=()):
        fragments = frozenset(fragments)
        whole_cells = arc_insides = arc_outsides = 0
        for r, c, side in fragments:
            if state["cells"][r][c]["arc"] is None:
                whole_cells += 1
            elif side == 0:
                arc_insides += 1
            else:
                arc_outsides += 1
        return cls(region_id, fragments, whole_cells, arc_insides, arc_outsides,
                   frozenset(invalid_arcs))


def determine_region_areas(state, regions=None):
    """Convenience view of the exact areas already stored on Region objects."""
    if regions is None:
        regions = determine_regions(state)[0]
    return {region.id: region.area for region in regions.values()}


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
                              fill=(region_colors or {}).get((r, c, 1 if cell["arc"] else 0),
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
                painter.polygon(polygon, fill=region_colors.get((r, c, 0), "white"))
            if region_colors is not None and (r, c, 0) in region_colors and cell["green"]:
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
    domains = state.get("arc_domains")
    if domains is not None:
        if (not isinstance(domains, list) or len(domains) != rows
                or any(not isinstance(row, list) or len(row) != columns for row in domains)):
            raise ValueError("Arc master list does not match the grid dimensions.")
        for r, row in enumerate(domains):
            for c, domain in enumerate(row):
                if (not isinstance(domain, list) or not domain
                        or any(orientation not in ARC_CYCLE for orientation in domain)
                        or len(set(domain)) != len(domain)):
                    raise ValueError("Invalid arc master-list entry.")
                if not allowed_arc_configurations(state, r, c):
                    raise ValueError("Arc master list contradicts the cell markings.")
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
        self.analysis_cancel = None
        self.analysis_result = None
        self.selected = None
        self.fresh_entry = True
        self.mode = tk.StringVar(value="arc")
        self.status = tk.StringVar()
        root.title(f"Jane Street — Arc Puzzle Editor — {name or path.stem}")
        root.geometry("850x850")
        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        for label, value in [("Select (Ctrl+0)", "select"), ("Green cells (Ctrl+1)", "green"), ("Digits (Ctrl+2)", "digit"), ("Arcs (Ctrl+3)", "arc")]:
            ttk.Radiobutton(toolbar, text=label, value=value, variable=self.mode,
                            command=self.mode_changed).pack(side="left", padx=5)
        self.undo_button = ttk.Button(toolbar, text="Undo", command=self.undo)
        self.undo_button.pack(side="left", padx=(20, 4))
        self.redo_button = ttk.Button(toolbar, text="Redo", command=self.redo)
        self.redo_button.pack(side="left", padx=4)
        ttk.Button(toolbar, text="Save", command=self.save).pack(side="right")
        ttk.Button(toolbar, text="Reset arcs", command=self.reset_arcs).pack(side="right", padx=4)
        dimensions = ttk.Frame(root, padding=(8, 0, 8, 8))
        dimensions.pack(fill="x")
        ttk.Label(dimensions, text=f"{self.state['rows']}x{self.state['columns']} grid").pack(side="left", padx=(4, 12))
        ttk.Button(dimensions, text="Check smooth arcs", command=self.check_smooth_arcs).pack(side="left", padx=4)
        ttk.Button(dimensions, text="Determine regions", command=self.check_regions).pack(side="left", padx=4)
        ttk.Button(dimensions, text="Compute region areas", command=self.compute_region_areas).pack(side="left", padx=4)
        ttk.Button(dimensions, text="Compute scores", command=self.compute_region_scores).pack(side="left", padx=4)
        ttk.Button(dimensions, text="Clear colors", command=self.clear_arc_colors).pack(side="left", padx=4)
        analysis_controls = ttk.Frame(root, padding=(8, 0, 8, 8))
        analysis_controls.pack(fill="x")
        ttk.Button(analysis_controls, text="Abort analysis",
                   command=self.abort_clue_analysis).pack(side="left", padx=4)
        self.analysis_button = ttk.Button(analysis_controls, text="Analyze selected clue",
                                          command=self.analyze_selected_clue)
        self.analysis_button.pack(side="left", padx=4)
        self.domain_text = tk.StringVar(value="Select a cell to view allowed arc configurations.")
        ttk.Label(analysis_controls, textvariable=self.domain_text).pack(side="left", padx=8)
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
        for number, mode in enumerate(("select", "green", "digit", "arc")):
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
        if mode != "select" and self.mode.get() == mode:
            mode = "select"
        self.mode.set(mode)
        self.mode_changed()
        return "break"

    def clear_selection(self, event=None):
        self.selected = None
        self.fresh_entry = True
        self.draw()
        return "break"

    def commit(self, previous, preserve_domains=False):
        if previous == self.state:
            return
        if not preserve_domains:
            # Deductions depend on clues, green cells, and manually fixed arcs.
            self.state.pop("arc_domains", None)
        self.cancel_clue_analysis()
        self.analysis_result = None
        self.undo_stack.append(previous)
        self.redo_stack.clear()
        self.smooth_colors = None
        self.region_colors = None
        self.area_labels = None
        self.draw()
        self.save()

    def reset_arcs(self):
        previous = copy.deepcopy(self.state)
        self.state.pop("arc_domains", None)
        for row in self.state["cells"]:
            for cell in row:
                cell["arc"] = None
        self.commit(previous)

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
        self.cancel_clue_analysis()
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
        self.cancel_clue_analysis()
        self.analysis_result = None
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

    def cancel_clue_analysis(self):
        event = getattr(self, "analysis_cancel", None)
        if event is not None:
            event.set()
            self.analysis_cancel = None
            self.analysis_button.configure(text="Analyze selected clue")

    def abort_clue_analysis(self):
        if self.analysis_cancel is not None:
            self.cancel_clue_analysis()
            self.status.set("Clue analysis aborted. No deductions applied.")

    def analyze_selected_clue(self):
        if self.analysis_cancel is not None:
            self.cancel_clue_analysis()
            self.status.set("Clue analysis cancelled.")
            return
        if self.selected is None:
            self.status.set("Select a clue cell first, then click Analyze selected clue.")
            return
        r, c = self.selected
        clue = self.state["cells"][r][c]["number"]
        if clue is None:
            self.status.set("The selected cell has no clue. Select a numbered cell.")
            return
        from clue_analysis import analyze_clue
        snapshot, selected = copy.deepcopy(self.state), self.selected
        event = self.analysis_cancel = threading.Event()
        self.analysis_result = None
        messages = Queue()
        self.analysis_button.configure(text="Cancel analysis")
        self.status.set(f"Analyzing clue {clue} at ({r + 1}, {c + 1})…")

        def worker():
            try:
                result = analyze_clue(snapshot, selected, stop_event=event,
                                      progress=lambda visited, accepted: messages.put(("progress", (visited, accepted))))
                messages.put(("done", result))
            except Exception as exc:
                messages.put(("error", str(exc)))

        def poll():
            if self.analysis_cancel is not event:
                return
            try:
                while True:
                    kind, value = messages.get_nowait()
                    if kind == "progress":
                        visited, accepted = value
                        self.status.set(f"Clue {clue}: {accepted} accepted states; {visited} branches checked…")
                    else:
                        self.analysis_cancel = None
                        self.analysis_button.configure(text="Analyze selected clue")
                        if kind == "error":
                            self.status.set(f"Clue analysis failed: {value}")
                        else:
                            suffix = " Stopped early: more than 25 accepted states." if value.limit_reached else " Search complete."
                            from clue_analysis import incorporate_analysis
                            previous = copy.deepcopy(self.state)
                            changes = incorporate_analysis(self.state, value)
                            self.commit(previous, preserve_domains=True)
                            self.analysis_result = value
                            if changes["removed"]:
                                suffix += f" Removed {changes['removed']} configurations from the master list."
                            if changes["applied"]:
                                suffix += " Applied the unique accepted state."
                            if not value.accepted_states and not value.limit_reached and not value.cancelled:
                                suffix += " No configuration satisfies this clue under the current constraints."
                            self.status.set(f"Clue {clue}: {len(value.accepted_states)} accepted states; "
                                            f"{value.explored} branches checked.{suffix}")
                        return
            except Empty:
                self.root.after(100, poll)

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(100, poll)

    def check_regions(self):
        regions, self.region_colors, invalid_arcs = determine_regions(self.state)
        self.region_colors = {fragment: color for fragment, color in self.region_colors.items()
                              if regions[fragment].has_valid_arc_separation()}
        self.area_labels = None
        unique_regions = set(regions.values())
        self.draw()
        count = len(unique_regions)
        if invalid_arcs:
            cells = ", ".join(f"({r + 1}, {c + 1})" for r, c in invalid_arcs)
            self.status.set(f"{count} regions — INVALID: both sides of an arc reconnect in cells (row, column): {cells}.")
        else:
            self.status.set(f"{count} regions — every arc separates distinct regions. "
                            f"{sum(region.determine_validity() for region in unique_regions)}/{count} regions are valid (integer area).")

    def compute_region_areas(self):
        regions, self.region_colors, invalid_arcs = determine_regions(self.state)
        self.region_colors = {fragment: color for fragment, color in self.region_colors.items()
                              if regions[fragment].has_valid_arc_separation()}
        unique_regions = set(regions.values())
        self.area_labels = [(position, str(region.area))
                            for region, position in region_area_positions(self.state, regions).items()
                            if region.has_valid_arc_separation()]
        self.draw()
        self.status.set(f"Areas computed for {len(unique_regions)} regions; "
                        f"{sum(region.is_integer for region in unique_regions)} have integer area. "
                        f"{len(invalid_arcs)} arcs have both sides in one region. Blue labels show areas.")

    def clear_arc_colors(self):
        self.smooth_colors = None
        self.region_colors = None
        self.area_labels = None
        self.draw()
        self.status.set("Analysis colors cleared.")

    def compute_region_scores(self):
        regions, self.region_colors, _ = determine_regions(self.state)
        unique_regions = set(regions.values())
        for region in unique_regions:
            region.determine_score(self.state)
        self.area_labels = [(position, f"S: {region.score}" if region.score is not None else "Invalid")
                            for region, position in region_area_positions(self.state, regions).items()]
        self.draw()
        self.status.set(f"Scores computed for {sum(region.score is not None for region in unique_regions)}"
                        f"/{len(unique_regions)} regions. Score = area × smooth perimeter pieces.")

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
        if hasattr(self, "domain_text"):
            if self.selected is None:
                self.domain_text.set("Select a cell to view allowed arc configurations.")
            else:
                r, c = self.selected
                names = {None: "no arc", "tl": "top-left", "tr": "top-right",
                         "br": "bottom-right", "bl": "bottom-left"}
                allowed = allowed_arc_configurations(self.state, r, c)
                self.domain_text.set(f"({r + 1}, {c + 1}) allowed: " + ", ".join(names[o] for o in allowed))

    def click(self, event, erase=False):
        mode = self.mode.get()
        if mode == "select" and erase:
            return
        self.canvas.focus_set()
        x, y = self.canvas.canvasx(event.x) - 16, self.canvas.canvasy(event.y) - 16
        r, c = int(y // self.size), int(x // self.size)
        if not (0 <= r < self.state["rows"] and 0 <= c < self.state["columns"]):
            return
        self.selected = (r, c)
        self.fresh_entry = True
        previous = copy.deepcopy(self.state)
        cell = self.state["cells"][r][c]
        if mode == "green":
            cell["green"] = False if erase else not cell["green"]
            if cell["green"]:
                cell["arc"] = None
        elif mode == "digit":
            if erase:
                cell["number"] = None
        elif mode == "arc" and erase:
            cell["arc"] = None
        elif mode == "arc" and not cell["green"]:
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
        if self.mode.get() == "select":
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
