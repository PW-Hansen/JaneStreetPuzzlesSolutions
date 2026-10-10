"""Tkinter entry point for the named grid puzzle editor."""
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog
from functions.constants import CELL_SIZE, DEFAULT_ROWS, DEFAULT_COLUMNS, MODES
from functions.model import Puzzle, click_direction
from functions.storage import Storage
from functions.rendering import draw_canvas, export_png

ROOT = Path(__file__).resolve().parent


class Editor:
    def __init__(self, root, puzzle, storage):
        self.root, self.puzzle, self.storage = root, puzzle, storage
        root.title(f'{puzzle.name} — Puzzle editor')
        self.mode = tk.StringVar(value='Select')
        self.status = tk.StringVar(value='Ready. Select a cell to inspect it.')
        self.details = tk.StringVar()
        self.help = tk.StringVar()
        outer = ttk.Frame(root, padding=12)
        outer.pack(fill='both', expand=True)
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        grid_frame = ttk.Frame(outer)
        grid_frame.grid(row=0, column=0, sticky='nsew')
        grid_frame.rowconfigure(0, weight=1)
        grid_frame.columnconfigure(0, weight=1)
        width, height = puzzle.columns * CELL_SIZE + 7, puzzle.rows * CELL_SIZE + 7
        self.canvas = tk.Canvas(grid_frame, width=width, height=height,
                                background='white', highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        side = ttk.Frame(outer, padding=(18, 0, 0, 0), width=290)
        side.grid(row=0, column=1, sticky='ns')
        ttk.Label(side, text='Editing mode', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        self.mode_buttons = []
        for index, mode in enumerate(MODES):
            button = ttk.Button(side, text=f'{mode}   Ctrl+{index}', command=lambda m=mode: self.set_mode(m))
            button.pack(fill='x', pady=3)
            self.mode_buttons.append(button)
            root.bind(f'<Control-Key-{index}>', lambda event, m=mode: self.set_mode(m))
        ttk.Label(side, textvariable=self.help, wraplength=270, justify='left').pack(anchor='w', pady=14)
        ttk.Separator(side).pack(fill='x')
        ttk.Label(side, text='Cell details', font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(14, 5))
        ttk.Label(side, textvariable=self.details, wraplength=270, justify='left').pack(anchor='w')
        ttk.Label(side, text='Analysis', font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(20, 5))
        ttk.Label(side, text='No analysis rules have been defined for this puzzle yet.',
                  wraplength=270, justify='left').pack(anchor='w')
        controls = ttk.Frame(outer)
        controls.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(10, 0))
        for text, command in [('Save state', self.save_state), ('Load state', self.load_state),
                              ('Print state', lambda: self.save_state(printing=True)),
                              ('Undo', self.undo), ('Redo', self.redo),
                              ('Reset edits', self.reset), ('Reset shading', lambda: self.reset(True))]:
            button = ttk.Button(controls, text=text, command=command)
            button.pack(side='left', padx=(0, 5))
            if text == 'Undo': self.undo_button = button
            if text == 'Redo': self.redo_button = button
        ttk.Label(outer, textvariable=self.status, wraplength=880, justify='left').grid(
            row=2, column=0, columnspan=2, sticky='ew', pady=(8, 0))
        self.canvas.bind('<Button-1>', self.click)
        self.canvas.bind('<Button-3>', lambda event: self.click(event, right=True))
        root.bind('<KeyPress>', self.key)
        root.bind('<Control-z>', lambda event: self.undo())
        root.bind('<Control-y>', lambda event: self.redo())
        root.bind('<Control-Z>', lambda event: self.redo())
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.set_mode('Select')
        root.update_idletasks()
        root.geometry(f'{root.winfo_reqwidth()}x{root.winfo_reqheight()}')
        root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())
        self.refresh()

    def set_mode(self, mode):
        self.mode.set('Select' if mode != 'Select' and self.mode.get() == mode else mode)
        help_text = {
            'Select': 'Select and inspect only. Arrow keys move selection; Escape clears it. Right-click, typing, and deletion do not edit.',
            'Digit Entering': 'Click to select, then type 0–9. Right-click, Backspace, or Delete clears the digit. Cells with arrows cannot contain digits.',
            'Arrow Entering': 'Click a triangular quarter to toggle its arrow. Right-click removes that arrow. N/E/S/W toggles directions; Backspace or Delete clears arrows.',
            'Circle/Square': 'Click or Space cycles blank → circle → square. Right-click, Backspace, or Delete clears the shape. Digits can coexist with shapes.',
            'Shading': 'Click or Space cycles white → light grey → light green. Right-click, Backspace, or Delete clears shading.'}
        self.help.set('Active: ' + self.mode.get() + '\n\n' + help_text[self.mode.get()])
        for button, mode_name in zip(self.mode_buttons, MODES):
            button.state(['pressed'] if mode_name == self.mode.get() else ['!pressed'])
        return 'break'

    def refresh(self):
        draw_canvas(self.canvas, self.puzzle)
        self.undo_button.state(['!disabled'] if self.puzzle.undo_stack else ['disabled'])
        self.redo_button.state(['!disabled'] if self.puzzle.redo_stack else ['disabled'])
        if self.puzzle.selected is None:
            self.details.set('No cell selected.')
        else:
            index = self.puzzle.selected
            row, col = divmod(index, self.puzzle.columns)
            cell = self.puzzle.cells[index]
            self.details.set(f'Row {row + 1}, column {col + 1}\nDigit: {cell["digit"] if cell["digit"] is not None else "none"}\n'
                             f'Arrows: {", ".join(cell["arrows"]) or "none"}\nShape: {cell["shape"] or "none"}\n'
                             f'Shading: {("none", "light grey", "light green")[cell["shading"]]}')

    def persist(self, text='Working puzzle saved.'):
        self.refresh()
        try:
            self.storage.save(self.puzzle)
            self.status.set(text)
        except (OSError, ValueError) as exc:
            self.status.set(f'Autosave failed: {exc}')
            messagebox.showerror('Save failed', str(exc), parent=self.root)

    def click(self, event, right=False):
        self.canvas.focus_set()
        x, y = self.canvas.canvasx(event.x) - 3, self.canvas.canvasy(event.y) - 3
        row, col = int(y // CELL_SIZE), int(x // CELL_SIZE)
        if not (0 <= row < self.puzzle.rows and 0 <= col < self.puzzle.columns): return
        self.puzzle.selected = row * self.puzzle.columns + col
        direction = click_direction(x % CELL_SIZE, y % CELL_SIZE, CELL_SIZE)
        changed = self.puzzle.edit(self.puzzle.selected, self.mode.get(), 'right' if right else 'click', direction)
        self.persist('Edit saved.' if changed else 'Cell selected. Incompatible content is preserved.')

    def key(self, event):
        if event.state & 4: return
        index = self.puzzle.selected
        if event.keysym == 'Escape':
            self.puzzle.selected = None
            self.persist('Selection cleared.')
            return 'break'
        if event.keysym in ('Up', 'Down', 'Left', 'Right'):
            row, col = divmod(index if index is not None else 0, self.puzzle.columns)
            dr, dc = {'Up': (-1, 0), 'Down': (1, 0), 'Left': (0, -1), 'Right': (0, 1)}[event.keysym]
            if index is not None:
                row, col = max(0, min(self.puzzle.rows - 1, row + dr)), max(0, min(self.puzzle.columns - 1, col + dc))
            self.puzzle.selected = row * self.puzzle.columns + col
            self.persist('Selection moved.')
            return 'break'
        if index is None: return
        kwargs = {}
        if event.keysym in ('BackSpace', 'Delete'): kwargs['action'] = 'clear'
        elif self.mode.get() == 'Digit Entering' and event.char in '0123456789' and event.char:
            kwargs['digit'] = event.char
        elif self.mode.get() == 'Arrow Entering' and event.char.lower() in ('n', 'e', 's', 'w'):
            kwargs['direction'] = dict(n='north', e='east', s='south', w='west')[event.char.lower()]
        elif event.keysym == 'space' and self.mode.get() in ('Circle/Square', 'Shading'): pass
        else: return
        changed = self.puzzle.edit(index, self.mode.get(), **kwargs)
        if changed: self.persist('Edit saved.')
        return 'break'

    def undo(self):
        if self.puzzle.undo(): self.persist('Undo saved.')
        return 'break'

    def redo(self):
        if self.puzzle.redo(): self.persist('Redo saved.')
        return 'break'

    def reset(self, shading_only=False):
        if self.puzzle.reset(shading_only): self.persist('Shading reset.' if shading_only else 'Edits reset to original clues.')

    def save_state(self, printing=False):
        name = simpledialog.askstring('Print state' if printing else 'Save state', 'State name:', parent=self.root)
        if name is None: return
        try:
            path = self.storage.snapshot_path(self.puzzle.name, name)
            png = ROOT / (name + '.png')
            if (path.exists() or (printing and png.exists())) and not messagebox.askyesno('Replace state', 'Replace the existing state or PNG with this name?', parent=self.root): return
            if printing: export_png(self.puzzle, png)
            self.storage.save(self.puzzle, path)
            self.status.set(f'Saved {name}' + (' and matching PNG.' if printing else '.'))
        except (OSError, ValueError, ImportError) as exc:
            messagebox.showerror('Save failed', str(exc), parent=self.root)
            self.status.set(f'Save failed: {exc}')

    def load_state(self):
        paths = self.storage.snapshots(self.puzzle.name)
        if not paths:
            self.status.set('No saved states for this puzzle.')
            return
        dialog = tk.Toplevel(self.root)
        dialog.title('Load state — ' + self.puzzle.name)
        dialog.transient(self.root)
        dialog.grab_set()
        listing = tk.Listbox(dialog, width=45, height=min(12, len(paths)), exportselection=False)
        listing.pack(padx=12, pady=12)
        for path in paths: listing.insert('end', path.stem)
        listing.selection_set(0)
        def load():
            if not listing.curselection(): return
            try:
                loaded = self.storage.load(paths[listing.curselection()[0]], self.puzzle.name)
                self.storage.save(loaded)
                self.puzzle = loaded
                self.refresh()
                self.status.set('Saved state loaded.')
                dialog.destroy()
            except (OSError, ValueError) as exc:
                messagebox.showerror('Load failed', str(exc), parent=dialog)
        ttk.Button(dialog, text='Load', command=load).pack(pady=(0, 12))
        listing.bind('<Double-Button-1>', lambda event: load())

    def close(self):
        data = self.puzzle.to_dict()
        data['undo'], data['redo'] = [], []
        try:
            self.storage.save(Puzzle.from_dict(data))
        except (OSError, ValueError) as exc:
            messagebox.showerror('Save failed', str(exc), parent=self.root)
            return
        self.root.destroy()


def launcher(root, storage):
    root.title('Puzzle launcher')
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Create or open a named puzzle', font=('Segoe UI', 14, 'bold')).pack(pady=(0, 12))
    paths = storage.puzzles()
    listing = tk.Listbox(frame, width=48, height=10, exportselection=False)
    listing.pack(fill='both', expand=True)
    for path in paths: listing.insert('end', path.stem)
    if paths: listing.selection_set(0)
    def start(puzzle):
        frame.destroy()
        Editor(root, puzzle, storage)
    def create():
        dialog = tk.Toplevel(root)
        dialog.title('New puzzle')
        dialog.transient(root)
        dialog.resizable(False, False)
        dialog.grab_set()
        form = ttk.Frame(dialog, padding=16)
        form.pack(fill='both', expand=True)
        fields = []
        for row, (label, default) in enumerate([
                ('Puzzle name', ''), ('Rows', DEFAULT_ROWS), ('Columns', DEFAULT_COLUMNS)]):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=5)
            value = tk.StringVar(value=str(default))
            entry = ttk.Entry(form, textvariable=value, width=30)
            entry.grid(row=row, column=1, sticky='ew', pady=5)
            fields.append((value, entry))
        def submit(event=None):
            try:
                name = fields[0][0].get()
                path = storage.working_path(name)
                if path.exists(): raise ValueError('That puzzle already exists. Open it instead.')
                try:
                    rows, columns = (int(field[0].get()) for field in fields[1:])
                except ValueError:
                    raise ValueError('Rows and columns must be whole numbers between 1 and 100.') from None
                puzzle = Puzzle(name, rows, columns)
                storage.save(puzzle)
            except (OSError, ValueError) as exc:
                messagebox.showerror('Create failed', str(exc), parent=dialog)
                return
            dialog.destroy()
            start(puzzle)
        buttons = ttk.Frame(form)
        buttons.grid(row=3, column=0, columnspan=2, sticky='e', pady=(12, 0))
        ttk.Button(buttons, text='Cancel', command=dialog.destroy).pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text='Create', command=submit).pack(side='left')
        dialog.bind('<Return>', submit)
        dialog.bind('<Escape>', lambda event: dialog.destroy())
        fields[0][1].focus_set()
    def open_path(path):
        try:
            puzzle = storage.load(path)
            storage.save(puzzle)
            start(puzzle)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Open failed', str(exc), parent=root)
    ttk.Button(frame, text='Create puzzle', command=create).pack(fill='x', pady=(12, 4))
    ttk.Button(frame, text='Open selected puzzle', command=lambda: open_path(paths[listing.curselection()[0]]) if listing.curselection() else None).pack(fill='x', pady=4)
    def browse():
        path = filedialog.askopenfilename(parent=root, title='Open puzzle or saved state', initialdir=ROOT, filetypes=[('Puzzle JSON', '*.json')])
        if path: open_path(path)
    ttk.Button(frame, text='Open puzzle or saved state file…', command=browse).pack(fill='x', pady=4)
    listing.bind('<Double-Button-1>', lambda event: open_path(paths[listing.curselection()[0]]) if listing.curselection() else None)


def main():
    root = tk.Tk()
    storage = Storage(ROOT)
    if len(sys.argv) > 2:
        root.destroy()
        raise SystemExit('Usage: python puzzle_gui.py [name]')
    if len(sys.argv) == 2:
        try:
            puzzle = storage.load(storage.working_path(sys.argv[1]), sys.argv[1])
        except (OSError, ValueError) as exc:
            messagebox.showerror('Open failed', str(exc), parent=root)
            root.destroy()
            raise SystemExit(1)
        Editor(root, puzzle, storage)
    else:
        launcher(root, storage)
    root.mainloop()


if __name__ == '__main__':
    main()

