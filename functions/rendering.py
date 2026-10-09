"""Shared layout for canvas rendering, hit testing, and PNG export."""

from functions.constants import CELL_SIZE, PADDING, THICK_WIDTH, PROJECT_ROOT
from functions.state import edge_key, valid_name
from functions.regions import tower_colors


def dimensions(grid):
    return (grid["columns"] * CELL_SIZE + 2 * PADDING,
            grid["rows"] * CELL_SIZE + 2 * PADDING)


def cell_at(grid, x, y):
    row, column = int((y - PADDING) // CELL_SIZE), int((x - PADDING) // CELL_SIZE)
    return (row, column) if 0 <= row < grid["rows"] and 0 <= column < grid["columns"] else None


def edge_at(grid, x, y):
    gx, gy = (x - PADDING) / CELL_SIZE, (y - PADDING) / CELL_SIZE
    column, row = round(gx), round(gy)
    options = []
    if 0 < column < grid["columns"] and 0 <= gy < grid["rows"]:
        r = int(gy)
        options.append((abs(gx - column), edge_key((r, column - 1), (r, column))))
    if 0 < row < grid["rows"] and 0 <= gx < grid["columns"]:
        c = int(gx)
        options.append((abs(gy - row), edge_key((row - 1, c), (row, c))))
    if options:
        distance, edge = min(options)
        if distance * CELL_SIZE <= 8:
            return edge
    return None


def primitives(session):
    """Yield rectangles, lines and text in drawing order."""
    grid = session.grid
    pad, size = PADDING, CELL_SIZE
    if session.mode == "Tower":
        for (r, c), color in tower_colors(grid).items():
            x, y = pad + c * size, pad + r * size
            yield "rectangle", (x, y, x + size, y + size), {"fill": color, "outline": ""}
    if session.selected is not None and session.mode != "Tower":
        r, c = session.selected
        x, y = pad + c * size, pad + r * size
        yield "rectangle", (x + 2, y + 2, x + size - 2, y + size - 2), {"fill": "#fff3cd", "outline": ""}
    for r in range(grid["rows"]):
        for c in range(grid["columns"]):
            x, y = pad + c * size, pad + r * size
            score, visit = grid["scores"][r][c], grid["visits"][r][c]
            main, corner = (visit, score) if session.mode == "Visit number" else (score, visit)
            if main is not None:
                yield "text", (x + size / 2, y + size / 2), {"text": str(main), "size": 20, "anchor": "center"}
            if corner is not None:
                left = session.mode == "Visit number"
                yield "text", (x + 7 if left else x + size - 7, y + 6), {"text": str(corner), "size": 11, "anchor": "nw" if left else "ne"}
    for r, c in grid.get("towers", []):
        x, y = pad + c * size, pad + r * size
        yield "line", (x + 18, y + 8, x + size - 18, y + 8), {"fill": "black", "width": 2}
    for r, c in grid.get("non_towers", []):
        x, y = pad + c * size, pad + r * size
        yield "line", (x + 18, y + size - 8, x + size - 18, y + size - 8), {"fill": "black", "width": 2}
    borders = {tuple(edge) for edge in grid["borders"]}
    for r in range(grid["rows"]):
        for c in range(grid["columns"]):
            x, y = pad + c * size, pad + r * size
            for neighbor, line in (((r, c + 1), (x + size, y, x + size, y + size)),
                                   ((r + 1, c), (x, y + size, x + size, y + size))):
                if neighbor[0] >= grid["rows"] or neighbor[1] >= grid["columns"]:
                    continue
                thick = tuple(edge_key((r, c), neighbor)) in borders
                yield "line", line, {"fill": "black" if thick else "#b0b0b0", "width": THICK_WIDTH if thick else 1}
    yield "rectangle", (pad, pad, pad + grid["columns"] * size, pad + grid["rows"] * size), {"outline": "black", "width": THICK_WIDTH}
    if session.selected is not None:
        r, c = session.selected
        x, y = pad + c * size, pad + r * size
        yield "rectangle", (x + 4, y + 4, x + size - 4, y + size - 4), {"outline": "#d97706", "width": 2}


def draw_grid(canvas, session):
    canvas.delete("grid")
    for kind, coordinates, style in primitives(session):
        style = dict(style)
        if kind == "text":
            style["font"] = ("Segoe UI", style.pop("size"))
        getattr(canvas, "create_" + kind)(*coordinates, tags="grid", **style)


def export_png(session, name):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", dimensions(session.grid), "white")
    draw = ImageDraw.Draw(image)
    for kind, coordinates, style in primitives(session):
        if kind == "text":
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", round(style["size"] * 96 / 72))
            except OSError:
                font = ImageFont.load_default(size=style["size"])
            anchor = {"center": "mm", "nw": "lt", "ne": "rt"}[style["anchor"]]
            draw.text(coordinates, style["text"], fill="black", font=font, anchor=anchor)
        elif kind == "line":
            draw.line(coordinates, fill=style["fill"], width=style["width"])
        else:
            draw.rectangle(coordinates, fill=style.get("fill"), outline=style.get("outline") or None,
                           width=style.get("width", 1))
    path = PROJECT_ROOT / (valid_name(name) + ".png")
    image.save(path)
    return path
