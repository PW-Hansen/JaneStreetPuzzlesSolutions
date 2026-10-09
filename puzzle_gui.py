"""Tkinter puzzle editor. Backend operations live in functions/."""

import argparse
from time import perf_counter
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from functions.constants import MODES, CELL_SIZE, PADDING
from functions.movements import MovementSearch
from functions.persistence import puzzles, snapshots, snapshot_path
from functions.rendering import dimensions, draw_grid, cell_at, edge_at
from functions.workflow import (
    create_named, open_named, autosave, save_snapshot, load_snapshot, print_state,
)


class PuzzleGUI(ttk.Frame):
    def __init__(self, root, session):
        super().__init__(root, padding=12)
        self.session = session
        self.grid(sticky="nsew")
        root.title(f"{session.grid['name']} — Puzzle editor")
        root.resizable(True, True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.mode = tk.StringVar(value=session.mode)
        self.details = tk.StringVar()
        self.value = tk.StringVar()
        self.message = tk.StringVar(value="Ready. Changes save automatically.")
        self._save_pending = None
        ttk.Label(self, text=f"{session.grid['name']} · {session.grid['rows']}×{session.grid['columns']} grid",
                  font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        toolbar = ttk.Frame(self)
        toolbar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        for i, mode in enumerate(MODES):
            ttk.Radiobutton(toolbar, text=f"{mode} (Ctrl+{i})", value=mode,
                            variable=self.mode, command=lambda m=mode: self.change_mode(m)).pack(side="left", padx=(0, 12))
        viewport = ttk.Frame(self)
        viewport.grid(row=2, column=0, sticky="nsew")
        viewport.columnconfigure(0, weight=1)
        viewport.rowconfigure(0, weight=1)
        width, height = dimensions(session.grid)
        self.canvas = tk.Canvas(viewport, width=width, height=height, background="white",
                                highlightthickness=0, takefocus=True, scrollregion=(0, 0, width, height))
        self.canvas.grid(row=0, column=0, sticky="nsew")
        xs = ttk.Scrollbar(viewport, orient="horizontal", command=self.canvas.xview)
        ys = ttk.Scrollbar(viewport, orient="vertical", command=self.canvas.yview)
        xs.grid(row=1, column=0, sticky="ew")
        ys.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        inspector = ttk.LabelFrame(self, text="Selected cell", padding=12)
        inspector.grid(row=2, column=1, sticky="nsew", padx=(12, 0))
        ttk.Label(inspector, textvariable=self.details, wraplength=240).pack(anchor="w", pady=(0, 14))
        ttk.Label(inspector, text="Integer value").pack(anchor="w")
        self.entry = ttk.Entry(inspector, textvariable=self.value, width=26)
        self.entry.pack(fill="x", pady=5)
        self.entry.bind("<Return>", lambda event: self.apply_value())
        self.apply_button = ttk.Button(inspector, text="Set value", command=self.apply_value)
        self.apply_button.pack(fill="x", pady=(0, 14))
        movement_controls = ttk.LabelFrame(inspector, text="Arithmetic lookahead", padding=6)
        movement_controls.pack(fill="x", pady=(0, 10))
        self.lookahead = tk.StringVar(value="3")
        ttk.Label(movement_controls, text="Moves ahead:").pack(side="left")
        ttk.Entry(movement_controls, textvariable=self.lookahead, width=5).pack(side="left", padx=6)
        self.movement_button = ttk.Button(inspector, text="Generate valid movements", command=self.generate_movements)
        self.movement_button.pack(fill="x", pady=(0, 10))
        help_text = ("Select: click to inspect.\nArrow keys: move selection.\nEscape: clear selection.\n\n"
                     "Score / Visit number: type digits into the selected cell or use Set value. "
                     "The first digit replaces the old value. Backspace removes a digit. "
                     "Delete or right-click clears that mode’s value. Signed integers are allowed.\n\n"
                     "Borders: click near a shared edge to toggle it. Right-click makes it thin. "
                     "Typing, Backspace, and Delete do nothing in border mode.\n\n"
                     "Tower: click to toggle a tower. Right-click or Delete removes it. "
                     "Blue = tower; light green = available region; light grey = region already has a tower.")
        help_frame = ttk.Frame(inspector)
        help_frame.pack(fill="both", expand=True)
        help_widget = tk.Text(help_frame, width=30, height=12, wrap="word", font=("Segoe UI", 10))
        help_widget.insert("1.0", help_text)
        help_widget.configure(state="disabled")
        help_widget.pack(side="left", fill="both", expand=True)
        help_scroll = ttk.Scrollbar(help_frame, command=help_widget.yview)
        help_scroll.pack(side="right", fill="y")
        help_widget.configure(yscrollcommand=help_scroll.set)
        controls = ttk.Frame(self)
        controls.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        for label, command in (("Save state", self.save_state), ("Load state", self.load_state),
                               ("Print state", self.print_current), ("Reset visit numbers", self.reset_visits)):
            ttk.Button(controls, text=label, command=command).pack(side="left", padx=(0, 8))
        self.undo_button = ttk.Button(controls, text="Undo", command=self.undo)
        self.undo_button.pack(side="left", padx=(0, 8))
        self.redo_button = ttk.Button(controls, text="Redo", command=lambda: self.undo(True))
        self.redo_button.pack(side="left")
        status = ttk.Label(self, textvariable=self.message, wraplength=700)
        status.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        status.bind("<Configure>", lambda event: status.configure(wraplength=max(100, event.width)))
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<Button-3>", lambda event: self.click(event, True))
        self.canvas.bind("<Key>", self.key)
        for i, mode in enumerate(MODES):
            root.bind(f"<Control-Key-{i}>", lambda event, m=mode: self.change_mode(m))
        root.bind("<Control-z>", lambda event: self.undo())
        root.bind("<Control-y>", lambda event: self.undo(True))
        root.bind("<Control-Shift-Z>", lambda event: self.undo(True))
        root.bind("<Control-s>", lambda event: self.flush_save())
        root.bind("<Escape>", self.clear_selection)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        root.update_idletasks()
        screen_w, screen_h = root.winfo_screenwidth() - 80, root.winfo_screenheight() - 140
        root.geometry(f"{min(max(self.winfo_reqwidth(), 900), screen_w)}x{min(max(self.winfo_reqheight(), 600), screen_h)}")
        root.minsize(min(820, screen_w), min(520, screen_h))
        self.canvas.focus_set()

    def refresh(self):
        draw_grid(self.canvas, self.session)
        self.mode.set(self.session.mode)
        selected = self.session.selected
        if selected is None:
            self.details.set(f"Mode: {self.session.mode}\nNo cell selected.")
            self.value.set("")
        else:
            r, c = selected
            score, visit = self.session.grid["scores"][r][c], self.session.grid["visits"][r][c]
            self.details.set(f"Mode: {self.session.mode}\nRow {r + 1}, column {c + 1}\nScore: {score if score is not None else '—'}\nVisit number: {visit if visit is not None else '—'}")
            self.details.set(self.details.get() + f"\nTower: {'yes' if [r, c] in self.session.grid['towers'] else 'no'}")
            value = visit if self.session.mode == "Visit number" else score
            self.value.set("" if value is None else str(value))
        editable = selected is not None and self.session.mode in ("Score", "Visit number")
        self.entry.configure(state="normal" if editable else "disabled")
        self.apply_button.configure(state="normal" if editable else "disabled")
        self.undo_button.configure(state="normal" if self.session.undo_stack else "disabled")
        self.redo_button.configure(state="normal" if self.session.redo_stack else "disabled")
        movement_ready = (selected is not None
                          and self.session.grid["scores"][selected[0]][selected[1]] is not None
                          and self.session.grid["visits"][selected[0]][selected[1]] is not None
                          and self.session.grid["visits"][selected[0]][selected[1]] >= 0)
        self.movement_button.configure(state="normal" if movement_ready else "disabled")

    def generate_movements(self):
        selected = self.session.selected
        if selected is None:
            return
        row, column = selected
        try:
            search = MovementSearch(self.session.grid["scores"][row][column],
                                    self.session.grid["visits"][row][column],
                                    int(self.lookahead.get()))
        except ValueError as error:
            self.message.set(str(error))
            return
        window = tk.Toplevel(self)
        window.title(f"Movements from r{row + 1}c{column + 1}")
        window.geometry("540x440")
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        start_score, start_visit = search.worklist[0][:2]
        ttk.Label(window, text=f"Score {start_score}, visit {start_visit} → visit {search.max_visit}",
                  padding=10).grid(row=0, column=0, columnspan=2, sticky="w")
        output = tk.Text(window, wrap="word", state="disabled")
        output.grid(row=1, column=0, sticky="nsew", padx=(10, 0))
        scroll = ttk.Scrollbar(window, command=output.yview)
        scroll.grid(row=1, column=1, sticky="ns", padx=(0, 10))
        output.configure(yscrollcommand=scroll.set)
        status = tk.StringVar()
        ttk.Label(window, textvariable=status, wraplength=500, padding=10).grid(row=2, column=0, columnspan=2, sticky="ew")
        started = perf_counter()
        count = 0
        integers = set()
        pending = None
        stopped = False

        def finish(label):
            nonlocal stopped, pending
            stopped = True
            if pending is not None:
                window.after_cancel(pending)
                pending = None
            abort.configure(state="disabled")
            status.set(f"{label}: {count} valid sequences, {len(integers)} distinct integers. {perf_counter() - started:.2f} seconds.")

        def batch():
            nonlocal count, pending
            pending = None
            lines = []
            for _ in range(200):
                if not search.worklist:
                    break
                result = search.advance()
                if result is not None:
                    score, visit, operations, last = result
                    count += 1
                    integers.add(score)
                    lines.append(f"{operations or '(no moves)'} → {score}\n")
            if lines:
                output.configure(state="normal")
                output.insert("end", "".join(lines))
                output.configure(state="disabled")
            if not search.worklist:
                output.configure(state="normal")
                output.insert("end", "\nValid integers: " + ", ".join(map(str, sorted(integers))) + "\n")
                output.configure(state="disabled")
                finish("Complete")
            else:
                status.set(f"{count} valid sequences so far. {perf_counter() - started:.2f} seconds.")
                pending = window.after(10, batch)

        abort = ttk.Button(window, text="Abort", command=lambda: finish("Aborted (partial results)"))
        abort.grid(row=3, column=0, columnspan=2, pady=(0, 10))
        def close():
            if not stopped:
                finish("Aborted")
            window.destroy()
        window.protocol("WM_DELETE_WINDOW", close)
        batch()

    def queue_save(self):
        if self._save_pending:
            self.after_cancel(self._save_pending)
        self._save_pending = self.after(200, self.flush_save)

    def flush_save(self):
        if self._save_pending:
            self.after_cancel(self._save_pending)
            self._save_pending = None
        try:
            autosave(self.session)
            self.message.set("Saved automatically.")
            return True
        except (OSError, ValueError) as error:
            self.message.set(f"Save failed: {error}")
            return False

    def changed(self, changed=True):
        self.refresh()
        if changed:
            self.queue_save()

    def change_mode(self, mode):
        self.session.set_mode(mode)
        self.changed()
        self.canvas.focus_set()
        return "break"

    def click(self, event, right=False):
        self.canvas.focus_set()
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        if self.session.mode == "Cell border drawing":
            try:
                self.changed(self.session.toggle_edge(edge_at(self.session.grid, x, y), clear=right))
            except ValueError as error:
                self.message.set(str(error))
        else:
            cell = cell_at(self.session.grid, x, y)
            if cell is not None:
                self.session.select(cell)
                if self.session.mode == "Tower":
                    try:
                        self.session.toggle_tower(clear=right)
                    except ValueError as error:
                        self.changed()
                        self.message.set(str(error))
                        return
                elif right and self.session.mode != "Select":
                    self.session.set_value(None)
                self.changed()

    def reveal_selection(self):
        if self.session.selected is None:
            return
        row, column = self.session.selected
        width, height = dimensions(self.session.grid)
        for position, extent, viewport, start, move in (
            (PADDING + column * CELL_SIZE, width, self.canvas.winfo_width(), self.canvas.canvasx(0), self.canvas.xview_moveto),
            (PADDING + row * CELL_SIZE, height, self.canvas.winfo_height(), self.canvas.canvasy(0), self.canvas.yview_moveto)):
            if position < start:
                move(max(0, (position - PADDING) / extent))
            elif position + CELL_SIZE > start + viewport:
                move((position + CELL_SIZE + PADDING - viewport) / extent)

    def key(self, event):
        if event.state & 4:
            return
        moves = {"Left": (0, -1), "Right": (0, 1), "Up": (-1, 0), "Down": (1, 0)}
        if event.keysym in moves:
            self.session.move(*moves[event.keysym])
            self.reveal_selection()
            self.changed()
        elif event.keysym == "Escape":
            self.session.select(None)
            self.changed()
        else:
            key = event.keysym if event.keysym in ("BackSpace", "Delete") else event.char
            if self.session.mode == "Tower" and key == "Delete":
                self.changed(self.session.toggle_tower(clear=True))
            else:
                self.changed(self.session.type_key(key))
        return "break"

    def apply_value(self):
        try:
            self.changed(self.session.input_text(self.value.get().strip()))
            self.canvas.focus_set()
        except ValueError as error:
            self.message.set(str(error))

    def clear_selection(self, event=None):
        self.session.select(None)
        self.changed()
        self.canvas.focus_set()
        return "break"

    def undo(self, redo=False):
        self.changed(self.session.history(redo))
        self.reveal_selection()
        return "break"

    def snapshot_name(self, title):
        name = simpledialog.askstring(title, "Name:", parent=self.winfo_toplevel())
        if name is None:
            return None
        try:
            path = snapshot_path(self.session.grid["name"], name)
        except ValueError as error:
            self.message.set(str(error))
            return None
        if path.exists() and not messagebox.askyesno("Replace state?", "A snapshot with this name exists. Replace it?", parent=self):
            return None
        return name

    def save_state(self):
        name = self.snapshot_name("Save state")
        if name is not None:
            try:
                save_snapshot(self.session, name)
                self.message.set(f"Saved state: {name}")
            except (OSError, ValueError) as error:
                self.message.set(f"Save state failed: {error}")

    def load_state(self):
        names = snapshots(self.session.grid["name"])
        if not names:
            self.message.set("No saved states for this puzzle.")
            return
        dialog = tk.Toplevel(self)
        dialog.title("Load state")
        dialog.transient(self.winfo_toplevel())
        selection = tk.StringVar(value=names[0])
        ttk.Combobox(dialog, textvariable=selection, values=names, state="readonly", width=35).pack(padx=16, pady=16)
        def load():
            try:
                restored = load_snapshot(self.session, selection.get())
                if self._save_pending:
                    self.after_cancel(self._save_pending)
                    self._save_pending = None
                self.session = restored
                self.refresh()
                self.reveal_selection()
                self.message.set(f"Loaded state: {selection.get()}")
                dialog.destroy()
                self.canvas.focus_set()
            except (OSError, ValueError) as error:
                self.message.set(f"Load failed: {error}")
        ttk.Button(dialog, text="Load", command=load).pack(pady=(0, 16))
        dialog.grab_set()

    def print_current(self):
        name = self.snapshot_name("Print state")
        if name is not None:
            try:
                path, snapshot = print_state(self.session, name)
                self.message.set(f"Exported {path.name} and saved matching state.")
            except (OSError, ValueError, ImportError) as error:
                self.message.set(f"Export failed: {error}")

    def reset_visits(self):
        self.changed(self.session.reset_visits())
        self.message.set("Visit numbers cleared. Scores and borders preserved. Undo restores visits.")

    def close(self):
        if self.flush_save() or messagebox.askyesno("Save failed", "Close without saving the latest changes?", parent=self):
            self.winfo_toplevel().destroy()


class Launcher(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=20)
        self.grid(sticky="nsew")
        root.title("Puzzle launcher")
        root.resizable(False, False)
        self.name, self.rows, self.columns = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.message = tk.StringVar()
        ttk.Label(self, text="Create a puzzle", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        for row, (label, variable) in enumerate((("Name", self.name), ("Rows", self.rows), ("Columns", self.columns)), 1):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12))
            entry = ttk.Entry(self, textvariable=variable, width=30)
            entry.grid(row=row, column=1, pady=4)
            if row == 1:
                entry.focus_set()
        ttk.Button(self, text="Create puzzle", command=self.create).grid(row=4, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Separator(self).grid(row=5, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Label(self, text="Open a puzzle or saved state", font=("Segoe UI", 12, "bold")).grid(row=6, column=0, columnspan=2, sticky="w")
        names = puzzles()
        self.existing = tk.StringVar(value=names[0] if names else "")
        self.snapshot = tk.StringVar(value="Working puzzle")
        combo = ttk.Combobox(self, textvariable=self.existing, values=names, state="readonly", width=28)
        combo.grid(row=7, column=0, columnspan=2, sticky="ew", pady=8)
        combo.bind("<<ComboboxSelected>>", self.update_snapshots)
        self.states = ttk.Combobox(self, textvariable=self.snapshot, state="readonly", width=28)
        self.states.grid(row=8, column=0, columnspan=2, sticky="ew", pady=4)
        self.update_snapshots()
        ttk.Button(self, text="Open", command=self.open,
                   state="normal" if names else "disabled").grid(row=9, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Label(self, textvariable=self.message, foreground="#b91c1c", wraplength=340).grid(row=10, column=0, columnspan=2, sticky="w")

    def update_snapshots(self, event=None):
        names = snapshots(self.existing.get()) if self.existing.get() else []
        self.states.configure(values=["Working puzzle"] + ["Saved: " + name for name in names])
        self.snapshot.set("Working puzzle")

    def show(self, session):
        self.grid_remove()
        self.editor = PuzzleGUI(self.winfo_toplevel(), session)

    def create(self):
        try:
            self.show(create_named(self.name.get(), self.rows.get(), self.columns.get()))
        except (OSError, ValueError) as error:
            self.message.set(str(error))

    def open(self):
        try:
            snapshot = self.snapshot.get()[7:] if self.snapshot.get().startswith("Saved: ") else None
            self.show(open_named(self.existing.get(), snapshot))
        except (OSError, ValueError) as error:
            self.message.set(str(error))


def main():
    parser = argparse.ArgumentParser(description="Open the puzzle launcher or a named puzzle.")
    parser.add_argument("name", nargs="?")
    args = parser.parse_args()
    root = tk.Tk()
    if args.name:
        try:
            PuzzleGUI(root, open_named(args.name))
        except (OSError, ValueError) as error:
            launcher = Launcher(root)
            launcher.message.set(f"Could not open {args.name}: {error}")
    else:
        Launcher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
