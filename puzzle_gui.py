"""A persistent editor for the Jane Street arc puzzle (no solving logic)."""

import argparse
import copy
import json
import os
import re
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk


DEFAULT_STATE = Path(__file__).with_name("puzzle_state.json")
DATA_DIRECTORY = Path(__file__).resolve().parent / "grids"
ARC_CYCLE = (None, "tl", "tr", "br", "bl")


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
        self.rows = tk.StringVar(value=str(self.state["rows"]))
        self.columns = tk.StringVar(value=str(self.state["columns"]))
        for label, variable in [("Rows", self.rows), ("Columns", self.columns)]:
            ttk.Label(dimensions, text=label).pack(side="left", padx=4)
            ttk.Spinbox(dimensions, from_=1, to=50, width=4,
                        textvariable=variable).pack(side="left")
        ttk.Button(dimensions, text="Resize grid", command=self.resize).pack(side="left", padx=10)
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
        self.rows.set(str(self.state["rows"]))
        self.columns.set(str(self.state["columns"]))
        self.selected = None
        self.fresh_entry = True
        self.draw()
        self.save()

    def resize(self):
        try:
            rows, columns = int(self.rows.get()), int(self.columns.get())
            if not (1 <= rows <= 50 and 1 <= columns <= 50):
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid size", "Use 1–50 rows and columns.")
            return
        if (rows, columns) == (self.state["rows"], self.state["columns"]):
            return
        if rows < self.state["rows"] or columns < self.state["columns"]:
            if not messagebox.askyesno("Shrink grid", "Cells outside the new size will be removed. You can undo this. Continue?"):
                return
        previous = copy.deepcopy(self.state)
        cells = blank_grid(rows, columns)
        for r in range(min(rows, self.state["rows"])):
            for c in range(min(columns, self.state["columns"])):
                cells[r][c] = self.state["cells"][r][c]
        self.state.update(rows=rows, columns=columns, cells=cells)
        self.selected = None
        self.commit(previous)

    def draw(self):
        self.canvas.delete("all")
        rows, columns = self.state["rows"], self.state["columns"]
        self.size = max(36, min(80, (self.canvas.winfo_width() - 32) / columns,
                                (self.canvas.winfo_height() - 32) / rows))
        size, margin = self.size, 16
        self.canvas.configure(scrollregion=(0, 0, columns * size + 32, rows * size + 32))
        for r, row in enumerate(self.state["cells"]):
            for c, cell in enumerate(row):
                x, y = margin + c * size, margin + r * size
                self.canvas.create_rectangle(x, y, x + size, y + size,
                    fill="#c5e5c8" if cell["green"] else "white", outline="#89939e")
                if cell["arc"]:
                    corner = cell["arc"]
                    cx = x + (size if corner in ("tr", "br") else 0)
                    cy = y + (size if corner in ("bl", "br") else 0)
                    start = {"tl": 270, "tr": 180, "br": 90, "bl": 0}[corner]
                    self.canvas.create_arc(cx - size, cy - size, cx + size, cy + size,
                                           start=start, extent=90, style=tk.ARC,
                                           outline="black", width=3)
                if cell["number"] is not None:
                    self.canvas.create_text(x + size / 2, y + size / 2,
                        text=str(cell["number"]), font=("Segoe UI", max(10, int(size * .24)), "bold"))
                if self.selected == (r, c):
                    self.canvas.create_rectangle(x + 3, y + 3, x + size - 3, y + size - 3,
                                                 outline="#e89520", width=3)
        self.canvas.create_rectangle(margin, margin, margin + columns * size,
                                     margin + rows * size, outline="black", width=4)
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
