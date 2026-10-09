"""Automate checkpoint continuation, fixed-interval trials, and final-tower visits."""

from copy import deepcopy
from dataclasses import dataclass

from functions.final_tower import FinalTowerSearch
from functions.path_analysis import ContinuationSearch, apply_continuation
from functions.path_candidates import compatible_grid
from functions.path_combinations import CombinationSearch
from functions.regions import region_map
from functions.state import Session


@dataclass
class SolveResult:
    session: Session
    status: str
    interval: int | None
    solutions: int
    message: str


def run_search(search):
    while not search.done:
        search.advance()
    return search


def cell_at_visit(grid, visit):
    cells = [(r, c) for r, row in enumerate(grid["visits"])
             for c, value in enumerate(row) if value == visit]
    if len(cells) > 1:
        raise ValueError(f"Visit {visit} is assigned to more than one cell.")
    return cells[0] if cells else None


def unvisited_scores(grid):
    return [(r, c) for r, row in enumerate(grid["scores"])
            for c, score in enumerate(row) if score is not None and grid["visits"][r][c] is None]


def interval_limit(grid, visit, remaining_clues):
    """Each remaining checkpoint consumes K new cells after the known prefix."""
    if remaining_clues <= 0:
        return 0
    return (grid["rows"] * grid["columns"] - (visit + 1)) // remaining_clues


def continue_checkpoint(session, visit, moves, report):
    start = cell_at_visit(session.grid, visit)
    if start is None:
        return None
    target_visit = visit + moves
    existing = cell_at_visit(session.grid, target_visit)
    if existing is not None:
        report(f"Visit {target_visit} already known at r{existing[0] + 1}c{existing[1] + 1}.")
        return existing
    search = run_search(ContinuationSearch(session.grid, start, moves))
    report(f"Visit {visit}, look ahead {moves}: {search.message}")
    if not search.paths:
        return None
    apply_continuation(session, search)
    return cell_at_visit(session.grid, target_visit)


def final_solutions(session, report):
    """Resolve checkpoint alternatives, then enumerate final tower continuations."""
    if session.pending_paths:
        combinations = run_search(CombinationSearch(session))
        report(f"{len(combinations.combinations)} valid checkpoint combinations.")
        candidates = [compatible_grid(session.grid, path) for path in combinations.combinations]
    else:
        candidates = [deepcopy(session.grid)]
    solutions = []
    seen = set()
    for grid in candidates:
        if grid is None:
            continue
        regions = region_map(grid)
        visited = {regions[tuple(cell)] for cell in grid["towers"]
                   if grid["visits"][cell[0]][cell[1]] is not None}
        if visited == set(regions.values()):
            completed = [grid]
        else:
            try:
                search = run_search(FinalTowerSearch(Session(grid)))
            except ValueError:
                continue
            report(f"{len(search.paths)} legal continuations to the final tower.")
            completed = search.solutions
        for solution in completed:
            path = sorted([[r, c, solution["scores"][r][c], visit,
                            int([r, c] in solution["towers"])]
                           for r, row in enumerate(solution["visits"])
                           for c, visit in enumerate(row) if visit is not None], key=lambda cell: cell[3])
            key = tuple(tuple(cell) for cell in path)
            if key not in seen:
                seen.add(key)
                solutions.append(path)
    return solutions


def solve(session, early_step=3, early_end=18, first_interval=4, report=None):
    """Solve a copy; failed interval trials cannot contaminate subsequent trials."""
    report = report or (lambda message: None)
    if (any(type(value) is not int for value in (early_step, early_end, first_interval))
            or early_step <= 0 or early_end < 0 or early_end % early_step or first_interval <= 0):
        raise ValueError("Use positive intervals and an early endpoint divisible by the early interval.")
    working = deepcopy(session)
    grid = working.grid
    start = grid["rows"] - 1, 0
    if grid["scores"][start[0]][start[1]] != 0:
        raise ValueError("The bottom-left starting cell must have score 0.")
    if grid["visits"][start[0]][start[1]] not in (None, 0):
        raise ValueError("The bottom-left starting cell must have visit 0.")
    grid["visits"][start[0]][start[1]] = 0
    if early_end >= grid["rows"] * grid["columns"]:
        raise ValueError("The early endpoint exceeds the available cells.")
    for visit in range(0, early_end, early_step):
        if continue_checkpoint(working, visit, early_step, report) is None:
            return SolveResult(working, "failed", None, 0, f"Could not reach visit {visit + early_step}.")
    baseline = deepcopy(working)
    remaining = len(unvisited_scores(baseline.grid))
    limit = interval_limit(baseline.grid, early_end, remaining)
    report(f"At visit {early_end}: {remaining} remaining scored cells; maximum interval {limit}.")
    intervals = range(first_interval, limit + 1) if remaining else (None,)
    for interval in intervals:
        trial = deepcopy(baseline)
        report(f"Trying interval {interval}." if interval is not None else "Checking the final tower.")
        visit = early_end
        success = True
        while unvisited_scores(trial.grid):
            if visit + interval >= grid["rows"] * grid["columns"]:
                success = False
                break
            if continue_checkpoint(trial, visit, interval, report) is None:
                success = False
                break
            visit += interval
        if not success:
            continue
        solutions = final_solutions(trial, report)
        if not solutions:
            report("No complete solution for this interval; trying the next interval.")
            continue
        trial._change(lambda: setattr(trial, "pending_paths", deepcopy([solutions])))
        status = "solved" if len(solutions) == 1 else "ambiguous"
        return SolveResult(trial, status, interval, len(solutions),
                           f"{len(solutions)} complete solution(s), interval {interval}.")
    return SolveResult(baseline, "failed", None, 0,
                       f"No solution with intervals {first_interval} through {limit}.")
