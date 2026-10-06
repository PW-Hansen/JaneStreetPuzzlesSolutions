"""Interactive expression grid. Run with: python puzzle_gui.py"""

import ast
import argparse
import json
import operator
import re
import tkinter as tk
import threading
from collections import deque
from decimal import Decimal, localcontext
from queue import Queue, Empty
from fractions import Fraction
from itertools import product
from math import isqrt
from pathlib import Path
from tkinter import font as tkfont, messagebox, simpledialog, ttk


DATA_DIRECTORY = Path(__file__).resolve().parent / "grids"
MIN_CELL_SIZE = 50


def max_region_size(grid_size):
    """Largest n with triangular number n(n + 1)/2 <= grid area."""
    return (isqrt(8 * grid_size * grid_size + 1) - 1) // 2


def variable_name(index):
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("a") + remainder) + name
    return name


def valid_combinations(expressions, bounds, region_limit):
    """Yield valid assignments (or None) so searches can run in UI-sized batches."""
    names = list(bounds)
    for combination in product(*(range(low, high + 1) for low, high in bounds.values())):
        values = dict(zip(names, combination))
        try:
            valid = True
            for expression in expressions:
                value = evaluate(expression, values)
                if value <= 0 or value.denominator != 1 or value > region_limit:
                    valid = False
                    break
        except (ValueError, SyntaxError, ArithmeticError, RecursionError):
            valid = False
        yield values if valid else None


def format_candidates(values):
    """Compact consecutive candidate values into ranges."""
    numbers = sorted(values)
    if not numbers:
        return "None"
    parts = []
    start = previous = numbers[0]
    for value in numbers[1:] + [None]:
        if value is not None and value == previous + 1:
            previous = value
            continue
        parts.append(str(start) if start == previous else f"{start}–{previous}")
        start = previous = value
    return ", ".join(parts)


def can_connect_region(size, labels, number, terminals):
    """Exact bounded connected-set search; other fixed numbers are obstacles."""
    terminals = frozenset(terminals)
    if len(terminals) <= 1:
        return True
    allowed = {i for i in range(size * size) if i not in labels or labels[i] == number}
    neighbors = {}
    for cell in allowed:
        row, column = divmod(cell, size)
        neighbors[cell] = {r * size + c for r, c in
                           ((row-1, column), (row+1, column), (row, column-1), (row, column+1))
                           if 0 <= r < size and 0 <= c < size and r * size + c in allowed}
    distances = {}
    for terminal in terminals:
        distance = {terminal: 0}
        queue = deque([terminal])
        while queue:
            cell = queue.popleft()
            for neighbor in neighbors[cell]:
                if neighbor not in distance:
                    distance[neighbor] = distance[cell] + 1
                    queue.append(neighbor)
        if not terminals <= distance.keys():
            return False
        distances[terminal] = distance
    seen = set()
    stack = [frozenset([min(terminals)])]
    while stack:
        region = stack.pop()
        if region in seen:
            continue
        seen.add(region)
        missing = terminals - region
        if not missing:
            return True
        remaining = number - len(region)
        if len(missing) > remaining or any(
                min(distances[terminal].get(cell, size * size) for cell in region) > remaining
                for terminal in missing):
            continue
        frontier = set().union(*(neighbors[cell] for cell in region)) - region
        for cell in sorted(frontier, key=lambda c: min(distances[t].get(c, size*size) for t in missing), reverse=True):
            stack.append(region | {cell})
    return False


def check_grid_connectivity(expressions, variables):
    size = len(expressions)
    limit = max_region_size(size)
    labels, groups = {}, {}
    for row, cells in enumerate(expressions):
        for column, expression in enumerate(cells):
            if not expression.strip():
                continue
            try:
                value = evaluate(expression, variables)
                if value.denominator != 1 or not 1 <= value <= limit:
                    return False, f"Rejected: row {row+1}, column {column+1} must evaluate to an integer from 1 to {limit}."
            except (ValueError, SyntaxError, ArithmeticError, RecursionError) as error:
                return False, f"Rejected: row {row+1}, column {column+1}: {error}"
            number = int(value)
            cell = row * size + column
            labels[cell] = number
            groups.setdefault(number, []).append(cell)
    # Count all fixed cells before attempting any connectivity search.
    for number, terminals in sorted(groups.items()):
        if len(terminals) > number:
            return False, f"Rejected: {len(terminals)} cells evaluate to {number}; at most {number} are allowed."
    for number, terminals in sorted(groups.items()):
        if not can_connect_region(size, labels, number, terminals):
            return False, f"Rejected: the {number} cells cannot be connected in a region of at most {number} cells."
    return True, "Connectivity check passed. Each value can connect through blank cells within its region size."


def connectivity_candidates(expressions, bounds):
    """Project surviving joint assignments onto each variable's candidate list."""
    flat = [cell for row in expressions for cell in row if cell.strip()]
    values = {name: set() for name in bounds}
    count = 0
    first = None
    for assignment in valid_combinations(flat, bounds, max_region_size(len(expressions))):
        if assignment is None or not check_grid_connectivity(expressions, assignment)[0]:
            continue
        count += 1
        if first is None:
            first = assignment
        for name, value in assignment.items():
            values[name].add(value)
    return count, values, first


def region_completions(size, labels, number):
    """All connected regions of exactly number cells containing its fixed cells."""
    terminals = frozenset(cell for cell, value in labels.items() if value == number)
    if not terminals or len(terminals) > number:
        return []
    allowed = {cell for cell in range(size * size) if cell not in labels or labels[cell] == number}
    neighbors = {cell: {r*size+c for r, c in
                        ((cell//size-1, cell%size), (cell//size+1, cell%size),
                         (cell//size, cell%size-1), (cell//size, cell%size+1))
                        if 0 <= r < size and 0 <= c < size and r*size+c in allowed}
                 for cell in allowed}
    seen, completed = set(), []
    stack = [frozenset([min(terminals)])]
    while stack:
        region = stack.pop()
        if region in seen:
            continue
        seen.add(region)
        if len(terminals - region) > number - len(region):
            continue
        if len(region) == number:
            if terminals <= region:
                completed.append(region)
            continue
        frontier = set().union(*(neighbors[cell] for cell in region)) - region
        for cell in frontier:
            stack.append(region | {cell})
    return completed


def canonical_shape(cells, size):
    """Translation-independent shape, allowing all rotations and reflections."""
    points = [divmod(cell, size) for cell in cells]
    shapes = []
    for swap in (False, True):
        for row_sign in (-1, 1):
            for column_sign in (-1, 1):
                transformed = [(row_sign*(c if swap else r), column_sign*(r if swap else c))
                               for r, c in points]
                min_row = min(r for r, c in transformed)
                min_column = min(c for r, c in transformed)
                shapes.append(tuple(sorted((r-min_row, c-min_column) for r, c in transformed)))
    return min(shapes)


def filter_containment(options, size):
    """Enforce adjacent-size shape support, processing largest sizes first."""
    shapes = {region: canonical_shape(region, size)
              for regions in options.values() for region in regions}
    contained = {region: {canonical_shape(region - {cell}, size) for cell in region}
                 for number, regions in options.items() if number > 1 for region in regions}
    while True:
        changed = False
        for number in sorted(options, reverse=True):
            if number - 1 not in options:
                continue
            bigger, smaller = options[number], options[number-1]
            supported_big, supported_small = set(), set()
            for big in bigger:
                for small in smaller:
                    if big.isdisjoint(small) and shapes[small] in contained[big]:
                        supported_big.add(big)
                        supported_small.add(small)
            if not supported_big or not supported_small:
                raise ValueError(f"Regions {number} and {number-1} cannot satisfy shape containment.")
            new_big = [region for region in bigger if region in supported_big]
            new_small = [region for region in smaller if region in supported_small]
            changed |= len(new_big) != len(bigger) or len(new_small) != len(smaller)
            options[number], options[number-1] = new_big, new_small
        if not changed:
            return options


def grow_forced_regions(expressions, variables, use_containment=True):
    passed, message = check_grid_connectivity(expressions, variables)
    if not passed:
        raise ValueError(message)
    size = len(expressions)
    labels = {r*size+c: int(evaluate(expression, variables))
              for r, row in enumerate(expressions) for c, expression in enumerate(row)
              if expression.strip()}
    original = dict(labels)
    while True:
        forced = {}
        candidates = {}
        for number in sorted(set(labels.values())):
            options = region_completions(size, labels, number)
            candidates[number] = options
            if not options:
                raise ValueError(f"Region {number} has no connected completion of size {number}.")
            mandatory = set.intersection(*(set(option) for option in options))
            for cell in mandatory - labels.keys():
                if cell in forced and forced[cell] != number:
                    raise ValueError("Different regions require the same blank cell.")
                forced[cell] = number
        if not forced:
            if not use_containment:
                return labels, len(labels) - len(original)
            candidates = filter_containment(candidates, size)
            for number in sorted(candidates, reverse=True):
                mandatory = set.intersection(*(set(option) for option in candidates[number]))
                for cell in mandatory - labels.keys():
                    if cell in forced and forced[cell] != number:
                        raise ValueError("Different regions require the same blank cell.")
                    forced[cell] = number
            if not forced:
                return labels, len(labels) - len(original)
            # Restart ordinary connected-region deductions before another
            # largest-to-smallest containment pass.
        labels.update(forced)


def region_colors(size, labels):
    """Greedy coloring of the region adjacency graph, with preferred colors."""
    palette = ['#f6d797', '#cab5ec', '#9cd7ed', '#efa5a5', '#efc394', '#a9d8af',
               '#e7afd4', '#b8c9ef', '#d9d79f']
    adjacency = {number: set() for number in labels.values()}
    for cell, number in labels.items():
        row, column = divmod(cell, size)
        for neighbor in (cell+1 if column+1 < size else -1,
                         cell+size if row+1 < size else -1):
            if neighbor in labels and labels[neighbor] != number:
                adjacency[number].add(labels[neighbor])
                adjacency[labels[neighbor]].add(number)
    colors = {}
    for number in sorted(adjacency):
        used = {colors[neighbor] for neighbor in adjacency[number] if neighbor in colors}
        preferred = palette[(number-1) % len(palette)]
        choices = [preferred] + palette
        color = next((color for color in choices if color not in used), None)
        if color is None:
            # A distinct fallback also handles grids with many touching regions.
            color = f"#{(number * 2654435761) & 0xffffff:06x}"
            while color in used:
                color = f"#{(int(color[1:], 16)+1) & 0xffffff:06x}"
        colors[number] = color
    return colors


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
    variables = state.get("variables", {})
    if (not isinstance(variables, dict)
            or any(not isinstance(name, str) or not re.fullmatch(r"[a-z]+", name)
                   or not isinstance(value, str) for name, value in variables.items())
            or type(state.get("show_values", False)) is not bool):
        raise ValueError("Invalid saved settings")
    state["size"] = size
    bounds = state.get("bounds", {})
    if (not isinstance(bounds, dict)
            or any(not isinstance(value, dict)
                   or not isinstance(value.get("min"), str)
                   or not isinstance(value.get("max"), str) for value in bounds.values())):
        raise ValueError("Invalid saved variable bounds")
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


def display_expression(expression):
    """Use compact mathematical notation without changing the stored input."""
    expression = re.sub(r"\s*(?:\^|\*\*)\s*(-?\d+)",
                        lambda match: match[1].translate(str.maketrans(
                            "0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")), expression)
    expression = re.sub(r"(?<=\d)\s*\*\s*(?=[a-z])", "", expression)
    return expression.replace("sqrt(", "√(").replace("cbrt(", "∛(").replace("**", "^").replace("-", "−").replace("*", "·")


def fraction_parts(expression):
    """Split a top-level quotient without changing its mathematical meaning."""
    try:
        node = ast.parse(expression.replace("^", "**"), mode="eval").body
    except (SyntaxError, ValueError):
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return inline_math(ast.unparse(node.left)), inline_math(ast.unparse(node.right))
    return None


def inline_math(expression):
    """Replace divisions anywhere in an expression with layout markers."""
    try:
        tree = ast.parse(expression.replace("^", "**"), mode="eval")
    except (ValueError, SyntaxError):
        return display_expression(expression)
    replacements = {}
    class Fractions(ast.NodeTransformer):
        def visit_Call(self, node):
            node = self.generic_visit(node)
            if (isinstance(node.func, ast.Name) and re.fullmatch(r"log_([a-z]+|\d+)", node.func.id)
                    and len(node.args) == 1 and not node.keywords):
                name = f"__fraction_{len(replacements)}__"
                replacements[name] = "〔" + node.func.id[4:] + "¦" + ast.unparse(node.args[0]) + "〕"
                return ast.copy_location(ast.Name(id=name, ctx=ast.Load()), node)
            return node
        def visit_BinOp(self, node):
            node = self.generic_visit(node)
            if isinstance(node.op, ast.Div):
                name = f"__fraction_{len(replacements)}__"
                replacements[name] = "⟦" + ast.unparse(node.left) + "¦" + ast.unparse(node.right) + "⟧"
                return ast.copy_location(ast.Name(id=name, ctx=ast.Load()), node)
            if isinstance(node.op, ast.Pow):
                name = f"__fraction_{len(replacements)}__"
                base = ast.unparse(node.left)
                if isinstance(node.left, (ast.BinOp, ast.UnaryOp)) or (
                        isinstance(node.left, ast.Name) and node.left.id in replacements):
                    base = "(" + base + ")"
                replacements[name] = "〖" + base + "¦" + ast.unparse(node.right) + "〗"
                return ast.copy_location(ast.Name(id=name, ctx=ast.Load()), node)
            return node
    text = ast.unparse(Fractions().visit(tree))
    for name, replacement in reversed(list(replacements.items())):
        text = text.replace(name, replacement)
    return display_expression(text)


def math_runs(text):
    """Separate radical arguments from surrounding text, including nested roots."""
    runs = []
    while text:
        root_start, cube_start, fraction_start, power_start, log_start = text.find("√("), text.find("∛("), text.find("⟦"), text.find("〖"), text.find("〔")
        candidates = [start for start in (root_start, cube_start, fraction_start, power_start, log_start) if start >= 0]
        start = min(candidates) if candidates else -1
        if start < 0:
            runs.append(("text", text))
            break
        is_fraction = start == fraction_start
        is_power = start == power_start
        is_log = start == log_start
        paired = is_fraction or is_power or is_log
        opening, closing = ("⟦", "⟧") if is_fraction else ("〖", "〗") if is_power else ("〔", "〕") if is_log else ("(", ")")
        depth, end = 1, start + (1 if paired else 2)
        separator = None
        while end < len(text) and depth:
            if paired and text[end] == "¦" and depth == 1:
                separator = end
            depth += (text[end] == opening) - (text[end] == closing)
            end += 1
        if depth:
            runs.append(("text", text))
            break
        if start:
            runs.append(("text", text[:start]))
        if paired:
            runs.append(("fraction" if is_fraction else "power" if is_power else "log", (math_runs(text[start+1:separator]), math_runs(text[separator+1:end-1]))))
        else:
            runs.append(("cube_root" if start == cube_start else "root", math_runs(text[start+2:end-1])))
        text = text[end:]
    return runs


def math_width(runs, font):
    return sum(font.measure(value) if kind == "text" else
               max(math_width(part, font) for part in value) + 6 if kind == "fraction" else
               math_width(value[0], font) + 0.85 * math_width(value[1], font) if kind == "power" else
               font.measure("log ") + 0.85 * math_width(value[0], font) + math_width(value[1], font) if kind == "log" else
               font.measure("3")*0.55 + font.measure("√") + 4 + math_width(value, font) if kind == "cube_root" else
               font.measure("√") + 4 + math_width(value, font) for kind, value in runs)


def draw_math(canvas, center_x, center_y, text, font):
    runs = math_runs(text)
    font_spec = ("Times New Roman", font.cget("size"), "italic")
    height = font.metrics("linespace")
    def draw(parts, left, y, scale=1):
        font_spec = ("Times New Roman", max(6, round(font.cget("size")*scale)), "italic")
        local_height = height * scale
        for kind, value in parts:
            if kind == "text":
                canvas.create_text(left, y, text=value, anchor="w", font=font_spec, fill="#252525")
                left += font.measure(value) * scale
            elif kind == "power":
                base_width = math_width(value[0], font) * scale
                draw(value[0], left, y, scale)
                draw(value[1], left+base_width, y-local_height*0.42, scale*0.85)
                left += base_width + math_width(value[1], font)*scale*0.85
            elif kind == "log":
                canvas.create_text(left, y, text="log", anchor="w",
                                   font=("Times New Roman", max(6, round(font.cget("size")*scale))), fill="#252525")
                left += font.measure("log")*scale
                draw(value[0], left, y+local_height*0.3, scale*0.85)
                left += math_width(value[0], font)*scale*0.85 + font.measure(" ")*scale
                draw(value[1], left, y, scale)
                left += math_width(value[1], font)*scale
            elif kind == "fraction":
                width = (max(math_width(part, font) for part in value) + 6)*scale
                for part, offset in ((value[0], -local_height*0.8), (value[1], local_height*0.8)):
                    draw(part, left+(width-math_width(part, font)*scale)/2, y+offset, scale)
                canvas.create_line(left, y, left+width, y, fill="#252525", width=1)
                left += width
            else:
                if kind == "cube_root":
                    canvas.create_text(left, y-local_height*0.48, text="3", anchor="w",
                                       font=("Times New Roman", max(6, round(font.cget("size")*scale*0.65))), fill="#252525")
                    left += font.measure("3")*scale*0.55
                root_width = font.measure("√")*scale
                argument_width = math_width(value, font)*scale
                # Draw the radical and vinculum as one continuous stroke.
                bar_y = y - local_height * 0.46
                canvas.create_line(left, y, left+root_width*0.28, y-local_height*0.08,
                                   left+root_width*0.52, y+local_height*0.35,
                                   left+root_width, bar_y,
                                   left+root_width+argument_width+4, bar_y,
                                   fill="#252525", width=1)
                draw(value, left+root_width+2, y, scale)
                left += root_width+argument_width+4
        return left
    draw(runs, center_x - math_width(runs, font)/2, center_y)


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


OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}


def evaluate(expression, variables):
    """Evaluate arithmetic only, keeping rational results exact."""
    if len(expression) > 200:
        raise ValueError("Expression is too long")
    tree = ast.parse(expression.replace("^", "**"), mode="eval")

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return Fraction(str(node.value))
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ValueError(f"Unknown variable: {node.id}")
            return Fraction(variables[node.id])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "cbrt" and len(node.args) == 1 and not node.keywords):
            value = visit(node.args[0])
            if isinstance(value, Fraction):
                def integer_cube_root(number):
                    low, high = 0, 1 << ((number.bit_length()+2)//3)
                    while low < high:
                        middle = (low+high+1)//2
                        if middle**3 <= number:
                            low = middle
                        else:
                            high = middle-1
                    return low
                numerator = integer_cube_root(abs(value.numerator))
                denominator = integer_cube_root(value.denominator)
                if numerator**3 == abs(value.numerator) and denominator**3 == value.denominator:
                    return Fraction(numerator if value >= 0 else -numerator, denominator)
            with localcontext() as context:
                context.prec = 80
                decimal = Decimal(value.numerator)/Decimal(value.denominator) if isinstance(value, Fraction) else value
                if not decimal:
                    return Fraction(0)
                root = (abs(decimal).ln()/Decimal(3)).exp()
                return root if decimal > 0 else -root
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and re.fullmatch(r"log_([a-z]+|\d+)", node.func.id)
                and len(node.args) == 1 and not node.keywords):
            base_name = node.func.id[4:]
            if base_name.isdigit():
                base = Fraction(int(base_name))
            elif base_name in variables:
                base = Fraction(variables[base_name])
            else:
                raise ValueError(f"Unknown logarithm base variable: {base_name}")
            argument = visit(node.args[0])
            if base <= 0 or base == 1 or argument <= 0:
                raise ValueError("Logarithms require a positive argument and a positive base different from 1")
            with localcontext() as context:
                context.prec = 80
                base_decimal = Decimal(base.numerator)/Decimal(base.denominator)
                argument_decimal = Decimal(argument.numerator)/Decimal(argument.denominator) if isinstance(argument, Fraction) else argument
                return argument_decimal.ln()/base_decimal.ln()
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "sqrt" and len(node.args) == 1 and not node.keywords):
            value = visit(node.args[0])
            if value < 0:
                raise ValueError("sqrt requires a nonnegative argument")
            if isinstance(value, Fraction):
                numerator, denominator = isqrt(value.numerator), isqrt(value.denominator)
                if numerator*numerator == value.numerator and denominator*denominator == value.denominator:
                    return Fraction(numerator, denominator)
            with localcontext() as context:
                context.prec = 80
                decimal = (Decimal(value.numerator)/Decimal(value.denominator)
                           if isinstance(value, Fraction) else value)
                return decimal.sqrt()
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow):
                if right != int(right) or abs(right) > 20:
                    raise ValueError("Powers require an integer exponent from -20 to 20")
                right = int(right)
            if isinstance(left, Decimal) or isinstance(right, Decimal):
                with localcontext() as context:
                    context.prec = 80
                    left = Decimal(left.numerator)/Decimal(left.denominator) if isinstance(left, Fraction) else left
                    right = Decimal(right.numerator)/Decimal(right.denominator) if isinstance(right, Fraction) else right
                    result = OPERATORS[type(node.op)](left, right)
            else:
                result = OPERATORS[type(node.op)](left, right)
            if isinstance(result, Decimal):
                return result
            result = Fraction(result)
            if result.numerator.bit_length() > 4096 or result.denominator.bit_length() > 4096:
                raise ValueError("Result is too large")
            return result
        raise ValueError("Use numbers, defined variables, parentheses, and arithmetic operators only")

    with localcontext() as context:
        context.prec = 80
        result = visit(tree.body)
        if isinstance(result, Decimal):
            nearest = result.to_integral_value()
            if abs(result - nearest) < Decimal("1e-60"):
                return Fraction(int(nearest))
            return Fraction(result)
        return result


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
        self.variables = {}
        self.bounds = {}
        self.valid_values = {}
        self.search_job = None
        self.search_revision = 0
        self.search_message = tk.StringVar(value="Set integer bounds, then compute valid values.")
        self.connectivity_message = tk.StringVar()
        self.region_labels = {}
        self.region_palette = {}
        self.region_message = tk.StringVar()
        self.storage_error = tk.StringVar()
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
        sidebar = ttk.Frame(body)
        sidebar.grid(row=0, column=1, rowspan=2, sticky="nsew")
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(0, weight=1)
        scroll_variables = len(self.variables) > 3
        if scroll_variables:
            variable_canvas = tk.Canvas(sidebar, width=750, height=280,
                                        bg="#f4f6fa", highlightthickness=0)
            variable_canvas.grid(row=0, column=0, sticky="nsew")
            scrollbar = ttk.Scrollbar(sidebar, orient="vertical", command=variable_canvas.yview)
            scrollbar.grid(row=0, column=1, sticky="ns")
            horizontal_scrollbar = ttk.Scrollbar(sidebar, orient="horizontal", command=variable_canvas.xview)
            horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
            variable_canvas.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal_scrollbar.set)
            panel = ttk.Frame(variable_canvas)
            variable_canvas.create_window(0, 0, window=panel, anchor="nw")
            panel.bind("<Configure>", lambda event: variable_canvas.configure(scrollregion=variable_canvas.bbox("all")))
        else:
            panel = ttk.Frame(sidebar)
            panel.grid(row=0, column=0, sticky="new")
        ttk.Label(panel, text="Variables", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        for column, (name, variable) in enumerate(self.variables.items()):
            panel.columnconfigure(column, minsize=250)
            field = ttk.LabelFrame(panel, text=name, padding=10)
            field.grid(row=1, column=column, sticky="new", padx=(0, 10), pady=(0, 10))
            field.columnconfigure(1, weight=1)
            for row, (label, value) in enumerate((("Candidate", variable),
                                                  ("Min", self.bounds[name]["min"]),
                                                  ("Max", self.bounds[name]["max"]))):
                ttk.Label(field, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
                ttk.Entry(field, textvariable=value, width=10).grid(row=row, column=1, sticky="ew", pady=3)
            self.valid_values[name] = tk.StringVar(value="Not computed")
            ttk.Label(field, text="Valid values").grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
            ttk.Label(field, textvariable=self.valid_values[name], wraplength=210).grid(row=4, column=0, columnspan=2, sticky="w")
        self.compute_button = ttk.Button(panel, text="Compute valid values", command=self.compute_valid_values)
        self.compute_button.grid(row=2, column=0, sticky="ew", padx=(0, 10), pady=(0, 8))
        ttk.Label(panel, textvariable=self.search_message, wraplength=230).grid(row=3, column=0, sticky="nw", padx=(0, 10))
        self.connectivity_button = ttk.Button(panel, text="Check connectivity", command=self.check_connectivity)
        self.connectivity_button.grid(row=4, column=0, sticky="ew", padx=(0, 10), pady=(12, 8))
        ttk.Label(panel, textvariable=self.connectivity_message, wraplength=230).grid(row=5, column=0, sticky="nw", padx=(0, 10))
        self.region_button = ttk.Button(panel, text="Create regions", command=self.create_regions)
        self.region_button.grid(row=6, column=0, sticky="ew", padx=(0, 10), pady=(12, 8))
        ttk.Label(panel, textvariable=self.region_message, wraplength=230).grid(row=7, column=0, sticky="nw", padx=(0, 10))
        footer = ttk.Frame(body)
        footer.grid(row=1, column=0, sticky="ew", padx=(0, 20))
        options = ttk.Frame(footer)
        options.pack(fill="x")
        self.display_button = ttk.Button(options, command=self.toggle_display)
        self.display_button.pack(side="left")
        self.update_display_button()
        detail_label = ttk.Label(footer, textvariable=self.detail)
        detail_label.pack(anchor="w", fill="x", pady=(12, 4))
        status_label = ttk.Label(footer, textvariable=self.status)
        status_label.pack(anchor="w", fill="x")
        storage_label = ttk.Label(footer, textvariable=self.storage_error, foreground="#a02828")
        storage_label.pack(anchor="w", fill="x")
        def wrap_grid_labels(event):
            width = max(100, min(self.board.winfo_width(), self.board.winfo_height()) - 8)
            for label in (detail_label, status_label, storage_label):
                if int(float(label.cget("wraplength"))) != width:
                    label.configure(wraplength=width)
        self.board.bind("<Configure>", wrap_grid_labels, add="+")
        main.bind("<Configure>", lambda event: help_label.configure(wraplength=max(100, event.width)))
        # Messages can add lines after a search finishes. Recalculate the
        # minimum height so the sidebar's last button never gets clipped.
        resize_pending = [False]
        def fit_contents():
            resize_pending[0] = False
            left_height = minimum_board + 32 + footer.winfo_reqheight()
            right_height = 240 if scroll_variables else panel.winfo_reqheight()
            height = max(620, main.winfo_reqheight() + max(left_height, right_height) + 80)
            width = max(820, sidebar.winfo_reqwidth() + minimum_board + 68)
            root.minsize(width, height)
        def schedule_fit(event=None):
            if not resize_pending[0]:
                resize_pending[0] = True
                root.after_idle(fit_contents)
        footer.bind("<Configure>", schedule_fit)
        panel.bind("<Configure>", schedule_fit, add="+")
        main.bind("<Configure>", schedule_fit, add="+")
        for message in (self.search_message, self.connectivity_message, self.region_message,
                        self.detail, self.status, self.storage_error):
            message.trace_add("write", lambda *_: schedule_fit())
        self.select(0, 0)
        for variable in self.variables.values():
            variable.trace_add("write", self.settings_changed)
        for bound in self.bounds.values():
            for value in bound.values():
                value.trace_add("write", self.bounds_changed)
        root.update_idletasks()
        # Reserve room for controls even with Windows font/display scaling.
        body_height = max(minimum_board + 32 + footer.winfo_reqheight(),
                          240 if scroll_variables else panel.winfo_reqheight())
        minimum_height = max(620, main.winfo_reqheight() + body_height + 80)
        minimum_width = max(820, sidebar.winfo_reqwidth() + minimum_board + 68)
        root.minsize(minimum_width, minimum_height)
        root.geometry(f"{max(940, minimum_width + 60)}x{max(760, minimum_height)}")

    def load_state(self):
        if not self.STATE_PATH.exists():
            return
        try:
            state = read_state(self.STATE_PATH)
            expressions = state["expressions"]
            show_values = state.get("show_values", False)
            self.expressions = expressions
            self.variables = {name: tk.StringVar(value=value) for name, value in state["variables"].items()}
            default_max = str(max_region_size(self.SIZE))
            self.bounds = {
                name: {key: tk.StringVar(value=state.get("bounds", {}).get(name, {}).get(key, default))
                       for key, default in (("min", "1"), ("max", default_max))}
                for name in self.variables}
            self.show_values.set(show_values)
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.storage_error.set(f"Could not load saved grid: {error}")

    def save_state(self):
        state = {"size": self.SIZE, "expressions": self.expressions,
                 "variables": {name: value.get() for name, value in self.variables.items()},
                 "bounds": {name: {key: value.get() for key, value in bound.items()}
                            for name, bound in self.bounds.items()},
                 "show_values": self.show_values.get()}
        try:
            write_state(self.STATE_PATH, state)
            self.storage_error.set("")
        except OSError as error:
            self.storage_error.set(f"Could not save grid: {error}")

    def settings_changed(self, *_):
        if _:
            self.clear_regions()
        self.connectivity_message.set("")
        self.refresh()
        self.save_state()

    def update_display_button(self):
        self.display_button.configure(text="Prioritize equations" if self.show_values.get()
                                      else "Prioritize values")

    def toggle_display(self):
        self.show_values.set(not self.show_values.get())
        self.update_display_button()
        self.refresh()
        self.save_state()

    def invalidate_search(self):
        self.search_revision += 1
        self.search_job = None
        self.compute_button.configure(text="Compute valid values")
        for value in self.valid_values.values():
            value.set("Not computed")
        self.search_message.set("Grid or bounds changed. Compute valid values again.")

    def bounds_changed(self, *_):
        self.invalidate_search()
        self.save_state()

    def compute_valid_values(self):
        self.search_revision += 1
        if self.search_job is not None:
            self.invalidate_search()
            self.search_message.set("Search cancelled.")
            return
        try:
            bounds = {}
            total = 1
            for name, fields in self.bounds.items():
                low, high = int(fields["min"].get()), int(fields["max"].get())
                if low > high:
                    raise ValueError(f"{name}: Min must not exceed Max.")
                bounds[name] = (low, high)
                total *= high - low + 1
            expressions = [cell for row in self.expressions for cell in row if cell.strip()]
            # Reject syntax mistakes and unknown names before enumerating candidates.
            for expression in expressions:
                tree = ast.parse(expression.replace("^", "**"), mode="eval")
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name) and node.id not in bounds and node.id not in ("sqrt", "cbrt"):
                        match = re.fullmatch(r"log_([a-z]+|\d+)", node.id)
                        if not match or (not match[1].isdigit() and match[1] not in bounds):
                            raise ValueError(f"Unknown variable: {node.id}")
        except (ValueError, SyntaxError) as error:
            self.search_message.set(str(error))
            return
        job = {"iterator": valid_combinations(expressions, bounds, max_region_size(self.SIZE)), "total": total,
               "checked": 0, "count": 0, "values": {name: set() for name in bounds}, "first": None}
        self.search_job = job
        for value in self.valid_values.values():
            value.set("Searching…")
        self.compute_button.configure(text="Cancel search")
        self.search_step(job)

    def search_step(self, job):
        if self.search_job is not job:
            return
        for _ in range(100):
            try:
                assignment = next(job["iterator"])
            except StopIteration:
                self.search_job = None
                self.compute_button.configure(text="Compute valid values")
                for name, values in job["values"].items():
                    self.valid_values[name].set(format_candidates(values))
                message = f"{job['count']} valid combinations within these bounds."
                if job["first"] is not None and job["first"]:
                    message += " Example: " + ", ".join(f"{name}={value}" for name, value in job["first"].items()) + "."
                    message += " Listed values must be used in a valid combination."
                self.search_message.set(message)
                return
            job["checked"] += 1
            if assignment is not None:
                job["count"] += 1
                if job["first"] is None:
                    job["first"] = assignment
                for name, value in assignment.items():
                    job["values"][name].add(value)
        self.search_message.set(f"Checked {job['checked']:,} of {job['total']:,} combinations…")
        self.root.after(1, lambda: self.search_step(job))

    def select(self, x, y):
        self.selected = (x, y)
        self.formula.set(self.expressions[y][x])
        self.selection_label.configure(text=f"Selected cell: row {y + 1}, column {x + 1}")
        self.refresh()

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
        expressions = [row[:] for row in self.expressions]
        try:
            variables = {name: Fraction(value.get().strip()) for name, value in self.variables.items()}
            bounds = {name: (int(fields["min"].get()), int(fields["max"].get()))
                      for name, fields in self.bounds.items()}
            if any(low > high for low, high in bounds.values()):
                raise ValueError("Min exceeds Max")
        except (ValueError, ZeroDivisionError):
            self.connectivity_message.set("Enter numeric candidates and integer bounds with Min ≤ Max.")
            return
        if self.search_job is not None:
            self.invalidate_search()
        revision = self.search_revision
        self.connectivity_button.configure(state="disabled")
        self.connectivity_message.set("Checking connectivity…")
        results = Queue()
        def work():
            try:
                message = check_grid_connectivity(expressions, variables)[1]
                results.put((message, connectivity_candidates(expressions, bounds)))
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
            if revision != self.search_revision or expressions != self.expressions:
                self.connectivity_message.set("Grid, bounds, or search changed. Check connectivity again.")
                return
            if filtered is not None:
                count, values, first = filtered
                for name, candidates in values.items():
                    self.valid_values[name].set(format_candidates(candidates))
                summary = f"{count} combinations pass connectivity within these bounds."
                if first:
                    summary += " Example: " + ", ".join(f"{name}={value}" for name, value in first.items()) + "."
                self.search_message.set(summary)
            try:
                current = {name: Fraction(value.get().strip()) for name, value in self.variables.items()}
            except (ValueError, ZeroDivisionError):
                current = None
            if expressions != self.expressions or current != variables:
                message = "Candidates or grid changed. Check connectivity again."
            self.connectivity_message.set(message)
        self.root.after(50, poll)

    def clear_regions(self):
        self.region_labels = {}
        self.region_palette = {}
        self.region_message.set("")

    def create_regions(self):
        expressions = [row[:] for row in self.expressions]
        try:
            variables = {name: Fraction(value.get().strip()) for name, value in self.variables.items()}
        except (ValueError, ZeroDivisionError):
            self.region_message.set("Enter numeric candidate values first.")
            return
        self.region_button.configure(state="disabled")
        self.region_message.set("Finding forced cells…")
        results = Queue()
        def work():
            try:
                results.put((grow_forced_regions(expressions, variables), None))
            except Exception as error:
                results.put((None, str(error)))
        threading.Thread(target=work, daemon=True).start()
        def poll():
            try:
                result, error = results.get_nowait()
            except Empty:
                self.root.after(50, poll)
                return
            self.region_button.configure(state="normal")
            try:
                current = {name: Fraction(value.get().strip()) for name, value in self.variables.items()}
            except (ValueError, ZeroDivisionError):
                current = None
            if expressions != self.expressions or variables != current:
                self.region_message.set("Grid or candidates changed. Create regions again.")
                return
            self.clear_regions()
            if error:
                self.region_message.set(error)
                self.refresh()
                return
            self.region_labels, added = result
            self.region_palette = region_colors(self.SIZE, self.region_labels)
            self.region_message.set(f"Added {added} forced cells. Ambiguous cells remain blank.")
            self.refresh()
        self.root.after(50, poll)

    def refresh(self):
        filled, errors = 0, 0
        cells = []
        variable_error = None
        try:
            values = {name: Fraction(variable.get().strip()) for name, variable in self.variables.items()}
        except (ValueError, ZeroDivisionError):
            variable_error = "Enter numeric values for all variables (for example 3 or 1/2)."
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
