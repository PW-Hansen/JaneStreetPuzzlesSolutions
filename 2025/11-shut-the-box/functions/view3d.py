"""Software 3D projection, picking, and antialiased drawing of fold candidates."""
from dataclasses import dataclass
from math import sin, cos, hypot, pi
from .folding import cuboid_surface, initial_placement, face_name
from .rendering import digit_font
from .constants import SHAPE_COLOR, SHAPE_SIZE_RATIO


@dataclass
class ProjectedCell:
    surface: object
    index: int | None
    polygon: tuple
    center: tuple
    depth: float
    placement: object


def rotate(point, yaw, pitch):
    x, y, z = point
    x, z = cos(yaw) * x + sin(yaw) * z, -sin(yaw) * x + cos(yaw) * z
    return x, cos(pitch) * y - sin(pitch) * z, sin(pitch) * y + cos(pitch) * z


def world_point(cell, dimensions, separation, right, down, u=0, v=0):
    return tuple(center / 2 - length / 2 + separation * normal + u * r + v * d
                 for center, length, normal, r, d in zip(cell.center, dimensions, cell.normal, right, down))


def project_fold(trial, width, height, yaw, pitch, zoom=1, separation=0):
    owners = {placement.cell: (index, placement) for index, placement in trial.mapping.items()}
    geometry = []
    bounds = []
    for surface in cuboid_surface(trial.dimensions):
        index, placement = owners.get(surface, (None, initial_placement(surface, 0)))
        corners = [rotate(world_point(surface, trial.dimensions, separation, placement.right, placement.down, u, v), yaw, pitch)
                   for u, v in ((-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5))]
        bounds.extend(corners)
        if rotate(surface.normal, yaw, pitch)[2] > 1e-8:
            center = rotate(world_point(surface, trial.dimensions, separation, placement.right, placement.down), yaw, pitch)
            geometry.append((surface, index, placement, corners, center))
    xmin, xmax = min(p[0] for p in bounds), max(p[0] for p in bounds)
    ymin, ymax = min(p[1] for p in bounds), max(p[1] for p in bounds)
    scale = min(max(1, width - 60) / max(1e-8, xmax - xmin),
                max(1, height - 60) / max(1e-8, ymax - ymin)) * zoom
    def screen(point):
        return (width / 2 + scale * (point[0] - (xmin + xmax) / 2),
                height / 2 - scale * (point[1] - (ymin + ymax) / 2))
    cells = [ProjectedCell(surface, index, tuple(screen(point) for point in corners), screen(center), center[2], placement)
             for surface, index, placement, corners, center in geometry]
    return sorted(cells, key=lambda cell: cell.depth), scale, screen


def point_in_polygon(point, polygon):
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
        previous = current
    return inside


def pick_cell(projected, point):
    return next((cell for cell in reversed(projected) if point_in_polygon(point, cell.polygon)), None)


def render_fold(trial, cells, columns, anchor, width, height, yaw, pitch,
                zoom=1, separation=0, coordinates=False, selected=None):
    from PIL import Image, ImageDraw
    projected, scale, screen = project_fold(trial, width, height, yaw, pitch, zoom, separation)
    supersample = 2
    image = Image.new('RGB', (width * supersample, height * supersample), '#f6f8fb')
    draw = ImageDraw.Draw(image)
    def points(polygon):
        return [(x * supersample, y * supersample) for x, y in polygon]
    for item in projected:
        light = .65 + .35 * rotate(item.surface.normal, yaw, pitch)[2]
        base = (208, 234, 207) if item.index is not None else (238, 241, 246)
        if item.index == anchor: base = (137, 204, 244)
        fill = tuple(round(value * light) for value in base)
        polygon = points(item.polygon)
        draw.polygon(polygon, fill=fill)
        draw.line(polygon + [polygon[0]], fill='#63706c', width=supersample)
        if item.index is not None:
            cell = cells[item.index]
            shape = cell['shape']
            if shape:
                extent = SHAPE_SIZE_RATIO / 2
                local = [(extent * cos(2*pi*i/40), extent * sin(2*pi*i/40)) for i in range(40)] if shape == 'circle' else [(-extent, -extent), (extent, -extent), (extent, extent), (-extent, extent)]
                shape_polygon = [screen(rotate(world_point(item.surface, trial.dimensions, separation,
                                                item.placement.right, item.placement.down, u, v), yaw, pitch)) for u, v in local]
                draw.polygon(points(shape_polygon), fill=SHAPE_COLOR)
            label = cell['digit']
            if coordinates:
                row, column = divmod(item.index, columns)
                label = f'{row + 1},{column + 1}'
            if label is not None and label != '':
                label = str(label)
                edge = min(hypot(item.polygon[(i+1)%4][0] - item.polygon[i][0],
                                 item.polygon[(i+1)%4][1] - item.polygon[i][1]) for i in range(4))
                font_size = min(28, int(edge * (.22 if coordinates else .46)))
                if font_size >= 7:
                    font = digit_font(font_size * supersample)
                    bbox = font.getbbox(label)
                    position = (item.center[0]*supersample - (bbox[0]+bbox[2])/2,
                                item.center[1]*supersample - (bbox[1]+bbox[3])/2)
                    draw.text(position, label, font=font, fill='#111111')
        if item.surface == selected:
            draw.line(polygon + [polygon[0]], fill='#e46b16', width=3 * supersample)
    return image.resize((width, height), Image.Resampling.LANCZOS), projected
