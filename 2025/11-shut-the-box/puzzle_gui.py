"""Tkinter entry point for the named grid puzzle editor."""
import sys
import queue
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog
from tkinter import font as tkfont
from functions.constants import CELL_SIZE, DEFAULT_ROWS, DEFAULT_COLUMNS, MODES
from functions.model import Puzzle, click_direction
from functions.storage import Storage
from functions.rendering import draw_canvas, export_png
from functions.placements import attempt_placements
from functions.dimensions import possible_dimension_totals
from functions.folding import folding_trials, largest_box_region, configured_anchor, face_name
from functions.fold_application import apply_unique_fold

ROOT = Path(__file__).resolve().parent


class Editor:
    def __init__(self, root, puzzle, storage):
        self.root, self.puzzle, self.storage = root, puzzle, storage
        root.title(f'{puzzle.name} — Puzzle editor')
        self.mode = tk.StringVar(value='Select')
        self.status = tk.StringVar(value='Ready. Select a cell to inspect it.')
        self.details = tk.StringVar()
        self.help = tk.StringVar()
        self.analysis_status = tk.StringVar()
        self.placement_status = tk.StringVar(value='Placement analysis idle.')
        self.placement_running = False
        self.dimension_running = False
        self.folding_running = False
        self.close_after_analysis = False
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
        self.placement_button = ttk.Button(side, text='Attempt placements', command=self.start_placements)
        self.placement_button.pack(fill='x', pady=3)
        self.dimension_button = ttk.Button(side, text='Determine valid box dimensions', command=self.determine_dimensions)
        self.dimension_button.pack(fill='x', pady=3)
        self.folding_button = ttk.Button(side, text='Try region folds', command=self.try_region_folds)
        self.folding_button.pack(fill='x', pady=3)
        self.abort_button = ttk.Button(side, text='Abort', command=self.abort_placements, state='disabled')
        self.abort_button.pack(fill='x', pady=3)
        ttk.Label(side, textvariable=self.placement_status, wraplength=270, justify='left').pack(anchor='w', pady=5)
        ttk.Label(side, textvariable=self.analysis_status,
                  wraplength=270, justify='left').pack(anchor='w')
        controls = ttk.Frame(outer)
        self.edit_controls = []
        controls.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(10, 0))
        for text, command in [('Save state', self.save_state), ('Load state', self.load_state),
                              ('Print state', lambda: self.save_state(printing=True)),
                              ('Undo', self.undo), ('Redo', self.redo),
                              ('Reset edits', self.reset), ('Reset shading', lambda: self.reset(True))]:
            button = ttk.Button(controls, text=text, command=command)
            button.pack(side='left', padx=(0, 5))
            self.edit_controls.append(button)
            if text == 'Undo': self.undo_button = button
            if text == 'Redo': self.redo_button = button
        ttk.Label(side, textvariable=self.status, wraplength=270, justify='left').pack(anchor='w', pady=(8, 0))
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
        if self.placement_running:
            for button in self.edit_controls:
                button.state(['disabled'])
        analysis = self.puzzle.analysis
        if analysis.conflicts:
            self.analysis_status.set(f'Contradiction ({len(analysis.conflicts)}):\n' + '\n'.join(analysis.conflicts[:3]))
        else:
            arrow_deduced = sum(source == 'arrow rules' for source in analysis.sources)
            number_deduced = sum(source == 'number rules' for source in analysis.sources)
            region_deduced = sum(source == 'region rules' for source in analysis.sources)
            unknown = sum(box is None for box in analysis.boxes)
            self.analysis_status.set(f'Arrow, number, and region rules updated automatically.\n'
                                     f'{arrow_deduced} arrow deductions; {number_deduced} number deductions.\n'
                                     f'{region_deduced} region deductions.\n'
                                     f'{unknown} unknown cells. No contradictions found.')
        if self.puzzle.selected is None:
            self.details.set('No cell selected.')
        else:
            index = self.puzzle.selected
            row, col = divmod(index, self.puzzle.columns)
            cell = self.puzzle.cells[index]
            self.details.set(f'Row {row + 1}, column {col + 1}\nDigit: {cell["digit"] if cell["digit"] is not None else "none"}\n'
                             f'Arrows: {", ".join(cell["arrows"]) or "none"}\nShape: {cell["shape"] or "none"}\n'
                             f'Box: {"unknown" if analysis.boxes[index] is None else "yes" if analysis.boxes[index] else "no"}\n'
                             f'Source: {analysis.sources[index]}')
            if cell['arrows'] and index in analysis.distances:
                candidates = ', '.join(map(str, analysis.distances[index])) or 'none'
                self.details.set(self.details.get() + f'\nPossible nearest distances: {candidates}')
            if index in analysis.numbers:
                count = analysis.numbers[index]
                self.details.set(self.details.get() + f'\nNumber count: {count.yes} yes, {count.unknown} unknown; '
                                 f'{count.target} required (including this cell).')
            if cell.get('face'):
                self.details.set(self.details.get() + f'\nFace: {cell["face"]}')

    def persist(self, text='Working puzzle saved.'):
        self.refresh()
        try:
            self.storage.save(self.puzzle)
            self.status.set(text)
        except (OSError, ValueError) as exc:
            self.status.set(f'Autosave failed: {exc}')
            messagebox.showerror('Save failed', str(exc), parent=self.root)

    def click(self, event, right=False):
        if self.placement_running: return
        self.canvas.focus_set()
        x, y = self.canvas.canvasx(event.x) - 3, self.canvas.canvasy(event.y) - 3
        row, col = int(y // CELL_SIZE), int(x // CELL_SIZE)
        if not (0 <= row < self.puzzle.rows and 0 <= col < self.puzzle.columns): return
        self.puzzle.selected = row * self.puzzle.columns + col
        direction = click_direction(x % CELL_SIZE, y % CELL_SIZE, CELL_SIZE)
        changed = self.puzzle.edit(self.puzzle.selected, self.mode.get(), 'right' if right else 'click', direction)
        self.persist('Edit saved.' if changed else 'Cell selected. Incompatible content is preserved.')

    def key(self, event):
        if self.placement_running: return 'break'
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
        if self.placement_running: return 'break'
        if self.puzzle.undo(): self.persist('Undo saved.')
        return 'break'

    def redo(self):
        if self.placement_running: return 'break'
        if self.puzzle.redo(): self.persist('Redo saved.')
        return 'break'

    def reset(self, shading_only=False):
        if self.placement_running: return
        if self.puzzle.reset(shading_only): self.persist('Shading reset.' if shading_only else 'Edits reset to original clues.')

    def save_state(self, printing=False):
        if self.placement_running: return
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
        if self.placement_running: return
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

    def start_placements(self):
        if self.placement_running or self.dimension_running or self.folding_running: return
        self.placement_running = True
        self.placement_started = time.perf_counter()
        self.placement_cancel = threading.Event()
        self.placement_messages = queue.Queue()
        self.placement_progress = 'Starting placement analysis'
        self.placement_button.state(['disabled'])
        self.dimension_button.state(['disabled'])
        self.folding_button.state(['disabled'])
        self.abort_button.state(['!disabled'])
        for button in self.edit_controls: button.state(['disabled'])
        cells = self.puzzle.to_dict()['cells']
        rows, columns = self.puzzle.rows, self.puzzle.columns
        def work():
            try:
                result = attempt_placements(cells, rows, columns,
                                            cancelled=self.placement_cancel.is_set,
                                            progress=lambda item: self.placement_messages.put(('progress', item)))
                self.placement_messages.put(('done', result))
            except Exception as exc:
                self.placement_messages.put(('error', str(exc)))
        threading.Thread(target=work, daemon=True).start()
        self.poll_placements()

    def abort_placements(self):
        if self.placement_running:
            self.placement_cancel.set()
            self.abort_button.state(['disabled'])
            self.placement_progress = 'Aborting placement analysis'

    def poll_placements(self):
        latest = None
        finished = None
        while True:
            try:
                kind, item = self.placement_messages.get_nowait()
            except queue.Empty:
                break
            if kind == 'progress': latest = item
            else: finished = (kind, item)
        elapsed = time.perf_counter() - self.placement_started
        if latest is not None and not self.placement_cancel.is_set():
            row, column = divmod(latest.index, self.puzzle.columns)
            assignment = 'forced placement found' if latest.assignment is None else 'testing in-box' if latest.assignment else 'testing out-box'
            self.placement_progress = f'Pass {latest.pass_number}, R{row + 1}C{column + 1}: {assignment}.\n{latest.forced} forced placements'
            self.puzzle.selected = latest.index
            self.refresh()
        if finished is None:
            self.placement_status.set(f'{self.placement_progress}\nElapsed: {elapsed:.1f}s')
            self.root.after(100, self.poll_placements)
            return
        self.placement_running = False
        self.placement_button.state(['!disabled'])
        self.dimension_button.state(['!disabled'])
        self.folding_button.state(['!disabled'])
        self.abort_button.state(['disabled'])
        for button in self.edit_controls: button.state(['!disabled'])
        kind, result = finished
        if kind == 'error':
            summary = f'Placement analysis failed: {result}'
            self.refresh()
        else:
            self.puzzle.apply_placements(result.cells)
            if result.status == 'contradiction':
                self.puzzle.selected = result.failed_cell
                row, column = divmod(result.failed_cell, self.puzzle.columns)
                summary = f'Contradiction: R{row + 1}C{column + 1} has no valid placements.'
                messagebox.showerror('No valid placements', summary + '\n\n' + '\n'.join(result.conflicts), parent=self.root)
            elif result.status == 'invalid':
                summary = 'Placement analysis stopped: the starting grid has contradictions.'
                messagebox.showerror('Starting grid is inconsistent', '\n'.join(result.conflicts), parent=self.root)
            elif result.status == 'cancelled':
                summary = 'Placement analysis aborted; earlier forced placements retained.'
            else:
                summary = 'Placement analysis complete: a full pass made no changes.'
            summary += f'\n{result.forced} forced placements; {result.tested} cells tested in {result.passes} passes.'
            self.persist('Placement results saved.')
        self.placement_status.set(f'{summary}\nElapsed: {elapsed:.1f}s')
        print(f'{summary.replace(chr(10), " ")} Elapsed: {elapsed:.1f}s')
        if self.close_after_analysis:
            self.close()

    def determine_dimensions(self):
        if self.placement_running or self.dimension_running or self.folding_running: return
        if self.puzzle.analysis.conflicts:
            messagebox.showerror('Grid is inconsistent', 'Resolve the current contradictions before determining dimensions.', parent=self.root)
            return
        in_box = sum(box is True for box in self.puzzle.analysis.boxes)
        unknown = sum(box is None for box in self.puzzle.analysis.boxes)
        totals = iter(possible_dimension_totals(in_box, unknown))
        self.dimension_running = True
        self.dimension_button.state(['disabled'])
        self.folding_button.state(['disabled'])
        self.placement_button.state(['disabled'])
        dialog = tk.Toplevel(self.root)
        dialog.title('Valid box dimensions — ' + self.puzzle.name)
        dialog.transient(self.root)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=12)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text=f'{in_box} confirmed in-box cells; {unknown} unknown cells.\n'
                            'Positive integers a ≥ b ≥ c; 2(ab + bc + ca) = box cells. Odd totals are skipped.').pack(anchor='w', pady=(0, 8))
        table_frame = ttk.Frame(body)
        table_frame.pack(fill='both', expand=True)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        table = ttk.Treeview(table_frame, columns=('added', 'cells', 'count', 'triples'), show='headings', height=14)
        result_font = tkfont.Font(root=dialog, font=ttk.Style(dialog).lookup('Treeview', 'font') or 'TkDefaultFont')
        for column, label, width in [('added', 'Unknown cells included', 155), ('cells', 'Box cells', 85),
                                     ('count', 'Triples', 70), ('triples', 'Dimensions (a, b, c)', 430)]:
            table.heading(column, text=label)
            table.column(column, width=width, minwidth=width, stretch=column == 'triples')
        table.grid(row=0, column=0, sticky='nsew')
        vertical = ttk.Scrollbar(table_frame, orient='vertical', command=table.yview)
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal = ttk.Scrollbar(table_frame, orient='horizontal', command=table.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        feedback = tk.StringVar()
        ttk.Label(body, textvariable=feedback, wraplength=740, justify='left').pack(anchor='w', pady=8)
        ttk.Label(body, text='These triples satisfy the cell-count formula; folding feasibility has not been tested.',
                  wraplength=740).pack(anchor='w')
        buttons = ttk.Frame(body)
        buttons.pack(anchor='e', pady=(8, 0))
        started = time.perf_counter()
        checked = matches = viable_totals = 0
        pending = None
        def finish(cancelled=False):
            nonlocal pending
            if pending is not None:
                dialog.after_cancel(pending)
                pending = None
            self.dimension_running = False
            self.dimension_button.state(['!disabled'])
            self.folding_button.state(['!disabled'])
            self.placement_button.state(['!disabled'])
            abort.state(['disabled'])
            outcome = 'Aborted; results are incomplete.' if cancelled else 'Complete.'
            feedback.set(f'{outcome} {checked} even totals checked; {viable_totals} totals with matches; '
                         f'{matches} dimension triples.\nElapsed: {time.perf_counter() - started:.1f}s')
        def close_dialog():
            if self.dimension_running: finish(True)
            dialog.destroy()
        abort = ttk.Button(buttons, text='Abort', command=lambda: finish(True))
        abort.pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text='Close', command=close_dialog).pack(side='left')
        dialog.protocol('WM_DELETE_WINDOW', close_dialog)
        def step():
            nonlocal checked, matches, viable_totals, pending
            pending = None
            try:
                result = next(totals)
            except StopIteration:
                finish()
                return
            checked += 1
            matches += len(result.triples)
            viable_totals += bool(result.triples)
            text = '; '.join(f'({a}, {b}, {c})' for a, b, c in result.triples) or 'None'
            table.insert('', 'end', values=(result.added_unknown, result.cells, len(result.triples), text))
            needed = max(430, result_font.measure(text) + 24)
            if needed > table.column('triples', 'width'):
                table.column('triples', width=needed)
            feedback.set(f'Checking {result.cells} box cells ({result.added_unknown} unknown cells included).\n'
                         f'Elapsed: {time.perf_counter() - started:.1f}s')
            pending = dialog.after(1, step)
        pending = dialog.after(1, step)

    def try_region_folds(self):
        if self.placement_running or self.dimension_running or self.folding_running: return
        if self.puzzle.analysis.conflicts:
            messagebox.showerror('Grid is inconsistent', 'Resolve the current contradictions before testing folds.', parent=self.root)
            return
        try:
            anchor = configured_anchor(self.storage.load_configuration(self.puzzle.name), self.puzzle.selected,
                                       self.puzzle.rows, self.puzzle.columns)
            boxes = self.puzzle.analysis.boxes.copy()
            region = largest_box_region(boxes, self.puzzle.rows, self.puzzle.columns)
            if anchor not in region:
                raise ValueError('The anchor must be a confirmed box cell in the largest region.')
        except (OSError, ValueError) as exc:
            messagebox.showerror('Cannot test folds', str(exc), parent=self.root)
            return
        trials = iter(folding_trials(boxes, self.puzzle.rows, self.puzzle.columns, anchor, self.puzzle.cells))
        self.folding_running = True
        for button in (self.folding_button, self.dimension_button, self.placement_button): button.state(['disabled'])
        dialog = tk.Toplevel(self.root)
        dialog.title('Region fold trials — ' + self.puzzle.name)
        dialog.transient(self.root)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=12)
        body.pack(fill='both', expand=True)
        row, column = divmod(anchor, self.puzzle.columns)
        ttk.Label(body, text=f'Largest confirmed box region: {len(region)} cells. Anchor: R{row + 1}C{column + 1}.\n'
                            'Testing every candidate box surface cell in four rotations; all region adjacencies remain uncut.').pack(anchor='w', pady=(0, 8))
        frame = ttk.Frame(body)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        table = ttk.Treeview(frame, columns=('dimensions', 'face', 'position', 'rotation'), show='headings', height=12)
        for key, label, width in [('dimensions', 'Dimensions (a,b,c)', 170), ('face', 'Anchor face', 100),
                                  ('position', 'Anchor center (x,y,z)', 230), ('rotation', 'Rotation', 100)]:
            table.heading(key, text=label)
            table.column(key, width=width)
        table.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(frame, orient='vertical', command=table.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        table.configure(yscrollcommand=scroll.set)
        feedback = tk.StringVar(value='Starting fold trials…')
        ttk.Label(body, textvariable=feedback, wraplength=700, justify='left').pack(anchor='w', pady=8)
        ttk.Label(body, text='Surviving trials fill the surface. A unique result is applied to the grid. Circle/square pairing rules are not checked.',
                  wraplength=700, justify='left').pack(anchor='w')
        buttons = ttk.Frame(body)
        buttons.pack(anchor='e', pady=(8, 0))
        survivors = []
        rejected = {'isolated anchor': 0, 'overlap': 0, 'severed connection': 0}
        checked = 0
        pending = None
        started = time.perf_counter()
        def view_mapping():
            if table.selection():
                trial = survivors[int(table.selection()[0])]
                self.show_fold_mapping(dialog, trial, anchor)
        view = ttk.Button(buttons, text='View cell mapping', command=view_mapping)
        view.pack(side='left', padx=(0, 8))
        table.bind('<Double-Button-1>', lambda event: view_mapping())
        def finish(cancelled=False):
            nonlocal pending
            if pending is not None:
                dialog.after_cancel(pending)
                pending = None
            self.folding_running = False
            for button in (self.folding_button, self.dimension_button, self.placement_button): button.state(['!disabled'])
            abort.state(['disabled'])
            outcome = 'Aborted; results are incomplete.' if cancelled else 'Complete.'
            summary = (f'{outcome} {checked} trials; {len(survivors)} surviving placements.\n'
                       f'Rejected: {rejected["isolated anchor"]} isolated anchors, {rejected["overlap"]} overlaps, '
                       f'{rejected["severed connection"]} severed connections.\n'
                       f'Elapsed: {time.perf_counter() - started:.1f}s')
            feedback.set(summary)
            if not cancelled and len(survivors) == 1:
                try:
                    if apply_unique_fold(self.puzzle, survivors):
                        self.persist('Unique fold applied.')
                    feedback.set(summary + '\nUnique fold applied to the grid with face colors.')
                except ValueError as exc:
                    feedback.set(summary + f'\nCould not apply fold: {exc}')
            print(summary.replace('\n', ' '))
        def close_dialog():
            if self.folding_running: finish(True)
            dialog.destroy()
        abort = ttk.Button(buttons, text='Abort', command=lambda: finish(True))
        abort.pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text='Close', command=close_dialog).pack(side='left')
        dialog.protocol('WM_DELETE_WINDOW', close_dialog)
        def step():
            nonlocal pending, checked
            pending = None
            deadline = time.perf_counter() + .01
            trial = None
            while time.perf_counter() < deadline:
                try:
                    trial = next(trials)
                except StopIteration:
                    finish()
                    return
                checked += 1
                if trial.reason:
                    rejected[trial.reason] = rejected.get(trial.reason, 0) + 1
                else:
                    identity = str(len(survivors))
                    survivors.append(trial)
                    table.insert('', 'end', iid=identity, values=(str(trial.dimensions), face_name(trial.anchor),
                                 str(tuple(value / 2 for value in trial.anchor.center)), f'{trial.rotation * 90}°'))
                    if not table.selection(): table.selection_set(identity)
            if trial is not None:
                feedback.set(f'Testing {trial.dimensions}, face {face_name(trial.anchor)}, rotation {trial.rotation * 90}°.\n'
                             f'{checked} trials; {len(survivors)} surviving placements. Elapsed: {time.perf_counter() - started:.1f}s')
            pending = dialog.after(1, step)
        pending = dialog.after(1, step)

    def show_fold_mapping(self, parent, trial, anchor):
        dialog = tk.Toplevel(parent)
        dialog.title(f'Cell mapping — {trial.dimensions}, rotation {trial.rotation * 90}°')
        dialog.transient(parent)
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill='both', expand=True)
        table = ttk.Treeview(frame, columns=('grid', 'face', 'position'), show='headings', height=18)
        for key, label, width in [('grid', 'Grid cell', 130), ('face', 'Face', 75), ('position', 'Surface center (x,y,z)', 250)]:
            table.heading(key, text=label)
            table.column(key, width=width)
        table.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=table.yview)
        scroll.pack(side='right', fill='y')
        table.configure(yscrollcommand=scroll.set)
        for index, placement in sorted(trial.mapping.items()):
            row, column = divmod(index, self.puzzle.columns)
            table.insert('', 'end', values=(f'R{row + 1}C{column + 1}' + (' (anchor)' if index == anchor else ''),
                         face_name(placement.cell), str(tuple(value / 2 for value in placement.cell.center))))

    def close(self):
        if self.placement_running:
            self.close_after_analysis = True
            self.abort_placements()
            return
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

