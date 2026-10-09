"""Retained continuation alternatives and compatibility with later grid edits."""

from copy import deepcopy

from functions.regions import propagate_towers


def validate_paths(groups, grid):
    if not isinstance(groups, list):
        raise ValueError("Invalid retained paths.")
    for group in groups:
        if not isinstance(group, list) or not group:
            raise ValueError("Invalid path alternatives.")
        for path in group:
            if not isinstance(path, list) or not path:
                raise ValueError("Invalid path.")
            for cell in path:
                if (not isinstance(cell, list) or len(cell) != 5
                        or any(type(value) is not int for value in cell)
                        or not (0 <= cell[0] < grid["rows"] and 0 <= cell[1] < grid["columns"])
                        or cell[3] < 0 or cell[4] not in (0, 1)):
                    raise ValueError("Invalid path cell.")
    return deepcopy(groups)


def compatible_grid(grid, path):
    """Merge a path into a copy; reject score, visit, or tower contradictions."""
    candidate = deepcopy(grid)
    visits = {}
    for r in range(grid["rows"]):
        for c in range(grid["columns"]):
            visit = grid["visits"][r][c]
            if visit is not None:
                visits.setdefault(visit, set()).add((r, c))
    for r, c, score, visit, height in path:
        if (grid["scores"][r][c] not in (None, score)
                or grid["visits"][r][c] not in (None, visit)
                or visits.get(visit, set()) - {(r, c)}
                or [r, c] in grid["non_towers" if height else "towers"]):
            return None
        candidate["scores"][r][c] = score
        candidate["visits"][r][c] = visit
        field = "tower_marks" if height else "non_tower_marks"
        if [r, c] not in candidate[field]:
            candidate[field].append([r, c])
    try:
        propagate_towers(candidate)
    except ValueError:
        return None
    return candidate


def recheck_paths(session):
    """Eliminate impossible alternatives and propagate shared deductions to stability."""
    session.path_notice = ""
    while True:
        before = deepcopy(session.grid)
        pending = []
        applied = False
        for group in session.pending_paths:
            survivors = [(path, compatible_grid(session.grid, path)) for path in group]
            survivors = [(path, grid) for path, grid in survivors if grid is not None]
            if len(survivors) == 1:
                session.grid = survivors[0][1]
                session.path_notice = "The remaining valid path was applied."
                applied = True
            elif survivors:
                pending.append([path for path, grid in survivors])
                grids = [grid for path, grid in survivors]
                for field in ("scores", "visits"):
                    for r in range(session.grid["rows"]):
                        for c in range(session.grid["columns"]):
                            value = grids[0][field][r][c]
                            if value is not None and all(grid[field][r][c] == value for grid in grids):
                                session.grid[field][r][c] = value
                for inferred, explicit in (("towers", "tower_marks"), ("non_towers", "non_tower_marks")):
                    for cell in grids[0][inferred]:
                        if all(cell in grid[inferred] for grid in grids) and cell not in session.grid[explicit]:
                            session.grid[explicit].append(cell)
                propagate_towers(session.grid)
            else:
                session.path_notice = "No retained path remains possible."
        session.pending_paths = pending
        if session.grid != before and not applied:
            session.path_notice = "Shared deductions from the remaining paths were applied."
        if session.grid == before:
            return
