"""Explicit and density-based anchor selection for command-line solving."""
from .folding import configured_anchor


def neighborhood_box_count(boxes, rows, columns, index, radius):
    row, column = divmod(index, columns)
    return sum(boxes[r * columns + c] is True
               for r in range(max(0, row-radius), min(rows, row+radius+1))
               for c in range(max(0, column-radius), min(columns, column+radius+1)))


def select_solver_anchor(boxes, rows, columns, coordinates=None):
    if coordinates is not None:
        index = configured_anchor({'fold_anchor': list(coordinates)}, None, rows, columns)
        if boxes[index] is not True:
            raise ValueError('The supplied anchor must be a confirmed box cell after placement analysis.')
        return index
    candidates = [index for index, box in enumerate(boxes) if box is True]
    if not candidates:
        raise ValueError('No confirmed box cell is available as a fold anchor.')
    return max(candidates, key=lambda index: (
        neighborhood_box_count(boxes, rows, columns, index, 1),
        neighborhood_box_count(boxes, rows, columns, index, 2), -index))
