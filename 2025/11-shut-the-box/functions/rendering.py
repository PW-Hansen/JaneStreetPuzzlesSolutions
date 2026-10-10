"""Shared drawing geometry for the interactive grid and PNG export."""
from functools import lru_cache
from math import floor, ceil
from .constants import CELL_SIZE, SHADING, SHAPE_COLOR, SHAPE_SIZE_RATIO, DIGIT_SIZE_RATIO, ANTIALIAS_SCALE, ARROW_PROFILE, ARROW_COLOR


def scene(puzzle, size=CELL_SIZE):
    margin = 3
    items = []
    def add(kind, coords, fill, width=1):
        items.append((kind, coords, fill, width))
    for index, cell in enumerate(puzzle.display_cells()):
        row, col = divmod(index, puzzle.columns)
        x, y = margin + col * size, margin + row * size
        add('rectangle', (x, y, x + size, y + size), SHADING[cell['shading']])
        # Inclusive pixel bounds must have the same integer inset on both sides.
        # This adjusts the diameter slightly instead of rounding each edge separately.
        inset = max(1, round(size * (1 - SHAPE_SIZE_RATIO) / 2))
        if cell['shape']:
            add('oval' if cell['shape'] == 'circle' else 'rectangle',
                (x + inset, y + inset, x + size - inset, y + size - inset), SHAPE_COLOR)
        for direction in cell['arrows']:
            cx, cy = x + size / 2, y + size / 2
            vectors = {'north': (0, -1), 'east': (1, 0), 'south': (0, 1), 'west': (-1, 0)}
            vx, vy = vectors[direction]
            # Stems overlap at the center, forming elbows, tees, or crosses
            # when a cell contains multiple directions, as in the source grid.
            points = tuple(coordinate for along, across in ARROW_PROFILE
                           for coordinate in (cx + size * (vx * along - vy * across),
                                              cy + size * (vy * along + vx * across)))
            add('polygon', points, ARROW_COLOR)
        if cell['digit'] is not None:
            add('text', (x + size / 2, y + size / 2, cell['digit']), '#111111', max(1, round(size * DIGIT_SIZE_RATIO)))
        if puzzle.analysis.sources[index] in ('clue', 'arrow rules'):
            add('line', (x + 3, y + size - 4, x + 7, y + size - 4), '#3377aa')
    w, h = puzzle.columns * size, puzzle.rows * size
    for col in range(1, puzzle.columns):
        add('line', (margin + col * size, margin, margin + col * size, margin + h), '#555555')
    for row in range(1, puzzle.rows):
        add('line', (margin, margin + row * size, margin + w, margin + row * size), '#555555')
    add('outline', (margin, margin, margin + w, margin + h), '#000000', 3)
    if puzzle.selected is not None:
        row, col = divmod(puzzle.selected, puzzle.columns)
        x, y = margin + col * size, margin + row * size
        add('outline', (x + 2, y + 2, x + size - 2, y + size - 2), '#2266cc', 2)
    return items


def draw_canvas(canvas, puzzle, size=CELL_SIZE):
    from PIL import ImageTk
    image = ImageTk.PhotoImage(render_image(puzzle, size), master=canvas)
    canvas.delete('all')
    canvas.create_image(0, 0, image=image, anchor='nw')
    canvas.grid_image = image  # Tk needs a live Python reference to the bitmap.


@lru_cache(maxsize=128)
def smooth_mask(kind, coords):
    """Rasterize a small shape at high resolution, preserving pixel symmetry."""
    from PIL import Image, ImageDraw
    xs, ys = coords[::2], coords[1::2]
    left, top = floor(min(xs)) - 2, floor(min(ys)) - 2
    right, bottom = ceil(max(xs)) + 3, ceil(max(ys)) + 3
    scale = ANTIALIAS_SCALE
    mask = Image.new('L', ((right - left) * scale, (bottom - top) * scale))
    draw = ImageDraw.Draw(mask)
    if kind == 'oval':
        x1, y1, x2, y2 = coords
        # Pillow's ellipse bounds are inclusive. Scale complete pixel extents,
        # so both sides have exactly the same coverage after downsampling.
        draw.ellipse(((x1 - left) * scale, (y1 - top) * scale,
                      (x2 - left + 1) * scale - 1, (y2 - top + 1) * scale - 1), fill=255)
    else:
        points = [((x - left + .5) * scale - .5, (y - top + .5) * scale - .5)
                  for x, y in zip(xs, ys)]
        draw.polygon(points, fill=255)
    return mask.resize((right - left, bottom - top), Image.Resampling.LANCZOS), (left, top)


@lru_cache(maxsize=32)
def digit_font(size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', size)
    except OSError:
        return ImageFont.load_default(size=size)


def render_image(puzzle, size=CELL_SIZE):
    """Use the same antialiased contents and crisp grid for Tk and PNG."""
    from PIL import Image, ImageDraw
    image = Image.new('RGB', (puzzle.columns * size + 7, puzzle.rows * size + 7), 'white')
    draw = ImageDraw.Draw(image)
    for kind, coords, color, width in scene(puzzle, size):
        if kind == 'text':
            font = digit_font(width)
            bounds = font.getbbox(coords[2])
            # Center the visible glyph rather than the font's ascent/descent box.
            position = (coords[0] + .5 - (bounds[0] + bounds[2]) / 2,
                        coords[1] + .5 - (bounds[1] + bounds[3]) / 2)
            draw.text(position, coords[2], fill=color, font=font)
        elif kind == 'outline':
            draw.rectangle(coords, outline=color, width=width)
        elif kind == 'line':
            draw.line(coords, fill=color, width=width)
        elif kind in ('polygon', 'oval'):
            mask, position = smooth_mask(kind, coords)
            image.paste(color, position, mask)
        else:
            getattr(draw, 'ellipse' if kind == 'oval' else 'rectangle')(coords, fill=color)
    return image


def export_png(puzzle, path, size=CELL_SIZE):
    render_image(puzzle, size).save(path, 'PNG')
