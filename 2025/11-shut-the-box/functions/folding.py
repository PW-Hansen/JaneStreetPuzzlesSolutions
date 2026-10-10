"""Forced, orientation-preserving embeddings of confirmed regions on cuboids."""
from collections import deque
from dataclasses import dataclass
from .regions import orthogonal_neighbors
from .dimensions import possible_dimension_totals


def negate(vector):
    return tuple(-value for value in vector)


@dataclass(frozen=True)
class SurfaceCell:
    center: tuple  # Coordinates in half-cell units, multiplied by two.
    normal: tuple


@dataclass(frozen=True)
class Placement:
    cell: SurfaceCell
    right: tuple
    down: tuple


@dataclass
class FoldTrial:
    dimensions: tuple
    anchor: SurfaceCell
    rotation: int
    reason: str | None
    mapping: dict | None


def cuboid_surface(dimensions):
    if len(dimensions) != 3 or any(type(d) is not int or d < 1 for d in dimensions):
        raise ValueError('Box dimensions must be three positive integers.')
    for axis in range(3):
        other = [i for i in range(3) if i != axis]
        for sign in (-1, 1):
            normal = tuple(sign if i == axis else 0 for i in range(3))
            for u in range(dimensions[other[0]]):
                for v in range(dimensions[other[1]]):
                    center = [0, 0, 0]
                    center[axis] = 0 if sign < 0 else 2 * dimensions[axis]
                    center[other[0]], center[other[1]] = 2 * u + 1, 2 * v + 1
                    yield SurfaceCell(tuple(center), normal)


def initial_placement(cell, rotation):
    axis = next(i for i, value in enumerate(cell.normal) if value)
    first, second = (axis + 1) % 3, (axis + 2) % 3
    right = tuple(cell.normal[axis] if i == first else 0 for i in range(3))
    down = tuple(1 if i == second else 0 for i in range(3))
    for _ in range(rotation):
        right, down = negate(down), right
    return Placement(cell, right, down)


def surface_step(placement, direction, dimensions):
    tangent = {'east': placement.right, 'west': negate(placement.right),
               'south': placement.down, 'north': negate(placement.down)}[direction]
    axis = next(i for i, value in enumerate(tangent) if value)
    center = tuple(p + 2 * t for p, t in zip(placement.cell.center, tangent))
    if 0 < center[axis] < 2 * dimensions[axis]:
        return Placement(SurfaceCell(center, placement.cell.normal), placement.right, placement.down)
    normal = placement.cell.normal
    center = tuple(p + t - n for p, t, n in zip(placement.cell.center, tangent, normal))
    def transport(vector):
        if vector == tangent: return negate(normal)
        if vector == negate(tangent): return normal
        return vector
    return Placement(SurfaceCell(center, tangent), transport(placement.right), transport(placement.down))


def largest_box_region(boxes, rows, columns):
    remaining = {index for index, value in enumerate(boxes) if value is True}
    largest = set()
    while remaining:
        root = min(remaining)
        region = {root}
        pending = [root]
        remaining.remove(root)
        while pending:
            for neighbor in orthogonal_neighbors(pending.pop(), rows, columns):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    region.add(neighbor)
                    pending.append(neighbor)
        if len(region) > len(largest): largest = region
    return largest


def grid_neighbors(index, rows, columns):
    row, column = divmod(index, columns)
    if row: yield 'north', index - columns
    if column + 1 < columns: yield 'east', index + 1
    if row + 1 < rows: yield 'south', index + columns
    if column: yield 'west', index - 1


def fold_region(region, boxes, rows, columns, anchor_index, dimensions, anchor_cell, rotation):
    start = initial_placement(anchor_cell, rotation)
    # Honor the specified anchor test: at least one possible grid neighbor must
    # remain on the anchor's face. In particular, a 1x1 face always fails.
    if not any(boxes[index] is not False and
               surface_step(start, direction, dimensions).cell.normal == anchor_cell.normal
               for direction, index in grid_neighbors(anchor_index, rows, columns)):
        return FoldTrial(dimensions, anchor_cell, rotation, 'isolated anchor', None)
    mapping = {anchor_index: start}
    occupied = {anchor_cell: anchor_index}
    pending = deque([anchor_index])
    while pending:
        index = pending.popleft()
        for direction, neighbor in grid_neighbors(index, rows, columns):
            if neighbor not in region: continue
            placement = surface_step(mapping[index], direction, dimensions)
            if neighbor in mapping:
                if placement != mapping[neighbor]:
                    return FoldTrial(dimensions, anchor_cell, rotation, 'severed connection', None)
            elif placement.cell in occupied:
                return FoldTrial(dimensions, anchor_cell, rotation, 'overlap', None)
            else:
                mapping[neighbor] = placement
                occupied[placement.cell] = neighbor
                pending.append(neighbor)
    if len(mapping) != len(region):
        raise ValueError('The region is not connected to the anchor.')
    return FoldTrial(dimensions, anchor_cell, rotation, None, mapping)


def folding_trials(boxes, rows, columns, anchor_index):
    if type(anchor_index) is not int or not 0 <= anchor_index < len(boxes):
        raise ValueError('The fold anchor is outside the grid.')
    region = largest_box_region(boxes, rows, columns)
    if anchor_index not in region:
        raise ValueError('The anchor must be a confirmed box cell in the largest region.')
    in_box = sum(box is True for box in boxes)
    unknown = sum(box is None for box in boxes)
    for total in possible_dimension_totals(in_box, unknown):
        for dimensions in total.triples:
            for anchor_cell in cuboid_surface(dimensions):
                for rotation in range(4):
                    yield fold_region(region, boxes, rows, columns, anchor_index, dimensions, anchor_cell, rotation)


def configured_anchor(configuration, selected, rows, columns):
    coordinates = configuration.get('fold_anchor')
    if coordinates is None:
        if selected is None: raise ValueError('Select a fold anchor cell first.')
        return selected
    if (not isinstance(coordinates, list) or len(coordinates) != 2 or
            any(type(value) is not int for value in coordinates)):
        raise ValueError('fold_anchor must contain a row and column, numbered from 1.')
    row, column = coordinates
    if not (1 <= row <= rows and 1 <= column <= columns):
        raise ValueError('Configured fold anchor is outside the grid.')
    return (row - 1) * columns + column - 1


def face_name(cell):
    axis = next(i for i, value in enumerate(cell.normal) if value)
    return ('+' if cell.normal[axis] > 0 else '-') + 'XYZ'[axis]
