"""Polyomino transformations, connected completions, and containment."""

from functions.equations_functions import evaluate
from .connectivity import minimum_region_size, check_grid_connectivity


def shape_orientations(cells, size):
    points = [divmod(cell,size) for cell in cells]
    unique = set()
    orientations = []
    for rotation in range(4):
        for reflected in (False,True):
            transformed = []
            for row,column in points:
                if reflected: column = -column
                for _ in range(rotation): row,column = column,-row
                transformed.append((row,column))
            top,left = min(r for r,c in transformed),min(c for r,c in transformed)
            shape = tuple(sorted((r-top,c-left) for r,c in transformed))
            if shape not in unique:
                unique.add(shape)
                orientations.append((rotation,reflected,shape))
    return orientations


def reverse_overlay_orientations(cells, size):
    """Unique connected shapes obtained by deleting one cell, with D4 symmetry."""
    number = len(cells)-1
    orientations,seen = [],set()
    for removed in sorted(cells):
        reduced = set(cells)-{removed}
        if not reduced or minimum_region_size(size,{},number,reduced) is None:
            continue
        for rotation,reflected,shape in shape_orientations(reduced,size):
            if shape not in seen:
                seen.add(shape)
                orientations.append((rotation,reflected,shape))
    return orientations


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
