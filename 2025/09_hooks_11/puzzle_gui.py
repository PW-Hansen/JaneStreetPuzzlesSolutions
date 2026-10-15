"""Launch the named grid editor: python puzzle_gui.py [name]."""
import argparse
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog
from pathlib import Path

from functions.constants import CELL_SIZE, MARGIN, COLORS, MODES, COLOR_KEYPAD
from functions.model import Puzzle, safe_name, read, write, save_snapshot, load_snapshot
from functions.rendering import draw, export_png

ROOT = Path(__file__).resolve().parent


class NewPuzzleDialog(simpledialog.Dialog):
    """Collect and validate the new puzzle setup in a single window."""

    def body(self, master):
        self.fields = {}
        for row, (key, label) in enumerate((('name', 'Puzzle name'), ('rows', 'Rows'), ('cols', 'Columns'))):
            ttk.Label(master, text=label).grid(row=row, column=0, sticky='w', padx=8, pady=7)
            field = ttk.Entry(master, width=28)
            field.grid(row=row, column=1, padx=8, pady=7)
            self.fields[key] = field
        self.error = tk.StringVar()
        ttk.Label(master, textvariable=self.error, foreground='#b71c1c', wraplength=330
                  ).grid(row=3, column=0, columnspan=2, sticky='w', padx=8, pady=7)
        return self.fields['name']

    def validate(self):
        try:
            name = safe_name(self.fields['name'].get())
            if (ROOT / 'grids' / f'{name}.json').exists():
                raise ValueError('A puzzle with this name already exists. Open it instead.')
            try:
                rows = int(self.fields['rows'].get())
                cols = int(self.fields['cols'].get())
            except ValueError:
                raise ValueError('Rows and columns must be whole numbers from 1 to 50.') from None
            self.pending = Puzzle(name, rows, cols)
            return True
        except ValueError as exc:
            self.error.set(str(exc))
            return False

    def apply(self):
        self.result = self.pending


class Editor:
    def __init__(self, root, puzzle):
        self.root, self.puzzle = root, puzzle
        self.selected = None
        self.mode = tk.IntVar(value=0)
        self.color = tk.IntVar(value=1)
        self.fresh_entry = True
        root.title(f"{puzzle.data['name']} — Puzzle editor")
        root.geometry('1100x850')
        root.minsize(780, 600)
        outer = ttk.Frame(root, padding=16)
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)
        workspace = ttk.Frame(outer)
        workspace.grid(row=0, column=0, sticky='nsew')
        workspace.columnconfigure(0, weight=1)
        workspace.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(workspace, background='white', highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        yscroll = ttk.Scrollbar(workspace, orient='vertical', command=self.canvas.yview)
        yscroll.grid(row=0, column=1, sticky='ns')
        xscroll = ttk.Scrollbar(workspace, orient='horizontal', command=self.canvas.xview)
        xscroll.grid(row=1, column=0, sticky='ew')
        self.canvas.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        panel = ttk.Frame(outer, padding=(20, 0, 0, 0), width=270)
        panel.grid(row=0, column=1, sticky='ns')
        ttk.Label(panel, text='Editing mode', font=('Segoe UI', 14, 'bold')).pack(anchor='w', pady=(0, 10))
        for i, mode in enumerate(MODES):
            ttk.Radiobutton(panel, text=f'{mode}   Ctrl+{i}', variable=self.mode, value=i,
                            command=lambda i=i: self.set_mode(i, from_radio=True)).pack(anchor='w', pady=5)
        self.last_mode = 0
        ttk.Label(panel, text='Cell colors · keys 1–9, 0 clears').pack(anchor='w', pady=(22, 8))
        palette = ttk.Frame(panel)
        palette.pack(anchor='w')
        for row, keys in enumerate(COLOR_KEYPAD):
            for col, i in enumerate(keys):
                tk.Radiobutton(palette, text=str(i) if i else '0 · No color', indicatoron=False,
                               background=COLORS[i], variable=self.color, value=i, width=5 if i else 17
                               ).grid(row=row, column=col, columnspan=1 if i else 3, sticky='ew', padx=2, pady=2)
        self.details = tk.StringVar()
        ttk.Label(panel, textvariable=self.details, wraplength=245, justify='left').pack(anchor='w', pady=22)
        ttk.Label(panel, text='Analysis', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        ttk.Label(panel, text='No puzzle analysis operations are configured. This editor stores manual entries, borders and colors.',
                  wraplength=245, justify='left').pack(anchor='w', pady=8)
        controls = ttk.Frame(outer)
        controls.grid(row=1, column=0, columnspan=2, sticky='w', pady=(14, 8))
        for label, command in [('Save state', self.save_state), ('Load state', self.load_state), ('Print state', self.print_state),
                               ('Undo', self.undo), ('Redo', self.redo), ('Reset edits', self.reset)]:
            ttk.Button(controls, text=label, command=command).pack(side='left', padx=(0, 7))
        self.status = tk.StringVar(value='Ready. Select a cell to inspect it.')
        ttk.Label(outer, textvariable=self.status, wraplength=950).grid(row=2, column=0, columnspan=2, sticky='w')
        self.canvas.bind('<Button-1>', lambda e: self.click(e, False))
        self.canvas.bind('<Button-3>', lambda e: self.click(e, True))
        root.bind('<Key>', self.key)
        for i in range(4):
            root.bind(f'<Control-Key-{i}>', lambda e, i=i: self.set_mode(i))
        root.bind('<Control-z>', lambda e: self.undo())
        root.bind('<Control-y>', lambda e: self.redo())
        root.bind('<Control-Z>', lambda e: self.redo())
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.redraw()

    def set_mode(self, mode, from_radio=False):
        self.mode.set(0 if mode and self.last_mode == mode else mode)
        self.last_mode = self.mode.get()
        self.fresh_entry = True
        self.redraw()
        self.canvas.focus_set()
        return 'break'

    def redraw(self):
        self.canvas.delete('all')
        data = self.puzzle.data
        self.canvas.configure(scrollregion=(0, 0, 2*MARGIN+data['cols']*CELL_SIZE, 2*MARGIN+data['rows']*CELL_SIZE))
        draw(data, lambda box, color: self.canvas.create_rectangle(*box, fill=color, outline=''),
             lambda points, color, width: self.canvas.create_line(*points, fill=color, width=width),
             lambda pos, value, color: self.canvas.create_text(*pos, text=value, fill=color, font=('Segoe UI', 23)), self.selected)
        selected = 'None' if self.selected is None else f'row {self.selected[0]+1}, column {self.selected[1]+1}'
        value = '' if self.selected is None else data['entries'].get(self.cell_key(), '(empty)')
        help_text = (
            'Click to select. Arrow keys move; Escape clears selection. Editing is disabled.',
            'Click a cell or an outside clue slot. Type letters/digits (up to 12). A new selection replaces its entry; further keys append. Right-click/Delete clears; Backspace removes the last character.',
            'Click near an internal edge to toggle its thick border. Right-click near an edge removes it. Delete/Backspace clears the selected cell’s internal edges.',
            'Choose a color with 1–9, then click cells. Clicking the same color clears it. Right-click/Delete/Backspace clears only the cell color.'
        )[self.mode.get()]
        self.details.set(f'Active: {MODES[self.mode.get()]}\n\nSelected: {selected}\nEntry: {value}\n\n{help_text}')

    def cell_key(self):
        return ','.join(map(str, self.selected))

    def persist(self):
        try:
            write(ROOT / 'grids' / f"{self.puzzle.data['name']}.json", self.puzzle.data)
            self.status.set('Working puzzle saved automatically.')
            return True
        except (OSError, ValueError) as exc:
            self.status.set(f'Automatic save failed: {exc}')
            messagebox.showerror('Save failed', str(exc), parent=self.root)
            return False

    def changed(self):
        self.persist()
        self.redraw()

    def click(self, event, right):
        self.canvas.focus_set()
        x, y = self.canvas.canvasx(event.x)-MARGIN, self.canvas.canvasy(event.y)-MARGIN
        r, c = int(y//CELL_SIZE), int(x//CELL_SIZE)
        rows, cols = self.puzzle.data['rows'], self.puzzle.data['cols']
        if not ((0 <= r < rows and -1 <= c <= cols) or (0 <= c < cols and -1 <= r <= rows)):
            return
        self.selected, self.fresh_entry = (r, c), True
        mode = self.mode.get()
        if mode == 1 and right:
            self.puzzle.change('entries', self.cell_key(), None)
        elif mode == 2:
            # The nearest edge must be within a deliberate 14-pixel hit area.
            cx, cy = round(x/CELL_SIZE), round(y/CELL_SIZE)
            dx, dy = abs(x-cx*CELL_SIZE), abs(y-cy*CELL_SIZE)
            edge = None
            if dx <= dy and dx <= 14 and 0 < cx < cols and 0 <= r < rows:
                edge = f'v,{r},{cx}'
            elif dy <= 14 and 0 < cy < rows and 0 <= c < cols:
                edge = f'h,{cy},{c}'
            if edge:
                self.puzzle.change('borders', edge, None if right or edge in self.puzzle.data['borders'] else True)
        elif mode == 3 and 0 <= r < rows and 0 <= c < cols:
            color = self.color.get()
            self.puzzle.change('colors', self.cell_key(), None if right or not color or self.puzzle.data['colors'].get(self.cell_key()) == color else color)
        self.changed() if mode else self.redraw()

    def key(self, event):
        if event.state & 4:
            return
        if event.keysym == 'Escape':
            self.selected = None
        elif event.keysym in ('Up', 'Down', 'Left', 'Right'):
            r, c = self.selected or (0, 0)
            dr, dc = {'Up': (-1,0), 'Down': (1,0), 'Left': (0,-1), 'Right': (0,1)}[event.keysym]
            nr, nc = r+dr, c+dc
            rows, cols = self.puzzle.data['rows'], self.puzzle.data['cols']
            if ((0 <= nr < rows and -1 <= nc <= cols) or (0 <= nc < cols and -1 <= nr <= rows)):
                self.selected = (nr, nc)
            self.fresh_entry = True
        elif self.mode.get() == 3 and event.char in '0123456789' and event.char:
            self.color.set(int(event.char))
        elif self.selected and self.mode.get():
            mode, key = self.mode.get(), self.cell_key()
            if event.keysym in ('Delete', 'BackSpace'):
                if mode == 1:
                    value = self.puzzle.data['entries'].get(key, '')
                    self.puzzle.change('entries', key, (value[:-1] or None) if event.keysym == 'BackSpace' else None)
                elif mode == 3:
                    self.puzzle.change('colors', key, None)
                elif mode == 2:
                    r, c = self.selected
                    self.puzzle.clear_cell_borders(r, c)
                self.changed()
            elif mode == 1 and event.char and event.char.isalnum():
                current = '' if self.fresh_entry else self.puzzle.data['entries'].get(key, '')
                self.puzzle.change('entries', key, (current+event.char.upper())[:12])
                self.fresh_entry = False
                self.changed()
        self.redraw()

    def undo(self):
        self.puzzle.undo()
        self.fresh_entry = True
        self.changed()
        return 'break'

    def redo(self):
        self.puzzle.redo()
        self.fresh_entry = True
        self.changed()
        return 'break'

    def state_name(self):
        name = simpledialog.askstring('Snapshot name', 'Name for this state:', parent=self.root)
        if name is None:
            return None
        return safe_name(name)

    def save_state(self, printing=False):
        try:
            name = self.state_name()
            if name is None:
                return
            path = ROOT / 'saved states' / self.puzzle.data['name'] / f'{name}.json'
            png = ROOT / f'{name}.png'
            if (path.exists() or (printing and png.exists())) and not messagebox.askyesno('Replace saved state?', f'Replace existing files for “{name}”?', parent=self.root):
                return
            if printing:
                export_png(png, self.puzzle.data, self.selected)
            save_snapshot(path, self.puzzle, self.selected)
            self.status.set(f'Saved {path.name}' + (f' and {png.name}.' if printing else '.'))
        except (OSError, ValueError, ImportError) as exc:
            messagebox.showerror('Save failed', str(exc), parent=self.root)

    def print_state(self):
        self.save_state(printing=True)

    def load_state(self):
        directory = ROOT / 'saved states' / self.puzzle.data['name']
        directory.mkdir(parents=True, exist_ok=True)
        path = filedialog.askopenfilename(parent=self.root, initialdir=directory, filetypes=[('Puzzle snapshots', '*.json')])
        if path:
            try:
                if Path(path).resolve().parent != directory.resolve():
                    raise ValueError('Choose a saved state belonging to this puzzle.')
                self.selected = load_snapshot(path, self.puzzle)
                self.fresh_entry = True
                self.changed()
            except (OSError, ValueError, KeyError, TypeError) as exc:
                messagebox.showerror('Load failed', str(exc), parent=self.root)

    def reset(self):
        if messagebox.askyesno('Reset edits', 'Clear all manually entered text, colors and internal borders? This can be undone.', parent=self.root):
            self.puzzle.reset_edits()
            self.changed()

    def close(self):
        if self.persist():
            self.puzzle.undo_stack.clear()
            self.puzzle.redo_stack.clear()
            self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', nargs='?')
    args = parser.parse_args()
    root = tk.Tk()

    def open_puzzle(name=None, path=None, create=False):
        try:
            loaded_selection = None
            if create:
                puzzle = NewPuzzleDialog(root, title='New puzzle').result
                if puzzle is None:
                    return
                write(ROOT / 'grids' / f"{puzzle.data['name']}.json", puzzle.data)
            else:
                data = read(path or ROOT / 'grids' / f'{safe_name(name)}.json')
                puzzle = Puzzle(data['name'], data['rows'], data['cols'])
                puzzle.data = data
                if path and Path(path).resolve().parent.parent.name == 'saved states':
                    loaded_selection = load_snapshot(path, puzzle)
            for child in root.winfo_children():
                child.destroy()
            editor = Editor(root, puzzle)
            editor.selected = loaded_selection
            editor.redraw()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror('Cannot open puzzle', str(exc), parent=root)

    root.title('Jane Street · Puzzle launcher')
    root.geometry('490x270')
    frame = ttk.Frame(root, padding=28)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Grid puzzle editor', font=('Segoe UI', 20, 'bold')).pack(anchor='w', pady=(0, 12))
    ttk.Label(frame, text='Create a named puzzle or resume a working grid or snapshot.').pack(anchor='w', pady=(0, 18))
    ttk.Button(frame, text='Create new puzzle', command=lambda: open_puzzle(create=True)).pack(fill='x', pady=5)

    def choose():
        path = filedialog.askopenfilename(parent=root, initialdir=ROOT / 'grids', filetypes=[('Puzzle or saved state', '*.json')])
        if path:
            open_puzzle(path=path)

    ttk.Button(frame, text='Open puzzle or saved state…', command=choose).pack(fill='x', pady=5)
    if args.name:
        root.after(0, lambda: open_puzzle(name=args.name))
    root.mainloop()


if __name__ == '__main__':
    main()
