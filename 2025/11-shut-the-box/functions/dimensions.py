"""Enumerate positive integer cuboid dimensions by possible box-cell totals."""
from dataclasses import dataclass
from math import isqrt


@dataclass(frozen=True)
class DimensionTotal:
    cells: int
    added_unknown: int
    triples: tuple


def dimension_triples(cell_count):
    """All (a,b,c), a >= b >= c >= 1, with surface area cell_count."""
    if type(cell_count) is not int or cell_count < 0:
        raise ValueError('The cell count must be a nonnegative integer.')
    if cell_count % 2:
        return ()
    half = cell_count // 2
    triples = []
    for c in range(1, isqrt(half // 3) + 1):
        # a >= b implies half >= b*b + 2*b*c.
        for b in range(c, isqrt(c * c + half) - c + 1):
            a, remainder = divmod(half - b * c, b + c)
            if remainder == 0 and a >= b:
                triples.append((a, b, c))
    return tuple(sorted(triples, reverse=True))


def possible_dimension_totals(in_box, unknown):
    """Check all feasible counts, omitting odd totals without calculating them."""
    if any(type(value) is not int or value < 0 for value in (in_box, unknown)):
        raise ValueError('Box and unknown counts must be nonnegative integers.')
    first = in_box + in_box % 2
    for total in range(first, in_box + unknown + 1, 2):
        yield DimensionTotal(total, total - in_box, dimension_triples(total))
