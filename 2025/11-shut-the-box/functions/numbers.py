"""Local box counts for numbered cells, including the numbered cell itself."""
from dataclasses import dataclass


@dataclass
class NumberCount:
    target: int
    yes: int
    unknown: int


def number_neighborhood(index, rows, columns):
    row, column = divmod(index, columns)
    return [r * columns + c
            for r in range(max(0, row - 1), min(rows, row + 2))
            for c in range(max(0, column - 1), min(columns, column + 2))]


def number_counts(cells, boxes, rows, columns):
    counts = {}
    for index, cell in enumerate(cells):
        if cell['digit'] is None:
            continue
        neighborhood = number_neighborhood(index, rows, columns)
        counts[index] = NumberCount(int(cell['digit']),
                                   sum(boxes[neighbor] is True for neighbor in neighborhood),
                                   sum(boxes[neighbor] is None for neighbor in neighborhood))
    return counts


def propagate_numbers(cells, boxes, sources, rows, columns, conflicts):
    """Apply count bounds once; the shared propagation loop repeats to stability."""
    changed = False
    for index, cell in enumerate(cells):
        if cell['digit'] is None:
            continue
        neighborhood = number_neighborhood(index, rows, columns)
        yes = sum(boxes[neighbor] is True for neighbor in neighborhood)
        unknown = [neighbor for neighbor in neighborhood if boxes[neighbor] is None]
        target = int(cell['digit'])
        if yes > target or yes + len(unknown) < target:
            row, column = divmod(index, columns)
            conflicts.append(f'R{row + 1}C{column + 1}: number {target} cannot be satisfied '
                             f'({yes} box cells, {len(unknown)} unknown, including the clue).')
            continue
        forced = False if yes == target else True if yes + len(unknown) == target else None
        if forced is not None:
            for neighbor in unknown:
                boxes[neighbor] = forced
                sources[neighbor] = 'number rules'
                changed = True
    return changed
