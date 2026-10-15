"""Launch the named grid editor: python puzzle_gui.py [name]."""
import argparse
import copy
from time import perf_counter
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog
from pathlib import Path

from functions.constants import CELL_SIZE, MARGIN, COLORS, MODES, COLOR_KEYPAD
from functions.model import Puzzle, safe_name, read, write, save_snapshot, load_snapshot
from functions.rendering import draw, export_png
from functions.state_export import print_state as export_state
from functions.analysis_workflow import apply_analysis, analysis_summary
from functions.answer_key import compute_answer_key
from functions.display_state import displayed_entries
from functions.hooks import HookSearch
from functions.pentominoes import PentominoSearch, RemainingPentominoSearch, analysis_records

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
        self.search = None
        self.search_callback = None
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
        self.details_text = tk.Text(panel, width=32, height=7, wrap='word', font=('Segoe UI', 9),
                                    relief='flat', background=root.cget('background'), state='disabled')
        self.details_text.pack(anchor='w', pady=(12, 10))
        ttk.Label(panel, text='Analysis', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        analysis_tabs = ttk.Notebook(panel)
        analysis_tabs.pack(anchor='w', fill='x', pady=6)
        hook_tab, pentomino_tab = ttk.Frame(analysis_tabs), ttk.Frame(analysis_tabs)
        analysis_tabs.add(hook_tab, text='Hooks')
        analysis_tabs.add(pentomino_tab, text='Pentominoes')
        answer_tab = ttk.Frame(analysis_tabs)
        analysis_tabs.add(answer_tab, text='Answer key')
        self.answer_button = ttk.Button(answer_tab, text='Generate answer key', command=self.generate_answer_key)
        self.answer_button.pack(anchor='w', pady=8)
        ttk.Label(answer_tab, text='Uses the displayed grid, including the selected preview.',
                  wraplength=245, justify='left').pack(anchor='w', pady=5)
        self.answer_text = tk.Text(answer_tab, width=30, height=8, wrap='word', state='disabled', font=('Segoe UI',9))
        self.answer_text.pack(fill='both', expand=True, pady=5)
        self.answer_source = None
        analysis_controls = ttk.Frame(hook_tab)
        analysis_controls.pack(anchor='w', pady=6)
        self.draw_hooks_button = ttk.Button(analysis_controls, text='Draw hooks', command=self.draw_hooks)
        self.draw_hooks_button.grid(row=0, column=0, padx=(0, 5), pady=3)
        self.abort_button = ttk.Button(analysis_controls, text='Abort', command=self.abort_hooks, state='disabled')
        self.abort_button.grid(row=0, column=1, pady=3)
        ttk.Button(analysis_controls, text='Previous', command=lambda: self.navigate_hooks(-1)).grid(row=1, column=0, pady=3)
        ttk.Button(analysis_controls, text='Next', command=lambda: self.navigate_hooks(1)).grid(row=1, column=1, pady=3)
        ttk.Button(analysis_controls, text='Confirmed view', command=self.confirmed_hooks).grid(row=2, column=0, pady=3)
        ttk.Button(analysis_controls, text='Use hooks', command=self.use_hooks).grid(row=2, column=1, pady=3)
        self.analysis_status = tk.StringVar(value='Ready to draw hooks from the 1-clue.')
        ttk.Label(hook_tab, textvariable=self.analysis_status, wraplength=245, justify='left').pack(anchor='w', pady=6)
        pentomino_controls = ttk.Frame(pentomino_tab)
        pentomino_controls.pack(anchor='w', pady=6)
        self.draw_pentominoes_button = ttk.Button(pentomino_controls, text='Draw pentominoes', command=self.draw_pentominoes)
        self.draw_pentominoes_button.grid(row=0, column=0, padx=(0, 5), pady=3)
        self.pentomino_abort_button = ttk.Button(pentomino_controls, text='Abort', command=self.abort_hooks, state='disabled')
        self.pentomino_abort_button.grid(row=0, column=1, pady=3)
        self.pentomino_view = tk.StringVar(value='Combinations')
        view_selector = ttk.Combobox(pentomino_controls, textvariable=self.pentomino_view,
                                    values=('Combinations', 'Individual placements', 'Three additional pentominoes'), state='readonly', width=28)
        view_selector.grid(row=1, column=0, columnspan=2, sticky='ew', pady=4)
        view_selector.bind('<<ComboboxSelected>>', self.change_pentomino_view)
        ttk.Button(pentomino_controls, text='Previous', command=lambda: self.navigate_pentominoes(-1)).grid(row=2, column=0, pady=3)
        ttk.Button(pentomino_controls, text='Next', command=lambda: self.navigate_pentominoes(1)).grid(row=2, column=1, pady=3)
        ttk.Button(pentomino_controls, text='Confirmed view', command=self.confirmed_pentominoes).grid(row=3, column=0, columnspan=2, sticky='ew', pady=3)
        self.draw_remaining_button = ttk.Button(pentomino_controls, text='Draw remaining pentominoes', command=self.draw_remaining_pentominoes)
        self.draw_remaining_button.grid(row=4, column=0, columnspan=2, sticky='ew', pady=3)
        self.pentomino_status = tk.StringVar(value='Draw hooks first, then test the outside pentomino clues.')
        ttk.Label(pentomino_tab, textvariable=self.pentomino_status, wraplength=245, justify='left').pack(anchor='w', pady=6)
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
        if self.answer_source is not None and self.answer_source != displayed_entries(self.puzzle.data):
            self.show_answer_text('The displayed digits changed. Generate the answer key again.')
            self.answer_source = None
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
        self.details_text.configure(state='normal')
        self.details_text.delete('1.0', 'end')
        self.details_text.insert('1.0', self.details.get())
        self.details_text.configure(state='disabled')
        if self.search is None:
            self.update_analysis_status()
            self.update_pentomino_status()

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
        if self.search is not None:
            self.search.cancelled = True
            self.search_discard = True
        self.persist()
        self.redraw()

    def draw_hooks(self):
        if self.search is not None:
            return
        try:
            self.search = HookSearch(copy.deepcopy(self.puzzle.data))
        except ValueError as exc:
            self.analysis_status.set(str(exc))
            return
        self.start_analysis('hooks')

    def draw_pentominoes(self):
        if self.search is not None:
            return
        try:
            self.search = PentominoSearch(copy.deepcopy(self.puzzle.data))
        except ValueError as exc:
            self.pentomino_status.set(str(exc))
            return
        self.start_analysis('pentominoes')

    def start_analysis(self, kind):
        self.search_kind = kind
        self.search_started = perf_counter()
        self.search_discard = False
        self.search_steps = self.search.run()
        self.draw_hooks_button.configure(state='disabled')
        self.draw_pentominoes_button.configure(state='disabled')
        self.draw_remaining_button.configure(state='disabled')
        self.answer_button.configure(state='disabled')
        self.abort_button.configure(state='normal')
        self.pentomino_abort_button.configure(state='normal')
        target = self.analysis_status if kind == 'hooks' else self.pentomino_status
        target.set('Drawing hooks · size 1 · 0.0 s' if kind == 'hooks' else 'Preparing pentominoes · 0.0 s')
        self.search_callback = self.root.after(1, self.advance_hooks)

    def finish_analysis_controls(self):
        self.draw_hooks_button.configure(state='normal')
        self.draw_pentominoes_button.configure(state='normal')
        self.draw_remaining_button.configure(state='normal')
        self.answer_button.configure(state='normal')
        self.abort_button.configure(state='disabled')
        self.pentomino_abort_button.configure(state='disabled')

    def advance_hooks(self):
        self.search_callback = None
        deadline = perf_counter() + 0.012
        try:
            while perf_counter() < deadline:
                next(self.search_steps)
        except StopIteration:
            search = self.search
            elapsed = perf_counter() - self.search_started
            self.search = None
            self.finish_analysis_controls()
            target = self.analysis_status if self.search_kind == 'hooks' else self.pentomino_status
            if self.search_discard:
                target.set(f'Cancelled because puzzle state changed · {elapsed:.2f} s')
            else:
                apply_analysis(self.puzzle, self.search_kind, search, elapsed)
                self.changed()
                print(analysis_summary(self.search_kind, search, elapsed))
            return
        except Exception as exc:
            elapsed = perf_counter() - self.search_started
            self.search = None
            self.finish_analysis_controls()
            target = self.analysis_status if self.search_kind == 'hooks' else self.pentomino_status
            target.set(f'{self.search_kind.capitalize()} search failed · {elapsed:.2f} s\n{exc}')
            return
        elapsed = perf_counter() - self.search_started
        if self.search_kind == 'hooks':
            self.analysis_status.set(f'Drawing hooks · size {self.search.size}\n{self.search.nodes:,} branches · {len(self.search.candidates)} layouts · {elapsed:.1f} s')
        else:
            self.pentomino_status.set(f'{self.search.progress}\n{len(self.search.placements)} placements · {len(self.search.candidates)} combinations\n{self.search.nodes:,} branches · {elapsed:.1f} s')
        self.search_callback = self.root.after(1, self.advance_hooks)

    def abort_hooks(self):
        if self.search is not None:
            self.search.cancelled = True

    def update_analysis_status(self):
        analysis = self.puzzle.data.get('analysis')
        if analysis is None:
            self.analysis_status.set('Ready to draw hooks from the 1-clue.')
            return
        count = len(analysis['candidates'])
        outcome = {'complete': 'Complete', 'cancelled': 'Cancelled — incomplete', 'limit': 'Search limit — incomplete'}[analysis['outcome']]
        result = f'{count} layouts' if count or analysis['outcome'] != 'complete' else 'No compatible layouts'
        preview = analysis['preview']
        view = f'Preview {preview+1}/{count} (purple)' if preview >= 0 else 'Confirmed view'
        canonical_count = len(analysis.get('canonical_borders', {}))
        self.analysis_status.set(f"{outcome} · {result}\n{analysis['elapsed']:.2f} s · {analysis['nodes']:,} branches\n{canonical_count} canonical borders · {view}")

    def navigate_hooks(self, direction):
        analysis = self.puzzle.data.get('analysis')
        if self.search is None and analysis and analysis['candidates']:
            index = analysis['preview']
            index = (0 if direction > 0 else len(analysis['candidates'])-1) if index < 0 else (index+direction) % len(analysis['candidates'])
            self.puzzle.preview_hooks(index)
            self.persist()
            self.redraw()

    def confirmed_hooks(self):
        if self.search is None:
            self.puzzle.preview_hooks(-1)
            self.persist()
            self.redraw()

    def use_hooks(self):
        if self.search is None:
            self.puzzle.use_hook_preview()
            self.changed()

    def update_pentomino_status(self):
        analysis = self.puzzle.data.get('pentomino_analysis')
        if analysis is None:
            self.pentomino_status.set('Draw hooks first, then test the outside pentomino clues.')
            return
        outcome = {'complete': 'Complete', 'cancelled': 'Cancelled — incomplete', 'limit': 'Search limit — incomplete'}[analysis['outcome']]
        view = analysis['view']
        self.pentomino_view.set({'combinations':'Combinations', 'placements':'Individual placements', 'extensions':'Three additional pentominoes'}[view])
        records = analysis_records(analysis)
        index = analysis['preview']
        preview = 'Confirmed view' if index < 0 else f'Preview {index+1}/{len(records)} · hook layout {records[index]["hook_index"]+1}'
        source_note = '\nInput hook layouts are incomplete.' if analysis.get('source_incomplete') else ''
        discarded = analysis.get('discarded_hook_layouts', 0)
        if view == 'extensions' and 'remaining_outcome' in analysis:
            outcome = {'complete':'Complete', 'cancelled':'Cancelled — incomplete', 'limit':'Search limit — incomplete'}[analysis['remaining_outcome']]
            input_note = '\nInput combinations are incomplete.' if analysis.get('remaining_source_incomplete') else ''
            self.pentomino_status.set(f"{outcome}{input_note}\n{len(analysis.get('extensions',[]))} three-piece extensions\n{analysis.get('discarded_combinations',0)} combinations discarded · {discarded} hook layouts discarded\n{analysis['remaining_elapsed']:.2f} s · {analysis['remaining_nodes']:,} branches\n{preview}")
        else:
            self.pentomino_status.set(f"{outcome}{source_note}\n{len(analysis['placements'])} individual placements · {len(analysis['candidates'])} compatible combinations\n{discarded} hook layouts discarded\n{analysis['elapsed']:.2f} s · {analysis['nodes']:,} branches\n{preview}")

    def change_pentomino_view(self, event=None):
        if self.search is None:
            analysis = self.puzzle.data.get('pentomino_analysis')
            if analysis:
                view = {'Combinations':'combinations', 'Individual placements':'placements', 'Three additional pentominoes':'extensions'}[self.pentomino_view.get()]
                records = analysis_records(analysis, view)
                self.puzzle.preview_pentominoes(0 if records else -1, view)
                self.persist()
                self.redraw()

    def navigate_pentominoes(self, direction):
        analysis = self.puzzle.data.get('pentomino_analysis')
        if self.search is None and analysis:
            records = analysis_records(analysis)
            if records:
                index = analysis['preview']
                index = (0 if direction > 0 else len(records)-1) if index < 0 else (index+direction) % len(records)
                self.puzzle.preview_pentominoes(index)
                self.persist()
                self.redraw()

    def confirmed_pentominoes(self):
        if self.search is None:
            self.puzzle.preview_pentominoes(-1)
            self.puzzle.preview_hooks(-1)
            self.persist()
            self.redraw()

    def draw_remaining_pentominoes(self):
        if self.search is not None:
            return
        try:
            self.search = RemainingPentominoSearch(copy.deepcopy(self.puzzle.data))
        except ValueError as exc:
            self.pentomino_status.set(str(exc))
            return
        self.start_analysis('remaining pentominoes')

    def show_answer_text(self, text):
        self.answer_text.configure(state='normal')
        self.answer_text.delete('1.0','end')
        self.answer_text.insert('1.0',text)
        self.answer_text.configure(state='disabled')

    def generate_answer_key(self):
        if self.search is not None:
            self.show_answer_text('Wait for the current analysis to finish.')
            return
        try:
            answer = compute_answer_key(self.puzzle.data)
        except ValueError as exc:
            self.show_answer_text(f'Answer key unavailable: {exc}')
            self.answer_source = None
        else:
            self.show_answer_text(answer.report())
            self.answer_source = displayed_entries(self.puzzle.data)
            print(answer.report())

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
                export_state(self.puzzle, ROOT, name, self.selected)
            else:
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
            if self.search_callback is not None:
                self.root.after_cancel(self.search_callback)
            if self.search is not None:
                self.search.cancelled = True
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
