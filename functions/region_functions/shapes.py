"""Polyomino transformations, connected completions, and containment."""

from .connectivity import minimum_region_size


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
