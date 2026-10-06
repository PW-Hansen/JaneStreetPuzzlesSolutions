"""Interactive expression grid. Run with: python puzzle_gui.py"""

import argparse
import tkinter as tk
import threading
from copy import deepcopy
from datetime import datetime
from queue import Queue, Empty
from fractions import Fraction
from pathlib import Path
from tkinter import font as tkfont, messagebox, simpledialog, ttk

from functions.solve_functions import (
    BackgroundRegionOperation, analyze_grid, candidate_labels, completed_regions,
    elapsed_text, included_expressions, make_overlay_snapshot, overlay_board,
)


from functions.persistence_functions import (
    grid_name, read_state, write_state, migrate_example,
    make_grid_state, make_saved_state, load_snapshot
)

from functions.equations_functions import (
    variable_name,
    clue_variables,
    evaluate
)

from functions.display_functions import (
    format_candidates,
    region_colors,
    grid_picture,
    fraction_parts,
    inline_math,
    math_runs,
    math_width,
    draw_math
)

from functions.region_functions import (
    max_region_size,
    check_grid_connectivity,
    find_region_overlays,
    compare_incomplete_regions,
    attempt_region_completions,
    continue_region_overlays
)


DATA_DIRECTORY = Path(__file__).resolve().parent / "grids"
MIN_CELL_SIZE = 40


def prepare_grid(root, name, size=None):
    migrate_example()
    path = DATA_DIRECTORY / f"{name}.json"
    if not path.exists():
        if size is None:
            size = simpledialog.askinteger("New grid", f"Size for '{name}' (number of rows and columns):",
                                           parent=root, minvalue=1)
        if size is None:
            return None
        state = {"size": size, "expressions": [[""] * size for _ in range(size)],
                 "show_values": False}
    else:
        state = read_state(path)
    if "variables" not in state:
        count = simpledialog.askinteger("Grid variables", f"Number of variables for '{name}':",
                                        parent=root, minvalue=0)
        if count is None:
            return None
        state["variables"] = {variable_name(i): "1" for i in range(count)}
        write_state(path, state)
    # Validate before opening an editable grid so a damaged save isn't overwritten.
    read_state(path)
    return path


def launcher_states():
    """List autosaved grids and named snapshots without changing their files."""
    result = [(f'{path.stem} (grid)',path.stem,path,False)
              for path in sorted(DATA_DIRECTORY.glob('*.json'))]
    folder = Path(__file__).resolve().parent / 'saved states'
    result.extend((f'{path.parent.name} / {path.stem}',path.parent.name,path,True)
                  for path in sorted(folder.glob('*/*.json')))
    return result


def choose_grid(root):
    migrate_example()
    dialog = tk.Toplevel(root)
    dialog.title("Open puzzle grid")
    dialog.resizable(False,False)
    result = []
    create = ttk.LabelFrame(dialog,text="Enter a grid name and size",padding=16)
    create.pack(fill="x",padx=16,pady=(16,8))
    ttk.Label(create,text="Name").grid(row=0,column=0,sticky="w",padx=(0,12))
    name_entry = ttk.Entry(create,width=32)
    name_entry.grid(row=0,column=1,pady=4)
    ttk.Label(create,text="Grid size").grid(row=1,column=0,sticky="w",padx=(0,12))
    size_entry = ttk.Entry(create,width=32)
    size_entry.insert(0,'5')
    size_entry.grid(row=1,column=1,pady=4)
    def open_name():
        try:
            name = grid_name(name_entry.get().strip())
            size = int(size_entry.get().strip())
            if size < 1: raise ValueError("Grid size must be a positive integer.")
            path = DATA_DIRECTORY / f'{name}.json'
            if path.exists() and read_state(path)['size'] != size:
                raise ValueError("That name already has a different grid size. Choose another name or load it below.")
            path = prepare_grid(dialog,name,size=size)
            if path is None: return
            result.append((name,path,None))
            dialog.destroy()
        except (OSError,ValueError,argparse.ArgumentTypeError) as error:
            messagebox.showerror("Could not open grid",str(error),parent=dialog)
    ttk.Button(create,text="Open grid",command=open_name).grid(row=2,column=0,columnspan=2,sticky="ew",pady=(8,0))
    saved = ttk.LabelFrame(dialog,text="Load a saved state",padding=16)
    saved.pack(fill="x",padx=16,pady=(8,16))
    choices = launcher_states()
    selection = ttk.Combobox(saved,state="readonly",values=[item[0] for item in choices],width=44)
    selection.pack(fill="x")
    if choices: selection.current(0)
    def open_saved():
        try:
            _,name,path,snapshot = choices[selection.current()]
            read_state(path)
            if snapshot:
                result.append((name,DATA_DIRECTORY / f'{name}.json',path))
            else:
                prepared = prepare_grid(dialog,name)
                if prepared is None: return
                result.append((name,prepared,None))
            dialog.destroy()
        except (OSError,ValueError,IndexError) as error:
            messagebox.showerror("Could not load state",str(error),parent=dialog)
    ttk.Button(saved,text="Load state",command=open_saved,state="normal" if choices else "disabled").pack(fill="x",pady=(8,0))
    name_entry.focus_set()
    root.wait_window(dialog)
    return result[0] if result else None


class GridCanvas(tk.Canvas):
    """A square paper-style board with clickable cells."""

    def __init__(self, parent, select, size):
        minimum = size * MIN_CELL_SIZE + 8
        super().__init__(parent, bg="#f4f6fa", highlightthickness=0,
                         width=minimum, height=max(360, minimum))
        self.select_cell = select
        self.size = size
        self.cells = []
        self.selection = (0, 0)
        self.bounds = (0, 0, 0)
        self.bind("<Configure>", lambda event: self.draw())
        self.bind("<Button-1>", self.click)
        self.configure(cursor="hand2")

    def click(self, event):
        left, top, side = self.bounds
        if side and left <= event.x < left + side and top <= event.y < top + side:
            self.select_cell(int((event.x - left) * self.size / side),
                             int((event.y - top) * self.size / side))

    def draw(self):
        self.delete("all")
        side = max(0, min(self.winfo_width(), self.winfo_height()) - 8)
        if side < 5:
            return
        left = 4
        top = (self.winfo_height() - side) / 2
        self.bounds = (left, top, side)
        cell = side / self.size
        self.create_rectangle(left, top, left + side, top + side, fill="white", outline="")
        font_size = max(12, min(24, int(cell * 0.27)))
        for x, y, text, color in self.cells:
            x0, y0 = left + x * cell, top + y * cell
            if color != "#ffffff":
                self.create_rectangle(x0, y0, x0 + cell, y0 + cell, fill=color, outline="")
            cx, cy = x0 + cell / 2, y0 + cell / 2
            fraction = fraction_parts(text)
            if fraction:
                fraction_font = tkfont.Font(family="Times New Roman", size=font_size, slant="italic")
                while max(math_width(math_runs(part), fraction_font) for part in fraction) > cell - 16 and fraction_font.cget("size") > 8:
                    fraction_font.configure(size=fraction_font.cget("size") - 1)
                offset_size = fraction_font.metrics("linespace") * 0.8
                for part, offset in ((fraction[0], -offset_size),
                                     (fraction[1], offset_size)):
                    draw_math(self, cx, cy + offset, part, fraction_font)
                half = (max(math_width(math_runs(part), fraction_font) for part in fraction) + 6) / 2
                self.create_line(cx - half, cy, cx + half, cy, fill="#333333")
            else:
                rendered = inline_math(text)
                math_font = tkfont.Font(family="Times New Roman", size=font_size, slant="italic")
                while math_width(math_runs(rendered), math_font) > cell - 12 and math_font.cget("size") > 8:
                    math_font.configure(size=math_font.cget("size") - 1)
                draw_math(self, cx, cy, rendered, math_font)
        for index in range(1, self.size):
            offset = index * cell
            self.create_line(left + offset, top, left + offset, top + side,
                             fill="#c5c5c5", dash=(1, 3))
            self.create_line(left, top + offset, left + side, top + offset,
                             fill="#c5c5c5", dash=(1, 3))
        self.create_rectangle(left, top, left + side, top + side, outline="#666666", width=1)
        x, y = self.selection
        self.create_rectangle(left + x * cell + 2, top + y * cell + 2,
                              left + (x + 1) * cell - 2, top + (y + 1) * cell - 2,
                              outline="#8ba5bf", width=1)


class PuzzleApp:
    def __init__(self, root, name, state_path, initial_state=None):
        self.root = root
        self.STATE_PATH = state_path
        self.SIZE = (read_state(state_path) if initial_state is None else initial_state)["size"]
        root.title(f"Jane Street Puzzle — {name}")
        root.geometry("760x720")
        root.minsize(620, 620)
        root.configure(bg="#f4f6fa")
        self.expressions = [["" for _ in range(self.SIZE)] for _ in range(self.SIZE)]
        self.disabled_cells = set()
        self.selected = (0, 0)
        self.show_values = tk.BooleanVar(value=False)
        self.formula = tk.StringVar()
        self.status = tk.StringVar()
        self.detail = tk.StringVar()
        self.variables = {}
        self.valid_values = {}
        self.search_revision = 0
        self.analytical_assignments = None
        self.analysis_steps = []
        self.search_message = tk.StringVar(value="Analyze included clues to find valid values.")
        self.connectivity_message = tk.StringVar()
        self.region_labels = {}
        self.region_palette = {}
        self.overlay_message = tk.StringVar()
        self.overlay_target = tk.StringVar(value="Highest")
        self.region_elapsed = tk.StringVar()
        self.overlay_states = []
        self.overlay_index = 0
        self.overlay_undo = []
        self.overlay_redo = []
        self.region_cancel = None
        self.storage_error = tk.StringVar()
        self.load_state(initial_state)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f4f6fa")
        style.configure("TLabel", background="#f4f6fa", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=7)

        layout = ttk.Frame(root, padding=24)
        layout.pack(fill="both", expand=True)
        layout.columnconfigure(0, weight=1)
        layout.rowconfigure(1, weight=1)
        main = ttk.Frame(layout)
        main.grid(row=0, column=0, sticky="ew")
        ttk.Label(main, text=f"{name} · {self.SIZE}×{self.SIZE}", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        region = ttk.Frame(main)
        region.pack(anchor="w", pady=(0, 8))
        ttk.Label(region, text="max region size =").pack(side="left", padx=(0, 6))
        self.max_region_value = tk.StringVar(value=str(max_region_size(self.SIZE)))
        ttk.Label(region, textvariable=self.max_region_value,
                  font=("Segoe UI", 10)).pack(side="left")
        self.selection_label = ttk.Label(main)
        self.selection_label.pack(anchor="w")
        editor = ttk.Frame(main)
        editor.pack(fill="x", pady=8)
        editor.columnconfigure(0, weight=1, uniform="equation_space")
        editor.columnconfigure(2, weight=1, uniform="equation_space")
        self.entry = ttk.Entry(editor, textvariable=self.formula, font=("Consolas", 14))
        self.entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(editor, text="Set cell", command=self.apply).grid(row=0, column=1, padx=(8, 0))
        help_label = ttk.Label(main, text="Select a cell, edit its expression, then click Set cell to save. Use a blank expression to empty it.")
        help_label.pack(anchor="w", fill="x")

        body = ttk.Frame(layout)
        body.grid(row=1, column=0, sticky="nsew", pady=16)
        body.columnconfigure(0, weight=1)
        minimum_board = self.SIZE * MIN_CELL_SIZE + 8
        body.columnconfigure(0, minsize=minimum_board + 20)
        body.rowconfigure(0, weight=1, minsize=minimum_board + 32)
        self.board = GridCanvas(body, self.select, self.SIZE)
        self.board.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        self.board.bind("<Double-Button-1>", lambda event: self.entry.focus_set())
        self.board.bind("<Button-3>", self.toggle_cell)
        sidebar = ttk.Frame(body)
        sidebar.grid(row=0, column=1, rowspan=2, sticky="nsew")
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(0, weight=1)
        variable_area = ttk.Frame(sidebar)
        variable_area.grid(row=0,column=0,sticky="nsew",padx=(0,12))
        variable_area.columnconfigure(0,weight=1)
        variable_area.rowconfigure(0,weight=1)
        overlay_panel = ttk.Frame(sidebar)
        overlay_panel.grid(row=0,column=1,sticky="new")
        overlay_panel.columnconfigure(0,minsize=250)
        ttk.Label(overlay_panel, text="Regions", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        scroll_variables = len(self.variables) > 3
        if scroll_variables:
            variable_canvas = tk.Canvas(variable_area, width=250, height=400,
                                        bg="#f4f6fa", highlightthickness=0)
            variable_canvas.grid(row=0, column=0, sticky="nsew")
            scrollbar = ttk.Scrollbar(variable_area, orient="vertical", command=variable_canvas.yview)
            scrollbar.grid(row=0, column=1, sticky="ns")
            horizontal_scrollbar = ttk.Scrollbar(variable_area, orient="horizontal", command=variable_canvas.xview)
            horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
            variable_canvas.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal_scrollbar.set)
            panel = ttk.Frame(variable_canvas)
            variable_canvas.create_window(0, 0, window=panel, anchor="nw")
            panel.bind("<Configure>", lambda event: variable_canvas.configure(scrollregion=variable_canvas.bbox("all")))
        else:
            panel = ttk.Frame(variable_area)
            panel.grid(row=0, column=0, sticky="new")
        ttk.Label(panel, text="Variables", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        panel.columnconfigure(0,minsize=250)
        for row, (name, variable) in enumerate(self.variables.items(),start=1):
            field = ttk.LabelFrame(panel, text=name, padding=10)
            field.grid(row=row, column=0, sticky="new", padx=(0, 10), pady=(0, 10))
            field.columnconfigure(1, weight=1)
            ttk.Label(field, text="Candidate").grid(row=0, column=0, sticky="w", padx=(0,10))
            ttk.Entry(field, textvariable=variable, width=10).grid(row=0, column=1, sticky="ew")
            self.valid_values[name] = tk.StringVar(value="Not analyzed")
            ttk.Label(field, text="Valid values").grid(row=1, column=0, columnspan=2, sticky="w", pady=(8,0))
            ttk.Label(field, textvariable=self.valid_values[name], wraplength=210).grid(row=2, column=0, columnspan=2, sticky="w")
        self.analyze_button = ttk.Button(panel, text="Analyze valid values", command=self.analyze_valid_values)
        controls_row = len(self.variables)+1
        self.analyze_button.grid(row=controls_row, column=0, sticky="ew", padx=(0, 10), pady=(0, 8))
        ttk.Label(panel, textvariable=self.search_message, wraplength=230).grid(row=controls_row+1, column=0, sticky="nw", padx=(0, 10))
        self.connectivity_button = ttk.Button(panel, text="Check connectivity", command=self.check_connectivity)
        self.connectivity_button.grid(row=controls_row+2, column=0, sticky="ew", padx=(0, 10), pady=(12, 8))
        ttk.Label(panel, textvariable=self.connectivity_message, wraplength=230).grid(row=controls_row+3, column=0, sticky="nw", padx=(0, 10))
        overlay_selection = ttk.LabelFrame(overlay_panel, text="Overlay region")
        overlay_selection.grid(row=1, column=0, sticky="ew", padx=(0,10), pady=(0,8))
        self.overlay_buttons = []
        for number in range(1,max_region_size(self.SIZE)+1):
            button = ttk.Button(overlay_selection, text=str(number), width=4,
                                command=lambda value=number:self.select_overlay_region(value))
            button.grid(row=(number-1)//5, column=(number-1)%5, padx=2, pady=2, sticky="ew")
            self.overlay_buttons.append(button)
        for column in range(5):
            overlay_selection.columnconfigure(column,weight=1)
        ttk.Label(overlay_panel, textvariable=self.overlay_message, wraplength=230).grid(row=8, column=0, sticky="nw", padx=(0, 10),pady=(8,0))
        ttk.Label(overlay_panel, textvariable=self.region_elapsed, wraplength=230).grid(row=9,column=0,sticky="w",pady=(4,0))
        self.abort_button = ttk.Button(overlay_panel,text="Abort",command=self.abort_region_operation,state="disabled")
        self.abort_button.grid(row=7,column=0,sticky="ew",padx=(0,10),pady=(0,8))
        overlay_navigation = ttk.Frame(overlay_panel)
        overlay_navigation.grid(row=3, column=0, sticky="ew", padx=(0,10), pady=8)
        ttk.Button(overlay_navigation, text="Previous", command=lambda:self.show_overlay(-1)).pack(side="left")
        ttk.Button(overlay_navigation, text="Next", command=lambda:self.show_overlay(1)).pack(side="left", padx=8)
        history_navigation = ttk.Frame(overlay_panel)
        history_navigation.grid(row=6,column=0,sticky="ew",pady=(0,8))
        self.compare_button = ttk.Button(overlay_panel,text="Compare incomplete regions",command=self.compare_regions,state="disabled")
        self.compare_button.grid(row=4,column=0,sticky="ew",padx=(0,10),pady=(0,8))
        self.completion_button = ttk.Button(overlay_panel,text="Attempt region completion",
                                           command=self.attempt_region_completion,state="disabled")
        self.completion_button.grid(row=5,column=0,sticky="ew",padx=(0,10),pady=(0,8))
        self.overlay_undo_button = ttk.Button(history_navigation,text="Undo",command=self.undo_overlay,state="disabled")
        self.overlay_undo_button.pack(side="left")
        self.overlay_redo_button = ttk.Button(history_navigation,text="Redo",command=self.redo_overlay,state="disabled")
        self.overlay_redo_button.pack(side="left",padx=8)
        footer = ttk.Frame(body)
        footer.grid(row=1, column=0, sticky="ew", padx=(0, 20))
        options = ttk.Frame(footer)
        options.pack(fill="x")
        self.display_button = ttk.Button(options, command=self.toggle_display)
        self.display_button.pack(side="left")
        self.update_display_button()
        ttk.Button(options, text="Exclude all", command=lambda: self.set_all_included(False)).pack(side="left", padx=(8, 0))
        ttk.Button(options, text="Include all", command=lambda: self.set_all_included(True)).pack(side="left", padx=(8, 0))
        saved_controls = ttk.Frame(footer)
        saved_controls.pack(fill="x",pady=(8,0))
        ttk.Button(saved_controls,text="Save state",command=self.save_named_state).pack(side="left")
        ttk.Button(saved_controls,text="Load state",command=self.choose_saved_state).pack(side="left",padx=8)
        ttk.Button(saved_controls,text="Reset to equations",command=self.reset_to_equations).pack(side="left")
        ttk.Button(saved_controls,text="Print state",command=self.print_state).pack(side="left",padx=(8,0))
        detail_label = ttk.Label(footer, textvariable=self.detail)
        detail_label.pack(anchor="w", fill="x", pady=(12, 4))
        status_label = ttk.Label(footer, textvariable=self.status)
        status_label.pack(anchor="w", fill="x")
        storage_label = ttk.Label(footer, textvariable=self.storage_error, foreground="#a02828")
        storage_label.pack(anchor="w", fill="x")
        def wrap_grid_labels(event):
            width = max(100, min(self.board.winfo_width(), self.board.winfo_height()) - 8)
            for label in (detail_label, status_label, storage_label):
                if str(label.cget("wraplength")) != str(width):
                    label.configure(wraplength=width)
        self.board.bind("<Configure>", wrap_grid_labels, add="+")
        main.bind("<Configure>", lambda event: help_label.configure(wraplength=max(100, event.width)))
        # Messages can add lines after a search finishes. Recalculate the
        # minimum height so the sidebar's last button never gets clipped.
        resize_pending = [False]
        def fit_contents():
            resize_pending[0] = False
            left_height = minimum_board + 32 + footer.winfo_reqheight()
            right_height = max(420 if scroll_variables else panel.winfo_reqheight(),overlay_panel.winfo_reqheight())
            height = max(620, main.winfo_reqheight() + max(left_height, right_height) + 80)
            width = max(820, sidebar.winfo_reqwidth() + minimum_board + 68)
            root.minsize(width, height)
        def schedule_fit(event=None):
            if not resize_pending[0]:
                resize_pending[0] = True
                root.after_idle(fit_contents)
        footer.bind("<Configure>", schedule_fit)
        panel.bind("<Configure>", schedule_fit, add="+")
        overlay_panel.bind("<Configure>", schedule_fit, add="+")
        main.bind("<Configure>", schedule_fit, add="+")
        for message in (self.search_message, self.connectivity_message,
                        self.overlay_message, self.detail, self.status, self.storage_error):
            message.trace_add("write", lambda *_: schedule_fit())
        self.select(0, 0)
        if self.analytical_assignments is not None:
            for name,text in candidate_labels(self.analytical_assignments,self.valid_values).items():
                self.valid_values[name].set(text)
            self.search_message.set(f"Restored {len(self.analytical_assignments)} analyzed partial assignments.")
        for variable in self.variables.values():
            variable.trace_add("write", self.settings_changed)
        root.update_idletasks()
        # Reserve room for controls even with Windows font/display scaling.
        body_height = max(minimum_board + 32 + footer.winfo_reqheight(),
                          max(420 if scroll_variables else panel.winfo_reqheight(),overlay_panel.winfo_reqheight()))
        minimum_height = max(620, main.winfo_reqheight() + body_height + 80)
        minimum_width = max(820, sidebar.winfo_reqwidth() + minimum_board + 68)
        root.minsize(minimum_width, minimum_height)
        root.geometry(f"{max(940, minimum_width + 60)}x{max(760, minimum_height)}")

    def load_state(self, state=None):
        if state is None and not self.STATE_PATH.exists():
            return
        try:
            state = read_state(self.STATE_PATH) if state is None else state
            expressions = state["expressions"]
            show_values = state.get("show_values", False)
            self.expressions = expressions
            self.disabled_cells = set(state.get("disabled_cells", []))
            self.variables = {name: tk.StringVar(value=value) for name, value in state["variables"].items()}
            self.show_values.set(show_values)
            self.overlay_target.set(str(state.get("overlay_region", "Highest")))
            analysis = state.get("analysis")
            if analysis:
                self.analytical_assignments = [{name: None if value is None else Fraction(value)
                                               for name, value in assignment.items()}
                                              for assignment in analysis.get("assignments", [])]
                self.analysis_steps = analysis.get("steps", [])
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.storage_error.set(f"Could not load saved grid: {error}")

    def state_data(self):
        return make_grid_state(self.SIZE,self.expressions,self.disabled_cells,
            {name:value.get() for name,value in self.variables.items()},
            self.overlay_target.get(),self.show_values.get(),self.analytical_assignments,self.analysis_steps)

    def save_state(self):
        state = self.state_data()
        try:
            write_state(self.STATE_PATH, state)
            self.storage_error.set("")
        except OSError as error:
            self.storage_error.set(f"Could not save grid: {error}")

    def print_state(self):
        self.save_named_state(picture=True)

    def save_named_state(self, picture=False):
        if getattr(self,'overlay_busy',False):
            self.storage_error.set("Wait for the overlay analysis to finish before saving.")
            return
        title = "Print state" if picture else "Save state"
        name = simpledialog.askstring(title,"Name for this picture and state:" if picture else "Name for this saved state:",parent=self.root,
                                     initialvalue=datetime.now().strftime('%Y-%m-%d_%H-%M-%S'))
        if name is None: return
        try:
            name = grid_name(name.strip())
            folder = Path(__file__).resolve().parent / 'saved states' / self.STATE_PATH.stem
            path = folder / f'{name}.json'
            picture_path = Path(__file__).resolve().parent / f'{name}.png'
            if (path.exists() or (picture and picture_path.exists())) and not messagebox.askyesno(title,f"Replace existing files named '{name}'?",parent=self.root):
                return
            state = make_saved_state(self.state_data(),self.overlay_snapshot(),
                self.overlay_undo,self.overlay_redo,self.selected,
                {key:value.get() for key,value in self.valid_values.items()},
                self.search_message.get(),self.connectivity_message.get())
            if picture:
                self.refresh()
                self.root.update_idletasks()
                image_data = grid_picture(self.board)
                temporary = picture_path.with_suffix('.png.tmp')
                temporary.write_bytes(image_data)
                temporary.replace(picture_path)
            write_state(path,state)
            self.storage_error.set("")
        except (OSError,ValueError,argparse.ArgumentTypeError) as error:
            self.storage_error.set(f"Could not save state: {error}")

    def choose_saved_state(self):
        if getattr(self,'overlay_busy',False):
            self.storage_error.set("Wait for the overlay analysis to finish before loading.")
            return
        folder = Path(__file__).resolve().parent / 'saved states' / self.STATE_PATH.stem
        paths = sorted(folder.glob('*.json'))
        if not paths:
            self.storage_error.set("No saved states for this grid yet.")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Load state")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog,text="Saved state:").pack(anchor="w",padx=16,pady=(16,4))
        selection = ttk.Combobox(dialog,state="readonly",values=[path.stem for path in paths],width=40)
        selection.pack(padx=16,pady=4)
        selection.current(0)
        def load():
            if self.load_named_state(paths[selection.current()]):
                dialog.destroy()
        ttk.Button(dialog,text="Load",command=load).pack(padx=16,pady=16)

    def load_named_state(self, path):
        try:
            state,snapshot,history,selected,analysis,assignments = load_snapshot(
                path,self.SIZE,self.variables)
            self.updating_candidates = True
            try:
                self.expressions = state['expressions']
                self.disabled_cells = set(state.get('disabled_cells',[]))
                for name,value in state['variables'].items(): self.variables[name].set(value)
                self.show_values.set(state.get('show_values',False))
                self.analytical_assignments = assignments
                self.analysis_steps = [] if analysis is None else analysis.get('steps',[])
                for name,label in self.valid_values.items(): label.set(state.get('valid_values',{}).get(name,'Not analyzed'))
                self.search_message.set(state.get('search_message',''))
                self.connectivity_message.set(state.get('connectivity_message',''))
                self.overlay_undo,self.overlay_redo = history['undo'],history['redo']
                self.update_display_button()
                self.select(*selected)
                self.restore_overlay(snapshot)
                self.storage_error.set("")
            finally:
                self.updating_candidates = False
            return True
        except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
            self.storage_error.set(f"Could not load state: {error}")
            return False

    def reset_to_equations(self):
        if getattr(self,'region_cancel',None) is not None:
            self.region_cancel.set()
        self.clear_regions()
        self.invalidate_search()
        self.updating_candidates = True
        try:
            for variable in self.variables.values():
                variable.set('')
        finally:
            self.updating_candidates = False
        self.search_message.set("Analyze included clues to find valid values.")
        self.overlay_target.set('Highest')
        self.overlay_index = 0
        self.overlay_highest = None
        self.overlay_base_labels = {}
        self.overlay_tested = 0
        self.disabled_cells.clear()
        self.connectivity_message.set("")
        self.show_values.set(False)
        self.update_display_button()
        self.refresh()
        self.save_state()

    def settings_changed(self, *_):
        if getattr(self, "updating_candidates", False):
            return
        if _:
            self.clear_regions()
        self.connectivity_message.set("")
        self.refresh()
        self.save_state()

    def apply_single_assignment(self):
        if self.analytical_assignments is None or len(self.analytical_assignments) != 1:
            return False
        changed = False
        self.updating_candidates = True
        try:
            for name, value in self.analytical_assignments[0].items():
                if value is not None and name in self.variables:
                    text = str(value)
                    if self.variables[name].get() != text:
                        self.variables[name].set(text)
                        changed = True
        finally:
            self.updating_candidates = False
        if changed:
            self.clear_regions()
            self.connectivity_message.set("")
            self.refresh()
        return changed

    def update_display_button(self):
        self.display_button.configure(text="Prioritize equations" if self.show_values.get()
                                      else "Prioritize values")

    def toggle_display(self):
        self.show_values.set(not self.show_values.get())
        self.update_display_button()
        self.refresh()
        self.save_state()

    def invalidate_search(self):
        self.analytical_assignments = None
        self.analysis_steps = []
        self.search_revision += 1
        for value in self.valid_values.values():
            value.set("Not computed")
        self.search_message.set("Grid changed. Analyze valid values again.")


    def analyze_valid_values(self):
        try:
            expressions = self.active_expressions()
            for expression in (text for row in expressions for text in row if text.strip()):
                clue_variables(expression, self.variables)
        except (ValueError, SyntaxError, ZeroDivisionError) as error:
            self.search_message.set(str(error))
            return
        self.invalidate_search()
        revision = self.search_revision
        self.analyze_button.configure(state="disabled")
        self.search_message.set("Analyzing included clues…")
        results = Queue()
        def work():
            try:
                results.put((analyze_grid(expressions, self.variables), None))
            except Exception as error:
                results.put((None, str(error)))
        threading.Thread(target=work, daemon=True).start()
        def poll():
            try:
                result, error = results.get_nowait()
            except Empty:
                self.root.after(50, poll)
                return
            self.analyze_button.configure(state="normal")
            if revision != self.search_revision:
                return
            if error:
                self.search_message.set(f"Could not analyze: {error}")
                return
            self.analytical_assignments, self.analysis_steps = result
            self.apply_single_assignment()
            for name,text in candidate_labels(self.analytical_assignments,self.valid_values).items():
                self.valid_values[name].set(text)
            message = f"{len(self.analytical_assignments)} analytically valid partial assignments."
            if self.analytical_assignments:
                message += " Example: " + ", ".join(f"{name}: {'?' if value is None else value}"
                                                    for name,value in self.analytical_assignments[0].items()) + "."
            self.search_message.set(message)
            self.save_state()
        self.root.after(50, poll)


    def select(self, x, y):
        self.selected = (x, y)
        self.formula.set(self.expressions[y][x])
        self.selection_label.configure(text=f"Selected cell: row {y + 1}, column {x + 1}")
        self.refresh()

    def active_expressions(self):
        return included_expressions(self.expressions,getattr(self,'disabled_cells',set()))

    def toggle_cell(self, event):
        left, top, side = self.board.bounds
        if not side or not (left <= event.x < left+side and top <= event.y < top+side):
            return
        column = int((event.x-left)*self.SIZE/side)
        row = int((event.y-top)*self.SIZE/side)
        cell = row*self.SIZE+column
        if cell in self.disabled_cells:
            self.disabled_cells.remove(cell)
        else:
            self.disabled_cells.add(cell)
        self.clear_regions()
        self.connectivity_message.set("")
        self.invalidate_search()
        self.select(column, row)
        self.save_state()

    def set_all_included(self, included):
        self.disabled_cells = set() if included else {
            row*self.SIZE+column for row, cells in enumerate(self.expressions)
            for column, expression in enumerate(cells) if expression.strip()
        }
        self.clear_regions()
        self.connectivity_message.set("")
        self.invalidate_search()
        self.refresh()
        self.save_state()

    def apply(self):
        self.clear_regions()
        expression = self.formula.get().strip()
        x, y = self.selected
        self.expressions[y][x] = expression
        self.connectivity_message.set("")
        self.invalidate_search()
        self.refresh()
        self.save_state()

    def check_connectivity(self):
        expressions = self.active_expressions()
        try:
            variables = {name: Fraction(value.get().strip()) for name, value in self.variables.items()}
        except (ValueError, ZeroDivisionError):
            self.connectivity_message.set("Enter numeric candidate values.")
            return
        partials = None if self.analytical_assignments is None else [dict(item) for item in self.analytical_assignments]
        revision = self.search_revision
        self.connectivity_button.configure(state="disabled")
        self.connectivity_message.set("Checking connectivity…")
        results = Queue()
        def work():
            try:
                message = check_grid_connectivity(expressions, variables)[1]
                survivors = None
                if partials is not None:
                    survivors = []
                    for assignment in partials:
                        used = set().union(*(clue_variables(cell, self.variables) for row in expressions for cell in row if cell.strip()))
                        if any(assignment.get(name) is None for name in used):
                            raise ValueError("Analyze the included clues before filtering connectivity.")
                        known = {name:value for name,value in assignment.items() if value is not None}
                        if check_grid_connectivity(expressions, known)[0]:
                            survivors.append(assignment)
                results.put((message, survivors))
            except Exception as error:
                results.put((f"Could not finish connectivity check: {error}", None))
        threading.Thread(target=work, daemon=True).start()
        def poll():
            try:
                message, filtered = results.get_nowait()
            except Empty:
                self.root.after(50, poll)
                return
            self.connectivity_button.configure(state="normal")
            if revision != self.search_revision or expressions != self.active_expressions():
                self.connectivity_message.set("Grid or analysis changed. Check connectivity again.")
                return
            applied_assignment = False
            if filtered is not None:
                self.analytical_assignments = filtered
                applied_assignment = self.apply_single_assignment()
                for name, label in self.valid_values.items():
                    values = {assignment.get(name) for assignment in filtered}
                    label.set("Unknown" if None in values else format_candidates(values))
                self.search_message.set(f"{len(filtered)} analyzed assignments pass connectivity.")
                self.save_state()
            try:
                current = {name: Fraction(value.get().strip()) for name, value in self.variables.items()}
            except (ValueError, ZeroDivisionError):
                current = None
            if expressions != self.active_expressions() or (current != variables and not applied_assignment):
                message = "Candidates or grid changed. Check connectivity again."
            self.connectivity_message.set(message)
        self.root.after(50, poll)

    def clear_regions(self, reset_history=True):
        self.region_labels = {}
        self.region_palette = {}
        self.overlay_states = []
        self.overlay_message.set("")
        if hasattr(self,'region_elapsed'):
            self.region_elapsed.set("")
        if reset_history:
            self.overlay_undo.clear()
            self.overlay_redo.clear()
        if hasattr(self,"overlay_buttons"):
            self.update_overlay_buttons()

    def select_overlay_region(self, number):
        self.overlay_target.set(str(number))
        self.save_state()
        if self.overlay_states and number != self.overlay_highest:
            self.continue_overlay(number)
        else:
            self.overlay_regions()

    def set_overlay_buttons_enabled(self, enabled):
        self.overlay_busy = not enabled
        self.update_overlay_buttons()

    def abort_region_operation(self):
        if getattr(self,'overlay_busy',False) and self.region_cancel is not None:
            self.region_cancel.set()
            self.abort_button.configure(state="disabled")
            self.overlay_message.set("Stopping region operation…")

    def overlay_snapshot(self):
        return make_overlay_snapshot(self.overlay_states,self.overlay_index,
            getattr(self,'overlay_highest',None),getattr(self,'overlay_base_labels',{}),
            getattr(self,'overlay_tested',0),
            str(self.overlay_highest) if self.overlay_states else self.overlay_target.get(),
            self.overlay_message.get(),self.region_labels,self.region_palette,
            self.region_elapsed.get() if hasattr(self,'region_elapsed') else '')

    def record_overlay(self, previous):
        self.overlay_undo.append(previous)
        self.overlay_redo.clear()

    def restore_overlay(self, snapshot):
        snapshot = deepcopy(snapshot)
        self.overlay_states = snapshot['states']
        self.overlay_index = snapshot['index']
        self.overlay_highest = snapshot['highest']
        self.overlay_base_labels = snapshot['base']
        self.overlay_tested = snapshot['tested']
        self.overlay_target.set(snapshot['target'])
        self.region_labels = snapshot['labels']
        self.region_palette = snapshot['palette']
        self.overlay_message.set(snapshot['message'])
        if hasattr(self,'region_elapsed'):
            self.region_elapsed.set(snapshot.get('elapsed',''))
        self.update_overlay_buttons()
        self.refresh()
        self.save_state()

    def undo_overlay(self):
        if getattr(self,'overlay_busy',False) or not self.overlay_undo:
            return
        self.overlay_redo.append(self.overlay_snapshot())
        self.restore_overlay(self.overlay_undo.pop())

    def redo_overlay(self):
        if getattr(self,'overlay_busy',False) or not self.overlay_redo:
            return
        self.overlay_undo.append(self.overlay_snapshot())
        self.restore_overlay(self.overlay_redo.pop())

    def update_overlay_buttons(self):
        completed = completed_regions(self.overlay_states,
            getattr(self,'overlay_base_labels',{}),getattr(self,'overlay_highest',None),identical=True)
        for number,button in enumerate(self.overlay_buttons,start=1):
            disabled = getattr(self,"overlay_busy",False) or number in completed
            button.configure(state="disabled" if disabled else "normal")
        if hasattr(self,'overlay_undo_button'):
            busy = getattr(self,'overlay_busy',False)
            self.overlay_undo_button.configure(state="normal" if self.overlay_undo and not busy else "disabled")
            self.overlay_redo_button.configure(state="normal" if self.overlay_redo and not busy else "disabled")
        if hasattr(self,'compare_button'):
            self.compare_button.configure(state="normal" if self.overlay_states and not getattr(self,'overlay_busy',False) else "disabled")
        if hasattr(self,'completion_button'):
            self.completion_button.configure(state="normal" if self.overlay_states and not getattr(self,'overlay_busy',False) else "disabled")
        if hasattr(self,'abort_button'):
            busy = getattr(self,'overlay_busy',False)
            self.abort_button.configure(state="normal" if busy and self.region_cancel is not None
                                        and not self.region_cancel.is_set() else "disabled")

    def overlay_regions(self):
        expressions = self.active_expressions()
        selected = self.overlay_target.get()
        try:
            variables = {name:Fraction(value.get().strip()) for name,value in self.variables.items()}
            target = None if selected == "Highest" else int(selected)
        except (ValueError,ZeroDivisionError):
            self.overlay_message.set("Enter numeric candidate values first.")
            return
        previous = self.overlay_snapshot()
        task = BackgroundRegionOperation(lambda progress:find_region_overlays(expressions,variables,progress,region=target))
        started = task.started
        self.region_cancel = task.cancel
        self.set_overlay_buttons_enabled(False)
        self.overlay_message.set("Testing translated, reflected, and rotated overlays…")
        def poll():
            self.region_elapsed.set(elapsed_text(started))
            updates,final = task.poll()
            for data in updates:
                self.overlay_message.set(f"Tested {data[0]} placements; {data[1]} valid so far.")
            if final is None:
                self.root.after(50,poll)
                return
            self.set_overlay_buttons_enabled(True)
            try:
                current = {name:Fraction(value.get().strip()) for name,value in self.variables.items()}
            except (ValueError,ZeroDivisionError): current = None
            if expressions != self.active_expressions() or current != variables or self.overlay_target.get() != selected:
                self.overlay_message.set("Grid or candidates changed. Overlay regions again.")
                return
            kind,data = final
            if kind == 'error':
                self.overlay_message.set(data)
                self.refresh()
                return
            self.record_overlay(previous)
            self.clear_regions(reset_history=False)
            self.region_elapsed.set(elapsed_text(started))
            self.overlay_highest,self.overlay_base_labels,self.overlay_states,self.overlay_tested = data
            self.overlay_index = 0
            if not self.overlay_states:
                self.overlay_message.set(f"No valid overlays among {self.overlay_tested} tested placements.")
                self.refresh()
                return
            self.show_overlay(0)
        self.root.after(50,poll)

    def show_overlay(self, step):
        if not self.overlay_states:
            return
        self.update_overlay_buttons()
        self.overlay_index = (self.overlay_index+step)%len(self.overlay_states)
        state = self.overlay_states[self.overlay_index]
        self.region_labels = overlay_board(state,self.overlay_base_labels,self.overlay_highest)
        self.region_palette = region_colors(self.SIZE,self.region_labels)
        self.overlay_message.set(
            f"Overlay {self.overlay_index+1}/{len(self.overlay_states)} for region {self.overlay_highest}. "
            f"Row {state['row']+1}, column {state['column']+1}; rotation {state['rotation']*90}°"
            f"{' reflected' if state['reflected'] else ''}. "
            f"Minimum connected size: {state['minimum_size']}. {self.overlay_tested} placements tested.")
        if state.get('forced_cells'):
            self.overlay_message.set(self.overlay_message.get()+f" {len(state['forced_cells'])} forced adjacent cells added.")
        if state.get('connection_cells'):
            self.overlay_message.set(self.overlay_message.get()+f" {len(state['connection_cells'])} low-slack connection cells added.")
        if state.get('neighbor_growth'):
            self.overlay_message.set(self.overlay_message.get()+f" {len(state['neighbor_growth'])} cells forced by bordering-region growth.")
        if state.get('growth_limited'):
            self.overlay_message.set(self.overlay_message.get()+" Growth limited: 3 rounds per region or more than 10 candidate cells.")
        if 'parent_index' in state:
            self.overlay_message.set(self.overlay_message.get()+f" From preceding overlay {state['parent_index']+1}.")
        if state.get('reverse_containment'):
            self.overlay_message.set(self.overlay_message.get()+f" Shape derived by removing one cell from region {self.overlay_highest+1}.")
        if 'comparison_growth' in state:
            self.overlay_message.set(self.overlay_message.get()+f" {len(state['comparison_growth'])} cells forced by comparing incomplete regions.")
        if 'completion_growth' in state:
            self.overlay_message.set(self.overlay_message.get()+f" {len(state['completion_growth'])} cells added by mirrored region completion.")
        self.refresh()

    def continue_overlay(self, region=None):
        if not self.overlay_states:
            self.overlay_message.set("Generate valid overlays first.")
            return
        states = self.overlay_states
        current = self.overlay_highest
        target = current+1 if region is None else region
        if target > max_region_size(self.SIZE):
            self.overlay_message.set("The next region exceeds max region size.")
            return
        previous = self.overlay_snapshot()
        task = BackgroundRegionOperation(lambda progress:continue_region_overlays(self.SIZE,self.overlay_base_labels,current,states,progress,region=target))
        started = task.started
        self.region_cancel = task.cancel
        self.set_overlay_buttons_enabled(False)
        self.overlay_message.set(f"Testing all {len(states)} preceding overlays for region {target}…")
        def poll():
            self.region_elapsed.set(elapsed_text(started))
            updates,final = task.poll()
            for data in updates:
                self.overlay_message.set(f"Checked {data[0]}/{data[1]} preceding overlays; {data[2]} valid continuations.")
            if final is None:
                self.root.after(50,poll)
                return
            self.set_overlay_buttons_enabled(True)
            if self.overlay_states is not states:
                self.overlay_message.set("Grid or overlays changed. Generate overlays again.")
                return
            kind,data=final
            if kind=='error':
                self.overlay_message.set(data)
                return
            target,children,tested=data
            if not children:
                self.overlay_message.set(f"No valid region {target} continuations. Previous overlays retained.")
                return
            self.record_overlay(previous)
            self.overlay_highest=target
            self.overlay_states=children
            self.overlay_tested=tested
            self.overlay_target.set(str(target))
            self.overlay_index=0
            self.show_overlay(0)
            self.save_state()
        self.root.after(50,poll)

    def attempt_region_completion(self):
        self.compare_regions(completion=True)

    def compare_regions(self, completion=False):
        if not self.overlay_states or getattr(self,'overlay_busy',False):
            return
        states = self.overlay_states
        current,base = self.overlay_highest,self.overlay_base_labels
        previous = self.overlay_snapshot()
        analyze = attempt_region_completions if completion else compare_incomplete_regions
        task = BackgroundRegionOperation(lambda progress:analyze(self.SIZE,base,current,states,progress))
        started = task.started
        self.region_cancel = task.cancel
        self.set_overlay_buttons_enabled(False)
        self.overlay_message.set("Attempting region completions from smallest to largest…" if completion else "Comparing incomplete regions from largest to smallest…")
        def poll():
            self.region_elapsed.set(elapsed_text(started))
            updates,final = task.poll()
            for data in updates:
                self.overlay_message.set(f"Checked {data[0]}/{data[1]} overlays; {data[2]} surviving.")
            if final is None:
                self.root.after(50,poll)
                return
            self.set_overlay_buttons_enabled(True)
            if self.overlay_states is not states:
                self.overlay_message.set("Grid or overlays changed. Compare again.")
                return
            kind,data = final
            if kind == 'error':
                self.overlay_message.set(data)
                return
            if not data:
                self.overlay_message.set("No overlays survive mirrored completion. Previous overlays retained." if completion
                                         else "No overlays survive incomplete-region comparison. Previous overlays retained.")
                return
            self.record_overlay(previous)
            self.overlay_states = data
            self.overlay_index = 0
            self.show_overlay(0)
            self.save_state()
        self.root.after(50,poll)

    def refresh(self):
        filled, errors = 0, 0
        cells = []
        variable_error = None
        try:
            values = {name: Fraction(variable.get().strip()) for name, variable in self.variables.items()}
        except (ValueError, ZeroDivisionError):
            variable_error = "Enter numeric values for all variables (for example 3 or 1/2)."
        selected_detail = "Empty cell. Enter an expression or a positive integer."
        for y, row in enumerate(self.active_expressions()):
            for x, expression in enumerate(row):
                text, color = expression, "#ffffff"
                detail = "Empty cell. Enter an expression or a positive integer."
                if expression:
                    filled += 1
                    try:
                        if variable_error:
                            raise ValueError(variable_error)
                        value = evaluate(expression, values)
                        value_text = str(value)
                        detail = f"{expression} = {value_text}"
                        if values:
                            detail += " with " + ", ".join(f"{name} = {value}" for name, value in values.items())
                        if value <= 0 or value.denominator != 1 or value > max_region_size(self.SIZE):
                            color = "#fff1d6"
                            detail += f" • Result must be an integer from 1 to {max_region_size(self.SIZE)}."
                        if self.show_values.get():
                            text = value_text
                    except (ValueError, SyntaxError, ArithmeticError, RecursionError) as error:
                        errors += 1
                        color = "#ffe0e0"
                        detail = f"Cannot calculate {expression}: {error}"
                selected = (x, y) == self.selected
                region = self.region_labels.get(y*self.SIZE+x)
                if region is not None:
                    color = self.region_palette[region]
                    text = str(region) if self.show_values.get() or not expression else expression
                    if not expression:
                        detail = f"Forced cell in region {region}."
                if y*self.SIZE+x in getattr(self, "disabled_cells", set()):
                    color = "#e5e5e5"
                    text = self.expressions[y][x] or text
                    detail = "Equation disabled. Right-click to enable it again."
                cells.append((x, y, text, color))
                if selected:
                    selected_detail = detail
        self.detail.set(selected_detail)
        self.board.cells = cells
        self.board.selection = self.selected
        self.board.draw()
        self.status.set(variable_error or
                        f"{filled}/{self.SIZE ** 2} cells filled • {errors} expression errors. "
                        "Amber cells are outside the allowed integer region sizes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Open a named expression grid.")
    parser.add_argument("name", nargs="?", type=grid_name,
                        help="Grid name. Omit to choose a grid or saved state in the launcher.")
    args = parser.parse_args()
    window = tk.Tk()
    window.withdraw()
    try:
        if args.name is None:
            choice = choose_grid(window)
        else:
            state_path = prepare_grid(window,args.name)
            choice = None if state_path is None else (args.name,state_path,None)
        if choice is not None:
            name,state_path,snapshot = choice
            initial = None if snapshot is None else read_state(snapshot)
            app = PuzzleApp(window,name,state_path,initial_state=initial)
            if snapshot is not None:
                app.load_named_state(snapshot)
            window.deiconify()
            window.mainloop()
        else:
            window.destroy()
    except (OSError, ValueError) as error:
        messagebox.showerror("Could not open grid", str(error), parent=window)
        window.destroy()
