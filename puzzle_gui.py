"""A persistent Jane Street arc puzzle editor with clue-local region analysis."""

import argparse
import copy
import colorsys
import json
import math
import os
import re
import threading
from time import perf_counter
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


def clue_factorizations(state, selected):
    """Ordered area/perimeter factor pairs within conservative grid bounds.

    These are arithmetic candidates, not a claim that each pair is realizable.
    No factoring loop depends on the magnitude of the clue (only grid area).
    """
    r, c = selected
    clue = state["cells"][r][c]["number"]
    if clue is None or clue <= 0:
        return []
    max_area = state["rows"] * state["columns"]
    possible_arcs = sum(any(arc is not None for arc in allowed_arc_configurations(state, r, c))
                        for r in range(state["rows"]) for c in range(state["columns"]))
    max_pieces = possible_arcs + 2 * state["rows"] + 2 * state["columns"]
    return [(area, clue // area) for area in range(1, min(clue, max_area) + 1)
            if clue % area == 0 and clue // area <= max_pieces]


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

    def verify(self, state):
        """Verify separation, integer area, and every clue belonging to this region."""
        score = self.determine_score(state)
        if score is None:
            return False
        return all(state['cells'][r][c]['number'] in (None, score)
                   for r, c, side in self.fragments if side == 0)

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


def render_grid(state, cell_size, arc_colors=None, region_colors=None, map_mode=False, active_clue=None):
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
    for r, row in enumerate(state['cells']):
        for c, cell in enumerate(row):
            saved = state.get('saved_analyses', {}).get(f'{r},{c}')
            if cell['number'] is None or saved is None or len(saved['states']) <= 1:
                continue
            cx = margin + (c + .5) * cell_size
            cy = margin + (r + (.16 if map_mode else .5)) * cell_size
            radius = cell_size * (.15 if map_mode else .23)
            painter.ellipse(box(cx - radius, cy - radius, cx + radius, cy + radius),
                            outline='#1769aa', width=2 * scale)
    if active_clue is not None:
        r, c = active_clue
        cx, cy = margin + (c + .5) * cell_size, margin + (r + .5) * cell_size
        radius = cell_size * .42
        painter.ellipse(box(cx - radius, cy - radius, cx + radius, cy + radius),
                        outline='#ef8c00', width=2 * scale)
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


def ordered_clues(state):
    from fractions import Fraction
    # Equivalent trigger orientations are one grouped conditional, matching
    # the display and propagation rather than inflating their importance.
    conditionals = {(tuple(rule['if'][:2]), tuple(rule['then'][:2]), frozenset(rule['then'][2]))
                    for rule in state.get('arc_implications', [])}
    ranked = []
    for r, row in enumerate(state['cells']):
        for c, cell in enumerate(row):
            if cell['number'] is None:
                continue
            nearby = {(r, c), (r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)}
            count = sum(source in nearby or target in nearby for source, target, _ in conditionals)
            score = Fraction(cell['number']) * Fraction(4, 5) ** count
            ranked.append((score, r, c))
    return [(r, c) for _, r, c in sorted(ranked)]


def save_accepted_states(state, selected, result):
    if (result.cancelled or result.limit_reached or result.worklist_limit_reached
            or len(result.accepted_states) >= 25):
        return False
    r, c = selected
    state.setdefault('saved_analyses', {})[f'{r},{c}'] = {
        'clue': state['cells'][r][c]['number'],
        'states': [[list(placement) for placement in accepted] for accepted in result.accepted_states]}
    return True


def prune_saved_states(state):
    """Discard local previews conflicting with actual drawn arcs, not omissions."""
    removed = 0
    saved = state.get('saved_analyses', {})
    for key, entry in list(saved.items()):
        surviving = [accepted for accepted in entry['states']
                     if all(state['cells'][r][c]['arc'] is None
                            or state['cells'][r][c]['arc'] == arc for r, c, arc in accepted)]
        removed += len(entry['states']) - len(surviving)
        if surviving:
            entry['states'] = surviving
        else:
            del saved[key]
    return removed


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
    rules = state.get('arc_implications', [])
    if not isinstance(rules, list):
        raise ValueError('Conditional arc deductions must be a list.')
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {'if', 'then'}:
            raise ValueError('Invalid conditional arc deduction.')
        source, target = rule['if'], rule['then']
        if (not isinstance(source, list) or not isinstance(target, list) or len(source) != 3 or len(target) != 3
            or any(not isinstance(v, int) or isinstance(v, bool) for v in source[:2] + target[:2])
            or not (0 <= source[0] < rows and 0 <= source[1] < columns
                    and 0 <= target[0] < rows and 0 <= target[1] < columns)
            or source[2] not in ARC_CYCLE or not isinstance(target[2], list) or not target[2]
            or any(arc not in ARC_CYCLE for arc in target[2])):
            raise ValueError('Invalid conditional arc deduction.')
    if rules:
        from arc_constraints import propagate_arc_domains
        if propagate_arc_domains(state) is None:
            raise ValueError('Conditional deductions contradict the current markings or master list.')
    saved = state.get('saved_analyses', {})
    if not isinstance(saved, dict):
        raise ValueError('Saved clue analyses must be a mapping.')
    for key, entry in saved.items():
        try:
            r, c = map(int, key.split(','))
            if not (0 <= r < rows and 0 <= c < columns):
                raise ValueError()
            if entry['clue'] != cells[r][c]['number'] or entry['clue'] is None:
                raise ValueError()
            accepted = entry['states']
            if not isinstance(accepted, list) or len(accepted) >= 25:
                raise ValueError()
            for placements in accepted:
                if not isinstance(placements, list):
                    raise ValueError()
                seen = set()
                for nr, nc, arc in placements:
                    if (type(nr) is not int or type(nc) is not int or
                            not (0 <= nr < rows and 0 <= nc < columns) or arc not in ARC_CYCLE
                            or (nr, nc) in seen or cells[nr][nc]['green'] and arc is not None):
                        raise ValueError()
                    seen.add((nr, nc))
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ValueError('Invalid saved clue analysis.') from None
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
        self.analysis_started_at = None
        self.analysis_elapsed_seconds = None
        self.preview_index = 0
        self.selected = None
        self.fresh_entry = True
        self.mode = tk.StringVar(value="select")
        self.status = tk.StringVar()
        root.title(f"Jane Street — Arc Puzzle Editor — {name or path.stem}")
        root.geometry("1110x850")
        toolbar = ttk.Frame(root, padding=8)
        toolbar.pack(fill="x")
        for label, value in [("Select (Ctrl+0)", "select"), ("Green cells (Ctrl+1)", "green"), ("Digits (Ctrl+2)", "digit"), ("Arcs (Ctrl+3)", "arc"), ("Map (Ctrl+4)", "map")]:
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
        ttk.Button(dimensions, text="Verify regions", command=self.verify_regions).pack(side="left", padx=4)
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
        ttk.Button(analysis_controls, text="Factorization", command=self.show_factorizations).pack(side="left", padx=4)
        local_controls = ttk.Frame(root, padding=(8, 0, 8, 6))
        local_controls.pack(fill='x')
        ttk.Button(local_controls, text='Scan local conditionals (3 cells)',
                   command=self.scan_local_conditionals).pack(side='left', padx=4)
        ttk.Button(local_controls, text='Wipe local conditionals',
                   command=self.wipe_local_conditionals).pack(side='left', padx=4)
        self.analyze_all_button = ttk.Button(local_controls, text='Analyze all clues',
                                             command=self.analyze_all_clues)
        self.analyze_all_button.pack(side='left', padx=4)
        options = self.state.get("analysis_options", {})
        self.simplify_arcs = tk.BooleanVar(value=options.get("simplify_arcs", True))
        self.prioritize_cells = tk.BooleanVar(value=options.get("prioritize_cells", True))
        self.check_other_clues = tk.BooleanVar(value=options.get("check_other_clues", True))
        ttk.Checkbutton(analysis_controls, text="Simplify arcs", variable=self.simplify_arcs,
                        command=self.save).pack(side="left", padx=8)
        ttk.Checkbutton(analysis_controls, text="Prioritize cells", variable=self.prioritize_cells,
                        command=self.save).pack(side="left", padx=8)
        ttk.Checkbutton(analysis_controls, text="Check other clues", variable=self.check_other_clues,
                        command=self.save).pack(side="left", padx=8)
        analysis_details = ttk.Frame(root, padding=(8, 0, 8, 8))
        analysis_details.pack(fill="x")
        self.domain_text = tk.StringVar(value="Select a cell to view allowed arc configurations.")
        self.implication_text = tk.StringVar()
        ttk.Label(analysis_details, textvariable=self.domain_text).pack(side="left", padx=8)
        self.search_time_text = tk.StringVar(value="Search time: —")
        ttk.Label(analysis_details, textvariable=self.search_time_text).pack(side="right", padx=12)
        self.batch_time_text = tk.StringVar(value='Total analysis time: —')
        ttk.Label(analysis_details, textvariable=self.batch_time_text).pack(side='right', padx=8)
        preview_controls = ttk.Frame(root, padding=(8, 0, 8, 8))
        self.preview_controls = preview_controls
        self.map_controls = ttk.Frame(root, padding=(8, 0, 8, 8))
        ttk.Label(self.map_controls, text="Allowed in selected cell:").pack(side="left", padx=4)
        self.map_options = {}
        for orientation, label in zip(ARC_CYCLE, ('No arc', 'Top-left', 'Top-right', 'Bottom-right', 'Bottom-left')):
            variable = tk.BooleanVar()
            button = ttk.Checkbutton(self.map_controls, text=label, variable=variable,
                                      command=lambda arc=orientation: self.toggle_domain(arc))
            button.pack(side="left", padx=4)
            self.map_options[orientation] = (variable, button)
        preview_controls.pack(fill="x")
        ttk.Label(preview_controls, text="Accepted state:").pack(side="left", padx=4)
        self.previous_state_button = ttk.Button(preview_controls, text="Previous",
                                               command=lambda: self.set_preview(self.preview_index - 1))
        self.previous_state_button.pack(side="left", padx=4)
        self.preview_choice = ttk.Combobox(preview_controls, state="readonly", width=28)
        self.preview_choice.pack(side="left", padx=4)
        self.preview_choice.bind("<<ComboboxSelected>>",
                                 lambda event: self.set_preview(self.preview_choice.current()))
        self.next_state_button = ttk.Button(preview_controls, text="Next",
                                           command=lambda: self.set_preview(self.preview_index + 1))
        self.next_state_button.pack(side="left", padx=4)
        ttk.Label(preview_controls, text="Blue arcs are speculative; State 0 shows confirmed arcs.").pack(side="left", padx=8)
        self.factorization_text = tk.StringVar()
        self.factorization_selection = None
        ttk.Label(root, textvariable=self.factorization_text, wraplength=800,
                  padding=(12, 0, 12, 4)).pack(fill="x")
        ttk.Label(root, text="Green: click to toggle • Digits: select a cell and type • "
                  "Arcs: click to cycle through four curves, then no arc\n"
                  "Backspace edits a clue • Delete clears the current mode’s mark • "
                  "Right-click removes a mark • Ctrl+Z / Ctrl+Y undo / redo",
                  padding=(12, 0, 12, 8)).pack(fill="x")
        body = ttk.Frame(root)
        body.pack(fill="both", expand=True)
        conditional_panel = ttk.Frame(body, width=260, padding=12)
        conditional_panel.pack(side="right", fill="y")
        conditional_panel.pack_propagate(False)
        ttk.Label(conditional_panel, text="Local conditionals").pack(anchor="w", pady=(0, 8))
        conditional_view = tk.Text(conditional_panel, wrap="word", width=28,
                                   state="disabled", relief="flat", background="#e9edf1")
        conditional_scroll = ttk.Scrollbar(conditional_panel, command=conditional_view.yview)
        conditional_scroll.pack(side="right", fill="y")
        conditional_view.configure(yscrollcommand=conditional_scroll.set)
        conditional_view.pack(fill="both", expand=True)
        def update_conditionals(*args):
            conditional_view.configure(state="normal")
            conditional_view.delete("1.0", "end")
            conditional_view.insert("1.0", self.implication_text.get())
            conditional_view.configure(state="disabled")
            conditional_view.yview_moveto(0)
        self.implication_text.trace_add("write", update_conditionals)
        frame = ttk.Frame(body)
        frame.pack(side="left", fill="both", expand=True)
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
        for number, mode in enumerate(("select", "green", "digit", "arc", "map")):
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
        self.draw()

    def toggle_domain(self, orientation):
        if self.selected is None:
            return
        r, c = self.selected
        cell = self.state['cells'][r][c]
        if cell['green'] or cell['arc'] is not None:
            self.status.set('Green cells and drawn arcs are fixed. Clear the marking before editing possibilities.')
            self.draw()
            return
        previous = copy.deepcopy(self.state)
        domains = self.state.setdefault('arc_domains',
            [[list(ARC_CYCLE) for _ in range(self.state['columns'])] for _ in range(self.state['rows'])])
        allowed = domains[r][c]
        if orientation in allowed:
            if len(allowed) == 1:
                self.state = previous
                self.status.set('Keep at least one possible configuration in each cell.')
                self.draw()
                return
            allowed.remove(orientation)
        else:
            allowed.append(orientation)
        domains[r][c] = [arc for arc in ARC_CYCLE if arc in allowed]
        from arc_constraints import propagate_arc_domains
        if propagate_arc_domains(self.state) is None:
            self.state = previous
            self.status.set('This edit conflicts with a recorded conditional deduction.')
            self.draw()
            return
        self.commit(previous, preserve_domains=True)

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
        if preserve_domains and self.state.get('arc_implications'):
            from arc_constraints import apply_arc_deductions
            try:
                apply_arc_deductions(self.state)
            except ValueError as exc:
                self.state = previous
                self.status.set(str(exc))
                self.draw()
                return
        if not preserve_domains:
            # Clue/green edits change the puzzle; arc placements retain deductions.
            self.state.pop("arc_domains", None)
            self.state.pop('arc_implications', None)
            self.state.pop('saved_analyses', None)
        else:
            prune_saved_states(self.state)
        self.cancel_clue_analysis()
        self.analysis_result = None
        self.preview_index = 0
        if getattr(self, 'selected', None) is not None:
            self.load_saved_clue(self.selected)
        self.undo_stack.append(previous)
        self.redo_stack.clear()
        self.smooth_colors = None
        self.region_colors = None
        self.area_labels = None
        self.draw()
        self.save()

    def wipe_local_conditionals(self):
        previous = copy.deepcopy(self.state)
        self.state.pop('arc_implications', None)
        self.commit(previous, preserve_domains=True)
        self.status.set('Local conditionals cleared. Arcs and excluded configurations preserved.')

    def reset_arcs(self):
        previous = copy.deepcopy(self.state)
        self.state.pop("arc_domains", None)
        self.state.pop('arc_implications', None)
        for row in self.state["cells"]:
            for cell in row:
                cell["arc"] = None
        self.commit(previous)

    def save(self):
        if hasattr(self, "simplify_arcs"):
            self.state["analysis_options"] = {"simplify_arcs": self.simplify_arcs.get(),
                                               "prioritize_cells": self.prioritize_cells.get(),
                                               "check_other_clues": self.check_other_clues.get()}
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
        self.preview_index = 0
        self.smooth_colors = None
        self.region_colors = None
        self.area_labels = None
        self.selected = None
        self.fresh_entry = True
        self.draw()
        self.save()

    def show_factorizations(self, update_status=True):
        if self.selected is None:
            self.status.set("Select a numbered clue cell first.")
            return
        r, c = self.selected
        clue = self.state["cells"][r][c]["number"]
        if clue is None:
            self.status.set("The selected cell has no clue.")
            return
        pairs = clue_factorizations(self.state, self.selected)
        self.factorization_selection = (self.selected, clue)
        expressions = "  •  ".join(f"{area} × {pieces}" for area, pieces in pairs)
        self.factorization_text.set(f"Clue {clue} — area × smooth perimeter pieces: " +
                                    (expressions or "No positive integer factor pairs within the grid bounds."))
        if update_status:
            self.status.set("Factorizations satisfy arithmetic and grid bounds; geometric feasibility still requires analysis.")

    def scan_local_conditionals(self):
        from local_conditionals import scan_local_conditionals
        self.cancel_clue_analysis()
        previous = copy.deepcopy(self.state)
        started = perf_counter()
        try:
            scanned, counts = scan_local_conditionals(previous, max_distance=3)
        except ValueError as exc:
            self.status.set(f'Local scan: {exc}')
            return False
        self.state = scanned
        self.commit(previous, preserve_domains=True)
        self.draw()
        self.status.set(f"Local scan: {counts['clues']} clues; {counts['pairs']} pairs checked; "
                        f"{counts['implications']} conditional deductions recorded; "
                        f"{counts['removed']} configurations removed in {perf_counter() - started:.2f} s; "
                        f"{counts['cutoffs']} checks inconclusive.")
        return True

    def check_smooth_arcs(self):
        self.preview_index = 0
        groups, self.smooth_colors, conflicts = smooth_arc_groups(self.state)
        self.draw()
        message = f"{len(set(groups.values()))} smooth arc pieces across {len(groups)} arcs."
        if conflicts:
            message += (f" {len(conflicts)} sharp self-joins: a smooth chain returns to itself; "
                        "its two ends cannot have different colors while keeping the chain one color.")
        self.status.set(message)

    def cancel_clue_analysis(self):
        if not getattr(self, '_batch_applying', False):
            self.stop_batch_analysis()
        event = getattr(self, "analysis_cancel", None)
        if event is not None:
            event.set()
            self.analysis_cancel = None
            started = getattr(self, "analysis_started_at", None)
            if started is not None:
                self.update_analysis_time(perf_counter() - started, "cancelled")
            self.analysis_started_at = None
            self.reset_analysis_buttons()
            if hasattr(self, 'canvas'):
                self.draw()

    def reset_analysis_buttons(self):
        self.analysis_button.configure(text="Analyze selected clue")

    def stop_batch_analysis(self):
        if getattr(self, 'batch_token', None) is not None and getattr(self, 'batch_started_at', None) is not None:
            self.update_batch_time(perf_counter() - self.batch_started_at)
            self.batch_started_at = None
        self.batch_token = None
        self.batch_clues = []
        if hasattr(self, 'analyze_all_button'):
            self.analyze_all_button.configure(text='Analyze all clues')

    def analyze_all_clues(self):
        if getattr(self, 'batch_token', None) is not None:
            self.abort_clue_analysis()
            return
        self.cancel_clue_analysis()
        started = perf_counter()
        self.update_batch_time(0.0)
        if not self.scan_local_conditionals():
            self.update_batch_time(perf_counter() - started)
            return
        self.batch_clues = ordered_clues(self.state)
        if not self.batch_clues:
            self.update_batch_time(perf_counter() - started)
            self.status.set('No clues to analyze.')
            return
        self.batch_token = object()
        self.batch_started_at = started
        self.batch_total = len(self.batch_clues)
        self.batch_completed = 0
        self.batch_pass = 1
        self.batch_pass_arcs = {(r, c, cell['arc']) for r, row in enumerate(self.state['cells'])
                                for c, cell in enumerate(row) if cell['arc'] is not None}
        if hasattr(self, 'analyze_all_button'):
            self.analyze_all_button.configure(text='Stop analyzing all clues')
        self.poll_batch_time(self.batch_token)
        self.next_batch_clue(self.batch_token)

    def update_batch_time(self, elapsed):
        self.batch_elapsed_seconds = elapsed
        if hasattr(self, 'batch_time_text'):
            self.batch_time_text.set(f'Total analysis time: {elapsed:.2f} s')

    def poll_batch_time(self, token):
        if getattr(self, 'batch_token', None) is not token:
            return
        self.update_batch_time(perf_counter() - self.batch_started_at)
        self.root.after(100, lambda: self.poll_batch_time(token))

    def next_batch_clue(self, token):
        if getattr(self, 'batch_token', None) is not token:
            return
        if not self.batch_clues:
            regions = set(determine_regions(self.state)[0].values())
            complete = all(region.verify(self.state) for region in regions)
            arcs = {(r, c, cell['arc']) for r, row in enumerate(self.state['cells'])
                    for c, cell in enumerate(row) if cell['arc'] is not None}
            if complete or not arcs - self.batch_pass_arcs:
                passes = self.batch_pass
                self.stop_batch_analysis()
                outcome = 'Puzzle verified complete.' if complete else 'No new arcs placed in the last pass.'
                self.status.set(f'Finished after {passes} passes. {outcome}')
                return
            self.batch_pass += 1
            self.batch_pass_arcs = arcs
            self.batch_clues = ordered_clues(self.state)
            self.batch_completed = 0
        remaining = set(self.batch_clues)
        self.batch_clues = [cell for cell in ordered_clues(self.state) if cell in remaining]
        self.selected = self.batch_clues.pop(0)
        self.load_saved_clue(self.selected)
        self.analyze_selected_clue()

    def batch_clue_finished(self):
        token = getattr(self, 'batch_token', None)
        if token is not None:
            self.batch_completed += 1
            self.root.after(0, lambda: self.next_batch_clue(token))

    def update_analysis_time(self, elapsed, outcome=""):
        self.analysis_elapsed_seconds = elapsed
        suffix = f" ({outcome})" if outcome else ""
        if hasattr(self, "search_time_text"):
            self.search_time_text.set(f"Search time: {elapsed:.2f} s{suffix}")

    def abort_clue_analysis(self):
        if self.analysis_cancel is not None or getattr(self, 'batch_token', None) is not None:
            self.cancel_clue_analysis()
            self.status.set(f"Clue analysis aborted after {self.analysis_elapsed_seconds or 0:.2f} s. Completed deductions preserved.")

    def analyze_selected_clue(self):
        if self.analysis_cancel is not None:
            self.cancel_clue_analysis()
            self.status.set(f"Clue analysis cancelled after {self.analysis_elapsed_seconds or 0:.2f} s.")
            return
        if self.selected is None:
            self.status.set("Select a clue cell first, then click Analyze selected clue.")
            return
        r, c = self.selected
        clue = self.state["cells"][r][c]["number"]
        if clue is None:
            self.status.set("The selected cell has no clue. Select a numbered cell.")
            return
        from incremental_analysis import analyze_clue_incremental as analyze_clue
        if hasattr(self, "factorization_text"):
            self.show_factorizations(update_status=False)
        snapshot, selected = copy.deepcopy(self.state), self.selected
        simplify_nonclue = self.simplify_arcs.get()
        prioritize_frontier = self.prioritize_cells.get()
        check_other_clues = self.check_other_clues.get()
        event = self.analysis_cancel = threading.Event()
        self.active_clue = selected
        self.analysis_started_at = perf_counter()
        self.update_analysis_time(0.0, "running")
        self.analysis_result = None
        self.preview_index = 0
        self.draw()
        messages = Queue()
        self.analysis_button.configure(text="Cancel analysis")
        engine_label = "Clue"
        progress_counts = [0, 0]
        self.status.set(f"Analyzing clue {clue} at ({r + 1}, {c + 1})…")
        if getattr(self, 'batch_token', None) is not None:
            self.status.set(f'Pass {self.batch_pass}: analyzing clue {self.batch_completed + 1}/{self.batch_total}: '
                            f'{clue} at ({r + 1}, {c + 1})…')

        def worker():
            started = perf_counter()
            print(f'Starting analysis of clue {clue} at r{selected[0] + 1}c{selected[1] + 1}', flush=True)
            try:
                result = analyze_clue(snapshot, selected, stop_event=event,
                                      simplify_nonclue=simplify_nonclue,
                                      prioritize_frontier=prioritize_frontier,
                                      check_other_clues=check_other_clues,
                                      progress=lambda visited, accepted: messages.put(("progress", (visited, accepted))))
                result.elapsed_seconds = perf_counter() - started
                outcome = ' (aborted)' if result.cancelled else ' (stopped early)' if result.limit_reached or result.worklist_limit_reached else ''
                print(f'Clue {clue} at r{selected[0] + 1}c{selected[1] + 1}: '
                      f'{result.elapsed_seconds:.2f} seconds{outcome}', flush=True)
                messages.put(("done", result))
            except Exception as exc:
                elapsed = perf_counter() - started
                print(f'Clue {clue} at r{selected[0] + 1}c{selected[1] + 1}: '
                      f'{elapsed:.2f} seconds (failed: {exc})', flush=True)
                messages.put(("error", (str(exc), elapsed)))

        def poll():
            if self.analysis_cancel is not event:
                return
            self.update_analysis_time(perf_counter() - self.analysis_started_at, "running")
            try:
                while True:
                    kind, value = messages.get_nowait()
                    if kind == "progress":
                        visited, accepted = value
                        progress_counts[:] = [visited, accepted]
                    else:
                        self.analysis_cancel = None
                        self.analysis_started_at = None
                        self.reset_analysis_buttons()
                        self.draw()
                        elapsed = value[1] if kind == "error" else value.elapsed_seconds
                        self.update_analysis_time(elapsed, "failed" if kind == "error" else "")
                        if kind == "error":
                            self.stop_batch_analysis()
                            self.status.set(f"Clue analysis failed after {elapsed:.2f} s: {value[0]}")
                        else:
                            suffix = " Stopped early: more than 25 accepted states." if value.limit_reached else " Search complete."
                            from clue_analysis import incorporate_analysis
                            previous = copy.deepcopy(self.state)
                            updated = copy.deepcopy(self.state)
                            try:
                                changes = incorporate_analysis(updated, value)
                                save_accepted_states(updated, selected, value)
                            except ValueError as exc:
                                self.stop_batch_analysis()
                                self.analysis_result = value
                                self.preview_index = 0
                                self.draw()
                                self.status.set(f'Clue {clue}: {len(value.accepted_states)} accepted states; '
                                                f'could not apply deductions: {exc}')
                                return
                            self.state = updated
                            self._batch_applying = True
                            try:
                                self.commit(previous, preserve_domains=True)
                            finally:
                                self._batch_applying = False
                            self.analysis_result = value
                            self.preview_index = 0
                            self.draw()
                            if changes["removed"]:
                                suffix += f" Removed {changes['removed']} configurations from the master list."
                            if changes.get('implications'):
                                suffix += f" Recorded {changes['implications']} conditional deductions."
                            if changes["applied"]:
                                suffix += " Applied the unique accepted state."
                            elif changes.get("forced"):
                                suffix += f" Applied {changes['forced']} forced cell configurations."
                            if value.factorization_pruned:
                                suffix += f" Factorization bounds rejected {value.factorization_pruned} branches."
                            if value.secondary_checks:
                                suffix += (f" Other-clue checks: {value.secondary_checks}; "
                                           f"{value.secondary_cache_hits} reused from cache; "
                                           f"rejected {value.secondary_pruned} branches; "
                                           f"{value.secondary_cutoffs} checks exceeded 25 pending worklist states.")
                            if not value.accepted_states and not value.limit_reached and not value.cancelled:
                                suffix += " No configuration satisfies this clue under the current constraints."
                            self.status.set(f"{engine_label} {clue}: {len(value.accepted_states)} accepted states; "
                                            f"{value.explored} branches checked in {elapsed:.2f} s.{suffix}")
                            self.batch_clue_finished()
                        return
            except Empty:
                visited, accepted = progress_counts
                self.status.set(f"{engine_label} {clue}: {accepted} accepted states; {visited} branches checked; "
                                f"{self.analysis_elapsed_seconds:.2f} s elapsed…")
                self.root.after(100, poll)

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(100, poll)

    def load_saved_clue(self, selected):
        self.preview_index = 0
        self.analysis_result = None
        entry = self.state.get('saved_analyses', {}).get(f'{selected[0]},{selected[1]}')
        if entry is None:
            return False
        from clue_analysis import ClueAnalysis
        self.analysis_result = ClueAnalysis(
            accepted_states=[tuple(tuple(placement) for placement in accepted) for accepted in entry['states']],
            source_clue=selected)
        return True

    def update_preview_controls(self):
        if not hasattr(self, "preview_choice"):
            return
        result = self.analysis_result
        count = len(result.accepted_states) if result is not None else 0
        self.preview_index = max(0, min(self.preview_index, count))
        self.preview_choice.configure(values=["State 0 — confirmed grid"] +
                                      [f"State {i} — preview" for i in range(1, count + 1)])
        self.preview_choice.current(self.preview_index)
        self.previous_state_button.configure(state="normal" if self.preview_index > 0 else "disabled")
        self.next_state_button.configure(state="normal" if self.preview_index < count else "disabled")

    def set_preview(self, index):
        result = self.analysis_result
        count = len(result.accepted_states) if result is not None else 0
        self.preview_index = max(0, min(index, count))
        self.draw()

    def preview_grid(self):
        """Build a display-only state; never mutate saved cells or domains."""
        result = self.analysis_result
        index = getattr(self, "preview_index", 0)
        if result is None or index == 0 or index > len(result.accepted_states):
            return self.state, {}
        display = copy.deepcopy(self.state)
        speculative = {}
        for r, c, orientation in result.accepted_states[index - 1]:
            if orientation != self.state["cells"][r][c]["arc"]:
                speculative[(r, c)] = "#1769aa"
            display["cells"][r][c]["arc"] = orientation
        return display, speculative

    def check_regions(self):
        self.preview_index = 0
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

    def verify_regions(self):
        self.preview_index = 0
        regions, _, _ = determine_regions(self.state)
        validity = {region: region.verify(self.state) for region in set(regions.values())}
        self.region_colors = {fragment: '#a8dfac' if validity[region] else '#c4c4c4'
                              for fragment, region in regions.items()}
        self.smooth_colors = None
        self.area_labels = None
        self.draw()
        self.status.set(f"Verified regions: {sum(validity.values())} valid (green); "
                        f"{sum(not valid for valid in validity.values())} invalid (grey).")

    def compute_region_areas(self):
        self.preview_index = 0
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
        self.preview_index = 0
        self.smooth_colors = None
        self.region_colors = None
        self.area_labels = None
        self.draw()
        self.status.set("Analysis colors cleared.")

    def compute_region_scores(self):
        self.preview_index = 0
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
        self.update_preview_controls()
        if hasattr(self, "factorization_text") and self.factorization_selection is not None:
            selected, clue = self.factorization_selection
            if self.selected != selected or self.state["cells"][selected[0]][selected[1]]["number"] != clue:
                self.factorization_text.set("")
                self.factorization_selection = None
            else:
                # Keep grid-bound candidates current after master-list changes.
                self.show_factorizations(update_status=False)
        self.canvas.delete("all")
        rows, columns = self.state["rows"], self.state["columns"]
        from arc_constraints import propagate_arc_domains
        effective_domains = propagate_arc_domains(self.state)
        self.size = max(36, min(80, (self.canvas.winfo_width() - 32) / columns,
                                (self.canvas.winfo_height() - 32) / rows))
        size, margin = self.size, 16
        self.canvas.configure(scrollregion=(0, 0, columns * size + 32, rows * size + 32))
        display, speculative = self.preview_grid()
        map_mode = self.mode.get() == 'map'
        if map_mode:
            display = {**self.state, 'cells': [[{**cell, 'arc': None} for cell in row]
                                               for row in self.state['cells']]}
        previewing = getattr(self, "preview_index", 0) > 0
        arc_colors = speculative if previewing else self.smooth_colors
        self.grid_image = ImageTk.PhotoImage(render_grid(display, size, arc_colors,
                                                        None if previewing or map_mode else self.region_colors,
                                                        map_mode=map_mode,
                                                        active_clue=(getattr(self, 'active_clue', None)
                                                                     if self.analysis_cancel is not None else None)),
                                               master=self.canvas)
        self.canvas.create_image(0, 0, image=self.grid_image, anchor="nw")
        for r, row in enumerate(self.state["cells"]):
            for c, cell in enumerate(row):
                x, y = margin + c * size, margin + r * size
                if cell["number"] is not None:
                    self.canvas.create_text(x + size / 2, y + size * (.16 if map_mode else .5),
                        text=str(cell["number"]), font=("Segoe UI", max(10, int(size * .24)), "bold"))
                if map_mode:
                    allowed = effective_domains[(r, c)] if effective_domains is not None else ()
                    for arc, dx, dy in ((None, .5, .5), ('tl', .78, .27), ('tr', .22, .27),
                                        ('br', .22, .76), ('bl', .78, .76)):
                        cx, cy, radius = x + dx * size, y + dy * size, size * .12
                        color = '#172b4d' if arc in allowed else '#c8c8c8'
                        if arc is None:
                            self.canvas.create_text(cx, cy, text='—', fill=color,
                                                    font=('Segoe UI', max(9, int(size * .2)), 'bold'))
                        else:
                            start = {'tl': 0, 'tr': 90, 'br': 180, 'bl': 270}[arc]
                            points = []
                            for step in range(13):
                                angle = math.radians(start + step * 7.5)
                                points.extend((cx + radius * math.cos(angle), cy - radius * math.sin(angle)))
                            self.canvas.create_line(*points, fill=color, width=2, smooth=True)
                        if arc not in allowed:
                            self.canvas.create_line(cx - radius, cy - radius, cx + radius, cy + radius,
                                                    fill='#c84646', width=1)
                if self.selected == (r, c):
                    self.canvas.create_rectangle(x + 3, y + 3, x + size - 3, y + size - 3,
                                                 outline="#e89520", width=3)
        for (r, c, x, y, width), area in ([] if previewing or map_mode else self.area_labels or []):
            self.canvas.create_text(margin + (c + x) * size, margin + (r + y) * size,
                                    text=area, fill="#174377",
                                    font=("Segoe UI", max(7, min(11, int(size * .14)))),
                                    width=max(16, int(width * size)), justify="center")
        self.undo_button.configure(state="normal" if self.undo_stack else "disabled")
        self.redo_button.configure(state="normal" if self.redo_stack else "disabled")
        if hasattr(self, 'map_controls'):
            if map_mode:
                self.map_controls.pack(fill='x', before=self.preview_controls)
            else:
                self.map_controls.pack_forget()
            allowed = effective_domains[self.selected] if self.selected and effective_domains is not None else ()
            for arc, (variable, button) in self.map_options.items():
                variable.set(arc in allowed)
                fixed = self.selected and (self.state['cells'][self.selected[0]][self.selected[1]]['green']
                                            or self.state['cells'][self.selected[0]][self.selected[1]]['arc'] is not None)
                button.configure(state='disabled' if self.selected is None or fixed else 'normal')
        if hasattr(self, "domain_text"):
            if self.selected is None:
                self.domain_text.set("Select a cell to view allowed arc configurations.")
            else:
                r, c = self.selected
                names = {None: "no arc", "tl": "top-left", "tr": "top-right",
                         "br": "bottom-right", "bl": "bottom-left"}
                allowed = effective_domains[(r, c)] if effective_domains is not None else ()
                self.domain_text.set(f"({r + 1}, {c + 1}) allowed: " + ", ".join(names[o] for o in allowed))
        if hasattr(self, 'implication_text'):
            from arc_constraints import describe_arc_implications
            self.implication_text.set(describe_arc_implications(self.state, self.selected))

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
        if not erase and self.state['cells'][r][c]['number'] is not None:
            if self.load_saved_clue(self.selected):
                self.draw()
                return
        if mode == 'map':
            if erase:
                dx, dy = (x % self.size) / self.size, (y % self.size) / self.size
                orientation = (None if .33 <= dx <= .67 and .33 <= dy <= .67 else
                               'tr' if dx < .5 and dy < .5 else 'tl' if dy < .5 else
                               'br' if dx < .5 else 'bl')
                self.toggle_domain(orientation)
            self.draw()
            return
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
            domains = self.state.get('arc_domains')
            allowed = domains[r][c] if domains is not None else ARC_CYCLE
            from arc_constraints import propagate_arc_domains
            effective = propagate_arc_domains(self.state)
            if effective is not None:
                # Test alternatives without the currently drawn arc pinning the
                # source cell; retained master domains and implications still apply.
                unmarked = {**self.state, 'cells': [list(row) for row in self.state['cells']]}
                unmarked['cells'][r][c] = {**cell, 'arc': None}
                effective = propagate_arc_domains(unmarked)
                if effective is not None:
                    allowed = effective[(r, c)]
            # None clears the drawn mark; it does not add no-arc to the domain.
            cycle = (None,) + tuple(arc for arc in ARC_CYCLE[1:] if arc in allowed)
            index = cycle.index(cell['arc']) if cell['arc'] in cycle else 0
            cell['arc'] = cycle[(index + 1) % len(cycle)]
        self.commit(previous, preserve_domains=mode == 'arc')
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
            if self.state['cells'][self.selected[0]][self.selected[1]]['number'] is not None:
                self.load_saved_clue(self.selected)
            self.draw()
            return "break"
        if self.mode.get() in ('select', 'map'):
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
        self.commit(previous, preserve_domains=self.mode.get() == 'arc')
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
