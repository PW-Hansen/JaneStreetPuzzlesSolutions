"""Antialiased rendering for the editor and PNG exports."""
import math
from PIL import Image, ImageDraw, ImageFont


def render_grid(state, cell_size, arc_colors=None, region_colors=None, map_mode=False, active_clue=None,
                include_labels=False, area_labels=None):
    """Draw at four times the display resolution for smooth circular edges."""
    scale, margin = 4, 16
    rows, columns = state["rows"], state["columns"]
    width = round(columns * cell_size + 2 * margin)
    height = round(rows * cell_size + 2 * margin)
    image = Image.new("RGB", (width * scale, height * scale), "#e9edf1")
    painter = ImageDraw.Draw(image)

    def box(x0, y0, x1, y1):
        return tuple(round(v * scale) for v in (x0, y0, x1, y1))

    # Paint all backgrounds first so neighboring cells cannot cover arc ends.
    for r, row in enumerate(state["cells"]):
        for c, cell in enumerate(row):
            x, y = margin + c * cell_size, margin + r * cell_size
            painter.rectangle(box(x, y, x + cell_size, y + cell_size),
                              fill=(region_colors or {}).get((r, c, 1 if cell["arc"] else 0),
                                    "#c5e5c8" if cell["green"] else "white"))
            if region_colors is not None and cell["arc"]:
                corner = cell["arc"]
                cx = x + (corner in ("tr", "br")) * cell_size
                cy = y + (corner in ("bl", "br")) * cell_size
                start = {"tl": 0, "tr": 90, "br": 180, "bl": 270}[corner]
                polygon = [(round(cx * scale), round(cy * scale))]
                for step in range(129):
                    angle = math.radians(start + 90 * step / 128)
                    polygon.append((round((cx + cell_size * math.cos(angle)) * scale),
                                    round((cy + cell_size * math.sin(angle)) * scale)))
                painter.polygon(polygon, fill=region_colors.get((r, c, 0), "white"))
            if region_colors is not None and (r, c, 0) in region_colors and cell["green"]:
                # Preserve the puzzle's green-cell markings under the overlay.
                painter.rectangle(box(x + 5, y + 5, x + 11, y + 11),
                                  fill="#83bd8b", outline="#35683c", width=scale)
    for r in range(1, rows):
        y = margin + r * cell_size
        painter.line(box(margin, y, margin + columns * cell_size, y),
                     fill="#89939e", width=scale)
    for c in range(1, columns):
        x = margin + c * cell_size
        painter.line(box(x, margin, x, margin + rows * cell_size),
                     fill="#89939e", width=scale)
    for r, row in enumerate(state["cells"]):
        for c, cell in enumerate(row):
            corner = cell["arc"]
            if corner is None:
                continue
            cx = margin + (c + (corner in ("tr", "br"))) * cell_size
            cy = margin + (r + (corner in ("bl", "br"))) * cell_size
            start = {"tl": 0, "tr": 90, "br": 180, "bl": 270}[corner]
            color = (arc_colors or {}).get((r, c), "black")
            # Pillow's arc stroke lies inside its bounding ellipse, shifting
            # endpoints for different centers. A centered polyline keeps the
            # radius and shared grid-corner endpoints exact.
            points = []
            for step in range(129):
                angle = math.radians(start + 90 * step / 128)
                points.append((round((cx + cell_size * math.cos(angle)) * scale),
                               round((cy + cell_size * math.sin(angle)) * scale)))
            painter.line(points, fill=color, width=3 * scale, joint="curve")
            radius = 1.5 * scale
            for px, py in (points[0], points[-1]):
                painter.ellipse((px - radius, py - radius, px + radius, py + radius),
                                fill=color)
    painter.line([ (round(x * scale), round(y * scale)) for x, y in
                  ((margin, margin), (margin + columns * cell_size, margin),
                   (margin + columns * cell_size, margin + rows * cell_size),
                   (margin, margin + rows * cell_size), (margin, margin))],
                 fill="black", width=4 * scale, joint="curve")
    for r, row in enumerate(state['cells']):
        for c, cell in enumerate(row):
            saved = state.get('saved_analyses', {}).get(f'{r},{c}')
            if cell['number'] is None or saved is None or len(saved['states']) <= 1:
                continue
            cx = margin + (c + .5) * cell_size
            cy = margin + (r + (.16 if map_mode else .5)) * cell_size
            radius = cell_size * (.15 if map_mode else .23)
            painter.ellipse(box(cx - radius, cy - radius, cx + radius, cy + radius),
                            outline='#1769aa', width=2 * scale)
    if active_clue is not None:
        r, c = active_clue
        cx, cy = margin + (c + .5) * cell_size, margin + (r + .5) * cell_size
        radius = cell_size * .42
        painter.ellipse(box(cx - radius, cy - radius, cx + radius, cy + radius),
                        outline='#ef8c00', width=2 * scale)
    if include_labels:
        def font(size, bold=False):
            try:
                return ImageFont.truetype('segoeuib.ttf' if bold else 'segoeui.ttf', round(size * scale))
            except OSError:
                return ImageFont.load_default(size=round(size * scale))
        from functions.arc_constraints import propagate_arc_domains
        domains = propagate_arc_domains(state) if map_mode else None
        for r, row in enumerate(state['cells']):
            for c, cell in enumerate(row):
                x, y = margin + c * cell_size, margin + r * cell_size
                if cell['number'] is not None:
                    painter.text((round((x + cell_size / 2) * scale),
                                  round((y + cell_size * (.16 if map_mode else .5)) * scale)),
                                 str(cell['number']), fill='black', anchor='mm',
                                 font=font(max(10, cell_size * .24), True))
                if map_mode:
                    allowed = domains[(r, c)] if domains is not None else ()
                    for arc, dx, dy in ((None, .5, .5), ('tl', .78, .27), ('tr', .22, .27),
                                        ('br', .22, .76), ('bl', .78, .76)):
                        cx, cy, radius = x + dx * cell_size, y + dy * cell_size, cell_size * .12
                        color = '#172b4d' if arc in allowed else '#c8c8c8'
                        if arc is None:
                            painter.text((round(cx * scale), round(cy * scale)), '—', anchor='mm',
                                         fill=color, font=font(max(9, cell_size * .2), True))
                        else:
                            start = {'tl': 0, 'tr': 90, 'br': 180, 'bl': 270}[arc]
                            points = [(round((cx + radius * math.cos(math.radians(start + step * 7.5))) * scale),
                                       round((cy - radius * math.sin(math.radians(start + step * 7.5))) * scale))
                                      for step in range(13)]
                            painter.line(points, fill=color, width=2 * scale, joint='curve')
                        if arc not in allowed:
                            painter.line(box(cx - radius, cy - radius, cx + radius, cy + radius),
                                         fill='#c84646', width=scale)
        for (r, c, dx, dy, _), label in area_labels or []:
            painter.text((round((margin + (c + dx) * cell_size) * scale),
                          round((margin + (r + dy) * cell_size) * scale)), str(label),
                         fill='#174377', anchor='mm', font=font(max(7, min(11, cell_size * .14))))
    return image.resize((width, height), Image.Resampling.LANCZOS)

