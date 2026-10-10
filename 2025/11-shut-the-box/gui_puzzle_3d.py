"""Interactive 3D viewer for surviving region folds of a named puzzle."""
import sys
import time
from math import pi
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import ImageTk
from functions.storage import Storage
from functions.folding import folding_trials, configured_anchor, largest_box_region, face_name
from functions.view3d import render_fold, pick_cell

ROOT = Path(__file__).resolve().parent


class FoldViewer:
    def __init__(self, root, puzzle, storage):
        self.root, self.puzzle = root, puzzle
        if puzzle.analysis.conflicts:
            raise ValueError('Resolve the grid contradictions before viewing folds.')
        self.anchor = configured_anchor(storage.load_configuration(puzzle.name), puzzle.selected, puzzle.rows, puzzle.columns)
        region = largest_box_region(puzzle.analysis.boxes, puzzle.rows, puzzle.columns)
        if self.anchor not in region:
            raise ValueError('The anchor must belong to the largest confirmed box region.')
        root.title(puzzle.name + ' — 3D region folds')
        root.geometry('1100x800')
        root.minsize(800, 600)
        self.trials = iter(folding_trials(puzzle.analysis.boxes.copy(), puzzle.rows, puzzle.columns, self.anchor, puzzle.cells))
        self.candidates, self.current = [], 0
        self.yaw, self.pitch, self.zoom = -.55, .45, 1
        self.selected = None
        self.projected = []
        self.pending = self.draw_pending = None
        self.running = True
        self.checked = 0
        self.started = time.perf_counter()
        self.drag = None
        self.moved = False
        self.coordinates = tk.BooleanVar(value=False)
        self.separation = tk.DoubleVar(value=0)
        self.summary, self.progress, self.details = (tk.StringVar() for _ in range(3))
        outer = ttk.Frame(root, padding=12)
        outer.pack(fill='both', expand=True)
        toolbar = ttk.Frame(outer)
        toolbar.pack(fill='x')
        self.previous = ttk.Button(toolbar, text='Previous fold', command=lambda: self.navigate(-1))
        self.previous.pack(side='left')
        self.next = ttk.Button(toolbar, text='Next fold', command=lambda: self.navigate(1))
        self.next.pack(side='left', padx=6)
        ttk.Button(toolbar, text='Reset view', command=self.reset_view).pack(side='left', padx=6)
        ttk.Checkbutton(toolbar, text='Grid coordinates', variable=self.coordinates, command=self.schedule_draw).pack(side='left')
        ttk.Label(toolbar, text='Separate faces').pack(side='left', padx=(14, 5))
        ttk.Scale(toolbar, from_=0, to=3, variable=self.separation, command=lambda value: self.schedule_draw()).pack(side='left', fill='x', expand=True)
        self.abort = ttk.Button(toolbar, text='Abort search', command=self.stop_search)
        self.abort.pack(side='right', padx=6)
        ttk.Label(outer, textvariable=self.summary, wraplength=1000, justify='left').pack(anchor='w', pady=8)
        body = ttk.Frame(outer)
        body.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(body, background='#f6f8fb', highlightthickness=0)
        self.canvas.pack(side='left', fill='both', expand=True)
        side = ttk.Frame(body, padding=(12, 0, 0, 0))
        side.pack(side='right', fill='y')
        ttk.Label(side, text='Look at a face').pack(anchor='w')
        views = [('+X', -pi/2, 0), ('-X', pi/2, 0), ('+Y', 0, pi/2), ('-Y', 0, -pi/2), ('+Z', 0, 0), ('-Z', pi, 0)]
        for label, yaw, pitch in views:
            ttk.Button(side, text=label, command=lambda y=yaw, p=pitch: self.set_view(y, p)).pack(fill='x', pady=2)
        ttk.Label(side, text='Drag to rotate.\nMouse wheel to zoom.\nClick a cell to inspect it.\n\nGreen: mapped region\nBlue: anchor\nGrey: uncovered surface', wraplength=220, justify='left').pack(anchor='w', pady=12)
        ttk.Label(side, textvariable=self.details, wraplength=220, justify='left').pack(anchor='w')
        ttk.Label(side, textvariable=self.progress, wraplength=220, justify='left').pack(anchor='w', pady=12)
        ttk.Label(side, text='Surface-complete placements. Circle/square pairing rules are not checked.', wraplength=220, justify='left').pack(anchor='w')
        self.canvas.bind('<Configure>', lambda event: self.schedule_draw())
        self.canvas.bind('<ButtonPress-1>', self.press)
        self.canvas.bind('<B1-Motion>', self.motion)
        self.canvas.bind('<ButtonRelease-1>', self.release)
        self.canvas.bind('<MouseWheel>', self.wheel)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.update_controls()
        self.pending = root.after(1, self.search_step)

    def search_step(self):
        self.pending = None
        deadline = time.perf_counter() + .015
        while time.perf_counter() < deadline:
            try:
                trial = next(self.trials)
            except StopIteration:
                self.stop_search(complete=True)
                return
            self.checked += 1
            if trial.reason is None:
                self.candidates.append(trial)
                if len(self.candidates) == 1: self.schedule_draw()
                self.update_controls()
        self.progress.set(f'Searching: {self.checked} trials\n{len(self.candidates)} surviving folds\nElapsed: {time.perf_counter()-self.started:.1f}s')
        self.pending = self.root.after(1, self.search_step)

    def stop_search(self, complete=False):
        if self.pending is not None:
            self.root.after_cancel(self.pending)
            self.pending = None
        self.running = False
        self.abort.state(['disabled'])
        outcome = 'Search complete' if complete else 'Search aborted; incomplete results'
        self.progress.set(f'{outcome}\n{self.checked} trials\n{len(self.candidates)} surviving folds\nElapsed: {time.perf_counter()-self.started:.1f}s')
        if not self.candidates:
            self.summary.set('No surviving folds found.' if complete else 'No surviving folds found before cancellation.')
        self.update_controls()

    def update_controls(self):
        self.previous.state(['disabled'] if self.current == 0 else ['!disabled'])
        self.next.state(['disabled'] if self.current + 1 >= len(self.candidates) else ['!disabled'])
        if self.candidates:
            trial = self.candidates[self.current]
            row, col = divmod(self.anchor, self.puzzle.columns)
            self.summary.set(f'Fold {self.current+1} of {len(self.candidates)} · dimensions {trial.dimensions} · '
                             f'R{row+1}C{col+1} on {face_name(trial.anchor)} at '
                             f'{tuple(v/2 for v in trial.anchor.center)} · rotation {trial.rotation*90}° · '
                             f'{len(trial.mapping)} mapped cells')

    def navigate(self, delta):
        if self.candidates:
            self.current = max(0, min(len(self.candidates)-1, self.current+delta))
            self.selected = None
            self.details.set('')
            self.update_controls()
            self.schedule_draw()

    def reset_view(self):
        self.yaw, self.pitch, self.zoom = -.55, .45, 1
        self.separation.set(0)
        self.schedule_draw()

    def set_view(self, yaw, pitch):
        self.yaw, self.pitch = yaw, pitch
        self.schedule_draw()

    def schedule_draw(self):
        if self.draw_pending is None:
            self.draw_pending = self.root.after_idle(self.draw)

    def draw(self):
        self.draw_pending = None
        if not self.candidates: return
        image, self.projected = render_fold(self.candidates[self.current], self.puzzle.cells,
                        self.puzzle.columns, self.anchor, max(1, self.canvas.winfo_width()),
                        max(1, self.canvas.winfo_height()), self.yaw, self.pitch, self.zoom,
                        self.separation.get(), self.coordinates.get(), self.selected)
        self.image = ImageTk.PhotoImage(image, master=self.canvas)
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, image=self.image, anchor='nw')

    def press(self, event):
        self.drag = (event.x, event.y)
        self.moved = False

    def motion(self, event):
        if self.drag is None: return
        dx, dy = event.x-self.drag[0], event.y-self.drag[1]
        self.yaw += dx * .01
        self.pitch = max(-pi/2, min(pi/2, self.pitch + dy * .01))
        self.drag = (event.x, event.y)
        self.moved = True
        self.schedule_draw()

    def release(self, event):
        self.drag = None
        if self.moved: return
        item = pick_cell(self.projected, (event.x, event.y))
        if item is None: return
        self.selected = item.surface
        details = f'Face: {face_name(item.surface)}\nCenter: {tuple(v/2 for v in item.surface.center)}'
        if item.index is None:
            details += '\nNot covered by this region.'
        else:
            row, col = divmod(item.index, self.puzzle.columns)
            cell = self.puzzle.cells[item.index]
            details += f'\nGrid: R{row+1}C{col+1}\nDigit: {cell["digit"] if cell["digit"] is not None else "none"}\nShape: {cell["shape"] or "none"}'
        self.details.set(details)
        self.schedule_draw()

    def wheel(self, event):
        self.zoom = max(.25, min(4, self.zoom * (1.12 if event.delta > 0 else 1/1.12)))
        self.schedule_draw()

    def close(self):
        if self.pending is not None: self.root.after_cancel(self.pending)
        if self.draw_pending is not None: self.root.after_cancel(self.draw_pending)
        self.root.destroy()


def main():
    if len(sys.argv) > 2: raise SystemExit('Usage: python gui_puzzle_3d.py [name]')
    root = tk.Tk()
    storage = Storage(ROOT)
    def open_puzzle(name, launcher=None):
        try:
            puzzle = storage.load(storage.working_path(name), name)
            configuration = storage.load_configuration(name)
            anchor = configured_anchor(configuration, puzzle.selected, puzzle.rows, puzzle.columns)
            if puzzle.analysis.conflicts: raise ValueError('Resolve grid contradictions first.')
            if anchor not in largest_box_region(puzzle.analysis.boxes, puzzle.rows, puzzle.columns):
                raise ValueError('The anchor must belong to the largest confirmed box region.')
        except (OSError, ValueError) as exc:
            messagebox.showerror('Cannot open 3D viewer', str(exc), parent=root)
            return False
        if launcher is not None: launcher.destroy()
        FoldViewer(root, puzzle, storage)
        return True
    if len(sys.argv) == 2:
        if not open_puzzle(sys.argv[1]):
            root.destroy()
            raise SystemExit(1)
    else:
        root.title('3D puzzle launcher')
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Choose a named puzzle to view its surviving folds.').pack(pady=(0, 10))
        names = [path.stem for path in storage.puzzles()]
        name = tk.StringVar(value=names[0] if names else '')
        ttk.Combobox(frame, values=names, textvariable=name, state='readonly', width=35).pack()
        ttk.Button(frame, text='Open 3D viewer', command=lambda: open_puzzle(name.get(), frame)).pack(pady=(12, 0))
    root.mainloop()


if __name__ == '__main__':
    main()
