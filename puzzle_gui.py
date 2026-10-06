"""Interactive expression grid. Run with: python puzzle_gui.py"""

import ast
import argparse
import json
import operator
import re
import tkinter as tk
from fractions import Fraction
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk


DATA_DIRECTORY = Path(__file__).resolve().parent / "grids"


def grid_name(value):
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value)
            or value.upper() in {"CON", "PRN", "AUX", "NUL",
                                 *(f"COM{i}" for i in range(1, 10)),
                                 *(f"LPT{i}" for i in range(1, 10))}):
        raise argparse.ArgumentTypeError("Use a name of up to 64 letters, digits, hyphens, or underscores.")
    return value


def read_state(path):
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("Expected saved grid settings")
    expressions = state.get("expressions")
    size = state.get("size", len(expressions) if isinstance(expressions, list) else 0)
    if (type(size) is not int or size < 1
            or not isinstance(expressions, list) or len(expressions) != size
            or any(not isinstance(row, list) or len(row) != size
                   or any(not isinstance(cell, str) for cell in row) for row in expressions)):
        raise ValueError("Expected a square grid of expressions")
    if (not isinstance(state.get("x", "1"), str)
            or not isinstance(state.get("y", "1"), str)
            or type(state.get("show_values", False)) is not bool):
        raise ValueError("Invalid saved settings")
    state["size"] = size
    return state


def write_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def migrate_example():
    """Preserve the previous single grid as the named example grid."""
    old_path = Path(__file__).resolve().with_name("grid_state.json")
    new_path = DATA_DIRECTORY / "example.json"
    if old_path.exists() and not new_path.exists():
        write_state(new_path, read_state(old_path))


def prepare_grid(root, name):
    migrate_example()
    path = DATA_DIRECTORY / f"{name}.json"
    if not path.exists():
        size = simpledialog.askinteger("New grid", f"Size for '{name}' (number of rows and columns):",
                                       parent=root, minvalue=1)
        if size is None:
            return None
        write_state(path, {"size": size, "expressions": [[""] * size for _ in range(size)],
                           "x": "1", "y": "1", "show_values": False})
    # Validate before opening an editable grid so a damaged save isn't overwritten.
    read_state(path)
    return path


def display_expression(expression):
    """Use compact mathematical notation without changing the stored input."""
    expression = re.sub(r"(?:\^|\*\*)(-?\d+)",
                        lambda match: match[1].translate(str.maketrans(
                            "0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")), expression)
    expression = re.sub(r"(?<=\d)\s*\*\s*(?=[xy])", "", expression)
    return expression.replace("-", "−").replace("*", "·")


class GridCanvas(tk.Canvas):
    """A square paper-style board with clickable cells."""

    def __init__(self, parent, select, size):
        super().__init__(parent, bg="#f4f6fa", highlightthickness=0, height=360)
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
        left = (self.winfo_width() - side) / 2
        top = (self.winfo_height() - side) / 2
        self.bounds = (left, top, side)
        cell = side / self.size
        self.create_rectangle(left, top, left + side, top + side, fill="white", outline="")
        font_size = max(10, min(22, int(cell * 0.22)))
        for x, y, text, color in self.cells:
            x0, y0 = left + x * cell, top + y * cell
            if color != "#ffffff":
                self.create_rectangle(x0, y0, x0 + cell, y0 + cell, fill=color, outline="")
            cx, cy = x0 + cell / 2, y0 + cell / 2
            # A simple quotient is drawn as a stacked fraction, like the reference.
            fraction = re.fullmatch(r"\s*([xy]|\d+)\s*/\s*([xy]|\d+)\s*", text)
            if fraction:
                for part, offset in ((fraction[1], -font_size * 0.65),
                                     (fraction[2], font_size * 0.65)):
                    self.create_text(cx, cy + offset, text=part,
                                     font=("Times New Roman", font_size, "italic"))
                half = font_size * max(len(fraction[1]), len(fraction[2])) * 0.4
                self.create_line(cx - half, cy, cx + half, cy, fill="#333333")
            else:
                self.create_text(cx, cy, text=display_expression(text),
                                 font=("Times New Roman", font_size, "italic"),
                                 width=cell - 8, fill="#252525")
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


OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}


def evaluate(expression, x, y):
    """Evaluate arithmetic only, keeping rational results exact."""
    if len(expression) > 200:
        raise ValueError("Expression is too long")
    tree = ast.parse(expression.replace("^", "**"), mode="eval")

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return Fraction(str(node.value))
        if isinstance(node, ast.Name) and node.id in ("x", "y"):
            return Fraction(x if node.id == "x" else y)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow):
                if right.denominator != 1 or abs(right) > 20:
                    raise ValueError("Powers require an integer exponent from -20 to 20")
                right = int(right)
            result = OPERATORS[type(node.op)](left, right)
            result = Fraction(result)
            if result.numerator.bit_length() > 4096 or result.denominator.bit_length() > 4096:
                raise ValueError("Result is too large")
            return result
        raise ValueError("Use numbers, x, y, parentheses, and arithmetic operators only")

    return visit(tree.body)


class PuzzleApp:
    def __init__(self, root, name, state_path):
        self.root = root
        self.STATE_PATH = state_path
        self.SIZE = read_state(state_path)["size"]
        root.title(f"Jane Street Puzzle — {name}")
        root.geometry("760x720")
        root.minsize(620, 620)
        root.configure(bg="#f4f6fa")
        self.expressions = [["" for _ in range(self.SIZE)] for _ in range(self.SIZE)]
        self.selected = (0, 0)
        self.show_values = tk.BooleanVar(value=False)
        self.formula = tk.StringVar()
        self.status = tk.StringVar()
        self.detail = tk.StringVar()
        self.x_value = tk.StringVar(value="1")
        self.y_value = tk.StringVar(value="1")
        self.storage_error = tk.StringVar()
        self.loading_formula = False
        self.load_state()
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
        ttk.Label(main, text="x and y are shared by every cell.").pack(anchor="w", pady=(4, 8))
        variables = ttk.Frame(main)
        variables.pack(fill="x", pady=(0, 16))
        for name, variable in (("x", self.x_value), ("y", self.y_value)):
            ttk.Label(variables, text=f"{name} =").pack(side="left", padx=(0, 6))
            ttk.Entry(variables, textvariable=variable, width=10,
                      font=("Consolas", 12)).pack(side="left", padx=(0, 18))
        self.selection_label = ttk.Label(main)
        self.selection_label.pack(anchor="w")
        editor = ttk.Frame(main)
        editor.pack(fill="x", pady=8)
        self.entry = ttk.Entry(editor, textvariable=self.formula, font=("Consolas", 14))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda event: self.apply())
        ttk.Button(editor, text="Set cell", command=self.apply).pack(side="left", padx=(8, 0))
        help_label = ttk.Label(main, text="Examples: x^2, y/x, y - x. Select a cell to edit; changes save automatically.")
        help_label.pack(anchor="w", fill="x")

        self.board = GridCanvas(layout, self.select, self.SIZE)
        self.board.grid(row=1, column=0, sticky="nsew", pady=16)
        self.board.bind("<Double-Button-1>", lambda event: self.entry.focus_set())
        footer = ttk.Frame(layout)
        footer.grid(row=2, column=0, sticky="ew")
        options = ttk.Frame(footer)
        options.pack(fill="x")
        ttk.Checkbutton(options, text="Show calculated values", variable=self.show_values,
                        command=self.settings_changed).pack(side="left")
        ttk.Button(options, text="Clear cell", command=self.clear_cell).pack(side="right")
        ttk.Button(options, text="Clear grid", command=self.clear_grid).pack(side="right", padx=8)
        detail_label = ttk.Label(footer, textvariable=self.detail)
        detail_label.pack(anchor="w", fill="x", pady=(12, 4))
        status_label = ttk.Label(footer, textvariable=self.status)
        status_label.pack(anchor="w", fill="x")
        storage_label = ttk.Label(footer, textvariable=self.storage_error, foreground="#a02828")
        storage_label.pack(anchor="w", fill="x")
        def wrap_labels(event):
            for label in (help_label, detail_label, status_label, storage_label):
                label.configure(wraplength=max(100, event.width))
        main.bind("<Configure>", wrap_labels)
        footer.bind("<Configure>", wrap_labels)
        self.select(0, 0)
        self.formula.trace_add("write", self.expression_changed)
        self.x_value.trace_add("write", self.settings_changed)
        self.y_value.trace_add("write", self.settings_changed)
        root.update_idletasks()
        # Reserve room for controls even with Windows font/display scaling.
        minimum_height = max(620, main.winfo_reqheight() + footer.winfo_reqheight() + 240)
        root.minsize(620, minimum_height)
        root.geometry(f"760x{max(720, minimum_height)}")

    def load_state(self):
        if not self.STATE_PATH.exists():
            return
        try:
            state = read_state(self.STATE_PATH)
            expressions = state["expressions"]
            x_value, y_value = state.get("x", "1"), state.get("y", "1")
            show_values = state.get("show_values", False)
            if not isinstance(x_value, str) or not isinstance(y_value, str) or type(show_values) is not bool:
                raise ValueError("Invalid saved settings")
            self.expressions = expressions
            self.x_value.set(x_value)
            self.y_value.set(y_value)
            self.show_values.set(show_values)
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.storage_error.set(f"Could not load saved grid: {error}")

    def save_state(self):
        state = {"size": self.SIZE, "expressions": self.expressions, "x": self.x_value.get(),
                 "y": self.y_value.get(), "show_values": self.show_values.get()}
        try:
            write_state(self.STATE_PATH, state)
            self.storage_error.set("")
        except OSError as error:
            self.storage_error.set(f"Could not save grid: {error}")

    def expression_changed(self, *_):
        if not self.loading_formula:
            self.apply()

    def settings_changed(self, *_):
        self.refresh()
        self.save_state()

    def select(self, x, y):
        self.selected = (x, y)
        self.loading_formula = True
        try:
            self.formula.set(self.expressions[y][x])
        finally:
            self.loading_formula = False
        self.selection_label.configure(text=f"Selected cell: row {y + 1}, column {x + 1}")
        self.refresh()

    def apply(self):
        expression = self.formula.get().strip()
        x, y = self.selected
        self.expressions[y][x] = expression
        self.refresh()
        self.save_state()

    def clear_cell(self):
        self.formula.set("")
        self.apply()

    def clear_grid(self):
        self.expressions = [["" for _ in range(self.SIZE)] for _ in range(self.SIZE)]
        self.formula.set("")
        self.refresh()
        self.save_state()

    def refresh(self):
        filled, errors = 0, 0
        cells = []
        variable_error = None
        try:
            global_x = Fraction(self.x_value.get().strip())
            global_y = Fraction(self.y_value.get().strip())
        except (ValueError, ZeroDivisionError):
            variable_error = "Enter numeric values for x and y (for example 3 or 1/2)."
        selected_detail = "Empty cell. Enter an expression or a positive integer."
        for y, row in enumerate(self.expressions):
            for x, expression in enumerate(row):
                text, color = expression, "#ffffff"
                detail = "Empty cell. Enter an expression or a positive integer."
                if expression:
                    filled += 1
                    try:
                        if variable_error:
                            raise ValueError(variable_error)
                        value = evaluate(expression, global_x, global_y)
                        value_text = str(value)
                        detail = f"{expression} = {value_text} with x = {global_x}, y = {global_y}"
                        if value <= 0 or value.denominator != 1:
                            color = "#fff1d6"
                            detail += " • This result is not a positive integer."
                        if self.show_values.get():
                            text = value_text
                    except (ValueError, SyntaxError, ArithmeticError, RecursionError) as error:
                        errors += 1
                        color = "#ffe0e0"
                        detail = f"Cannot calculate {expression}: {error}"
                        if self.show_values.get():
                            text = "Error"
                selected = (x, y) == self.selected
                cells.append((x, y, text, color))
                if selected:
                    selected_detail = detail
        self.detail.set(selected_detail)
        self.board.cells = cells
        self.board.selection = self.selected
        self.board.draw()
        self.status.set(variable_error or
                        f"{filled}/{self.SIZE ** 2} cells filled • {errors} expression errors. "
                        "Amber cells evaluate to fractions, zero, or negative numbers.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Open a named expression grid.")
    parser.add_argument("name", nargs="?", default="example", type=grid_name,
                        help="Grid name (default: example). New names prompt for a size.")
    args = parser.parse_args()
    window = tk.Tk()
    window.withdraw()
    try:
        state_path = prepare_grid(window, args.name)
        if state_path is not None:
            PuzzleApp(window, args.name, state_path)
            window.deiconify()
            window.mainloop()
        else:
            window.destroy()
    except (OSError, ValueError) as error:
        messagebox.showerror("Could not open grid", str(error), parent=window)
        window.destroy()
