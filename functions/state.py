"""Validated state and editing/history operations, independent of Tkinter."""

from copy import deepcopy
import re

from functions.constants import MODES
from functions.regions import region_map, check_tower_regions, propagate_towers
from functions.path_candidates import recheck_paths, validate_paths


def valid_name(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Enter a name.")
    name = name.strip()
    if (len(name) > 100 or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
            or name.endswith((".", " ")) or name in (".", "..")
            or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", name)):
        raise ValueError("Use a valid file name without path separators.")
    return name


def new_grid(name, rows, columns):
    name = valid_name(name)
    if any(type(n) is not int or n <= 0 for n in (rows, columns)):
        raise ValueError("Rows and columns must be positive integers.")
    return {"name": name, "rows": rows, "columns": columns,
            "scores": [[None] * columns for _ in range(rows)],
            "visits": [[None] * columns for _ in range(rows)], "borders": [], "towers": [],
            "non_towers": [], "tower_marks": [], "non_tower_marks": []}


def edge_key(first, second):
    if abs(first[0] - second[0]) + abs(first[1] - second[1]) != 1:
        raise ValueError("Borders must join orthogonally adjacent cells.")
    return list(min(first, second)) + list(max(first, second))


def validate_grid(grid):
    if not isinstance(grid, dict):
        raise ValueError("Invalid grid data.")
    required = {"name", "rows", "columns", "scores", "visits", "borders"}
    if not required <= set(grid) or set(grid) - required - {"towers", "non_towers", "tower_marks", "non_tower_marks"}:
        raise ValueError("Grid fields are missing or unsupported.")
    new_grid(grid["name"], grid["rows"], grid["columns"])
    rows, columns = grid["rows"], grid["columns"]
    for field in ("scores", "visits"):
        values = grid[field]
        if not isinstance(values, list) or len(values) != rows:
            raise ValueError("Invalid cell rows.")
        for row in values:
            if not isinstance(row, list) or len(row) != columns:
                raise ValueError("Invalid cell columns.")
            if any(value is not None and type(value) is not int for value in row):
                raise ValueError("Cell values must be integers or empty.")
    if not isinstance(grid["borders"], list):
        raise ValueError("Invalid borders.")
    seen = set()
    for edge in grid["borders"]:
        if not isinstance(edge, list) or len(edge) != 4 or any(type(n) is not int for n in edge):
            raise ValueError("Invalid border coordinates.")
        first, second = tuple(edge[:2]), tuple(edge[2:])
        for row, column in (first, second):
            if not (0 <= row < rows and 0 <= column < columns):
                raise ValueError("Border outside the grid.")
        if edge != edge_key(first, second) or tuple(edge) in seen:
            raise ValueError("Duplicate or noncanonical border.")
        seen.add(tuple(edge))
    grid = deepcopy(grid)
    grid.setdefault("towers", [])  # Older working files and history had no tower field.
    if not isinstance(grid["towers"], list):
        raise ValueError("Invalid towers.")
    seen_towers = set()
    for cell in grid["towers"]:
        if (not isinstance(cell, list) or len(cell) != 2
                or any(type(n) is not int for n in cell)
                or not (0 <= cell[0] < rows and 0 <= cell[1] < columns)
                or tuple(cell) in seen_towers):
            raise ValueError("Invalid tower cell.")
        seen_towers.add(tuple(cell))
    check_tower_regions(grid)
    grid.setdefault("tower_marks", deepcopy(grid["towers"]))
    grid.setdefault("non_tower_marks", deepcopy(grid.get("non_towers", [])))
    for field in ("tower_marks", "non_tower_marks", "non_towers"):
        marks = grid.get(field, [])
        if not isinstance(marks, list):
            raise ValueError("Invalid tower markings.")
        marked = set()
        for cell in marks:
            if (not isinstance(cell, list) or len(cell) != 2
                    or any(type(n) is not int for n in cell)
                    or not (0 <= cell[0] < rows and 0 <= cell[1] < columns)
                    or tuple(cell) in marked):
                raise ValueError("Invalid tower marking cell.")
            marked.add(tuple(cell))
    propagate_towers(grid)
    return grid


class Session:
    def __init__(self, grid):
        self.grid = validate_grid(grid)
        self.undo_stack = []
        self.redo_stack = []
        self.selected = None
        self.mode = "Select"
        self._typing = None
        self.pending_paths = []
        self.path_notice = ""

    def _frame(self):
        return {"grid": deepcopy(self.grid), "selected": self.selected,
                "pending_paths": deepcopy(self.pending_paths)}

    def _change(self, operation):
        before = self._frame()
        operation()
        recheck_paths(self)
        if before["grid"] == self.grid and before["pending_paths"] == self.pending_paths:
            return False
        self.undo_stack.append(before)
        self.redo_stack.clear()
        return True

    def select(self, cell):
        if cell is not None:
            row, column = cell
            if not (0 <= row < self.grid["rows"] and 0 <= column < self.grid["columns"]):
                return
        self.selected = cell
        self._typing = None

    def move(self, dr, dc):
        row, column = self.selected if self.selected is not None else (0, 0)
        if self.selected is not None:
            row = max(0, min(self.grid["rows"] - 1, row + dr))
            column = max(0, min(self.grid["columns"] - 1, column + dc))
        self.select((row, column))

    def set_mode(self, mode):
        if mode not in MODES:
            raise ValueError("Unknown mode.")
        self.mode = "Select" if mode == self.mode else mode
        self._typing = None

    def set_value(self, value):
        if self.selected is None or self.mode not in ("Score", "Visit number"):
            return False
        if value is not None and type(value) is not int:
            raise ValueError("Enter an integer or leave the value empty.")
        row, column = self.selected
        field = "scores" if self.mode == "Score" else "visits"
        return self._change(lambda: self.grid[field][row].__setitem__(column, value))

    def input_text(self, text):
        if text and not re.fullmatch(r"[+-]?\d+", text, flags=re.ASCII):
            raise ValueError("Enter an integer or leave the value empty.")
        self._typing = None
        return self.set_value(int(text) if text else None)

    def type_key(self, key):
        if self.selected is None or self.mode not in ("Score", "Visit number"):
            return False
        if key == "Delete":
            self._typing = None
            return self.set_value(None)
        if key == "BackSpace":
            if self._typing is None:
                row, column = self.selected
                field = "scores" if self.mode == "Score" else "visits"
                value = self.grid[field][row][column]
                self._typing = "" if value is None else str(value)
            self._typing = self._typing[:-1]
        elif key in "0123456789" and len(key) == 1:
            self._typing = (self._typing or "") + key
        elif key in ("-", "+"):
            self._typing = key
        else:
            return False
        if self._typing in ("", "-", "+"):
            return self.set_value(None) if self._typing == "" else False
        return self.set_value(int(self._typing))

    def toggle_edge(self, edge, clear=False):
        if self.mode != "Cell border drawing" or edge is None:
            return False
        def operation():
            prospective = deepcopy(self.grid)
            if edge in prospective["borders"]:
                prospective["borders"].remove(edge)
            elif not clear:
                prospective["borders"].append(edge)
            propagate_towers(prospective)
            check_tower_regions(prospective)
            if edge in self.grid["borders"]:
                self.grid["borders"].remove(edge)
            elif not clear:
                self.grid["borders"].append(edge)
            self.grid = prospective
        return self._change(operation)

    def toggle_tower(self, clear=False):
        if self.mode != "Tower" or self.selected is None:
            return False
        cell = list(self.selected)
        if cell in self.grid["towers"] or clear:
            return self.clear_tower(self.selected)
        return self.mark_tower(self.selected)

    def _tower_change(self, edit):
        prospective = deepcopy(self.grid)
        edit(prospective)
        propagate_towers(prospective)
        return self._change(lambda: setattr(self, "grid", prospective))

    def mark_tower(self, cell, is_tower=True):
        """Shared assertion API for manual edits and analysis; deductions are atomic."""
        cell = list(cell)
        if (len(cell) != 2 or any(type(n) is not int for n in cell)
                or not (0 <= cell[0] < self.grid["rows"] and 0 <= cell[1] < self.grid["columns"])):
            raise ValueError("Cell is outside the grid.")
        def edit(grid):
            target = "tower_marks" if is_tower else "non_tower_marks"
            opposite = "non_tower_marks" if is_tower else "tower_marks"
            if cell in grid[opposite]:
                grid[opposite].remove(cell)
            if cell not in grid[target]:
                grid[target].append(cell)
        return self._tower_change(edit)

    def clear_tower(self, cell):
        cell = list(cell)
        def edit(grid):
            if cell in grid["tower_marks"]:
                grid["tower_marks"].remove(cell)
            # Clearing a forced tower also clears exclusions that would force it again.
            if cell in grid["towers"]:
                regions = region_map(grid)
                region = regions[tuple(cell)]
                grid["non_tower_marks"] = [mark for mark in grid["non_tower_marks"]
                                           if regions[tuple(mark)] != region]
        return self._tower_change(edit)

    def toggle_non_tower(self, clear=False):
        if self.mode != "Tower" or self.selected is None:
            return False
        cell = list(self.selected)
        if cell in self.grid["non_towers"] or clear:
            def edit(grid):
                if cell in grid["non_tower_marks"]:
                    grid["non_tower_marks"].remove(cell)
            return self._tower_change(edit)
        return self.mark_tower(self.selected, is_tower=False)

    def reset_visits(self):
        def operation():
            self.pending_paths = []
            self.grid["visits"] = [[None] * self.grid["columns"] for _ in range(self.grid["rows"])]
        return self._change(operation)

    def history(self, redo=False):
        source, target = ((self.redo_stack, self.undo_stack) if redo
                          else (self.undo_stack, self.redo_stack))
        if not source:
            return False
        target.append(self._frame())
        frame = source.pop()
        self.grid, self.selected = deepcopy(frame["grid"]), frame["selected"]
        self.pending_paths = deepcopy(frame.get("pending_paths", []))
        self.path_notice = ""
        self._typing = None
        return True

    def serialize(self):
        return {"version": 1, "grid": deepcopy(self.grid),
                "undo": deepcopy(self.undo_stack), "redo": deepcopy(self.redo_stack),
                "selected": self.selected, "mode": self.mode,
                "pending_paths": deepcopy(self.pending_paths)}

    @classmethod
    def deserialize(cls, data):
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("Unsupported saved-state format.")
        required = {"version", "grid", "undo", "redo", "selected", "mode"}
        if not required <= set(data) or set(data) - required - {"pending_paths"}:
            raise ValueError("Saved-state fields are missing or unsupported.")
        session = cls(data["grid"])
        session.pending_paths = validate_paths(data.get("pending_paths", []), session.grid)
        def selection(value, grid):
            if value is None:
                return None
            if (not isinstance(value, (list, tuple)) or len(value) != 2
                    or any(type(n) is not int for n in value)
                    or not (0 <= value[0] < grid["rows"] and 0 <= value[1] < grid["columns"])):
                raise ValueError("Invalid selection.")
            return tuple(value)
        session.selected = selection(data["selected"], session.grid)
        if data["mode"] not in MODES:
            raise ValueError("Invalid saved mode.")
        session.mode = data["mode"]
        for field, target in (("undo", session.undo_stack), ("redo", session.redo_stack)):
            if not isinstance(data[field], list):
                raise ValueError("Invalid history.")
            for frame in data[field]:
                if (not isinstance(frame, dict) or not {"grid", "selected"} <= set(frame)
                        or set(frame) - {"grid", "selected", "pending_paths"}):
                    raise ValueError("Invalid history frame.")
                grid = validate_grid(frame["grid"])
                if any(grid[key] != session.grid[key] for key in ("name", "rows", "columns")):
                    raise ValueError("History belongs to another grid.")
                target.append({"grid": grid, "selected": selection(frame["selected"], grid),
                               "pending_paths": validate_paths(frame.get("pending_paths", []), grid)})
        return session
