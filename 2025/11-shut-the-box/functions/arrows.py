"""Propagate nearest-box arrow constraints without changing manual cell data."""
from dataclasses import dataclass
from .constants import DIRECTIONS


@dataclass
class ArrowAnalysis:
    boxes: list  # None = unknown, False = outside, True = inside
    sources: list
    distances: dict
    conflicts: list


def ray_cells(index, rows, columns, direction):
    row, column = divmod(index, columns)
    dr, dc = {'north': (-1, 0), 'east': (0, 1),
              'south': (1, 0), 'west': (0, -1)}[direction]
    ray = []
    row, column = row + dr, column + dc
    while 0 <= row < rows and 0 <= column < columns:
        ray.append(row * columns + column)
        row, column = row + dr, column + dc
    return ray


def distance_assignments(rays, arrows, distance):
    """Requirements for one common nearest distance, including forbidden ties."""
    assignments = {}
    for direction, ray in rays.items():
        for offset, index in enumerate(ray[:distance], 1):
            assignments[index] = direction in arrows and offset == distance
    return assignments


def analyze_arrows(cells, rows, columns):
    boxes = [None if c['shading'] == 0 else c['shading'] == 2 for c in cells]
    sources = ['unknown' if value is None else 'manual shading' for value in boxes]
    conflicts = []
    clues = []
    for index, cell in enumerate(cells):
        required = False if cell['arrows'] else True if cell['digit'] is not None or cell['shape'] else None
        if required is not None:
            if boxes[index] is not None and boxes[index] != required:
                row, column = divmod(index, columns)
                conflicts.append(f'R{row + 1}C{column + 1}: shading contradicts the clue (box must be {"yes" if required else "no"}).')
            elif boxes[index] is None:
                boxes[index] = required
                sources[index] = 'clue'
        if cell['arrows']:
            rays = {direction: ray_cells(index, rows, columns, direction) for direction in DIRECTIONS}
            limit = min(len(rays[direction]) for direction in cell['arrows'])
            alternatives = [distance_assignments(rays, cell['arrows'], distance)
                            for distance in range(1, limit + 1)]
            clues.append((index, alternatives))
    base_boxes, base_sources = boxes.copy(), sources.copy()
    distances = {}
    if conflicts:
        return ArrowAnalysis(boxes, sources, distances, conflicts)
    changed = True
    while changed:
        changed = False
        for index, alternatives in clues:
            feasible = [(distance, assignments) for distance, assignments in enumerate(alternatives, 1)
                        if all(boxes[cell] is None or boxes[cell] == value
                               for cell, value in assignments.items())]
            distances[index] = [distance for distance, _ in feasible]
            if not feasible:
                row, column = divmod(index, columns)
                conflicts.append(f'R{row + 1}C{column + 1}: no nearest-box distance satisfies the arrows and current input.')
                continue
            common = dict(feasible[0][1])
            for _, assignments in feasible[1:]:
                common = {cell: value for cell, value in common.items()
                          if cell in assignments and assignments[cell] == value}
            for cell, value in common.items():
                if boxes[cell] is None:
                    boxes[cell] = value
                    sources[cell] = 'arrow rules'
                    changed = True
        if conflicts:
            # An inconsistent input must not leave partial propagation looking conclusive.
            return ArrowAnalysis(base_boxes, base_sources, distances, conflicts)
    return ArrowAnalysis(boxes, sources, distances, conflicts)
