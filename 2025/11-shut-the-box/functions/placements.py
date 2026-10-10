"""Repeated failed-placement deductions using the shared rule analysis."""
from copy import deepcopy
from dataclasses import dataclass
from .analysis import analyze_grid


@dataclass
class PlacementProgress:
    pass_number: int
    index: int
    assignment: bool | None
    tested: int
    forced: int


@dataclass
class PlacementResult:
    status: str
    cells: list
    passes: int
    tested: int
    forced: int
    failed_cell: int | None = None
    conflicts: tuple = ()


def attempt_placements(cells, rows, columns, *, cancelled=lambda: False, progress=None):
    """Test yes/no independently, commit only forced choices, repeat to stability.

    The caller's cells are never mutated. Cancellation or a contradiction retains
    earlier confirmed choices in the returned state, without accepting either
    speculative branch at the failed/current cell.
    """
    working = deepcopy(cells)
    analysis = analyze_grid(working, rows, columns)
    passes = tested = forced = 0
    if analysis.conflicts:
        return PlacementResult('invalid', working, passes, tested, forced,
                               conflicts=tuple(analysis.conflicts))
    while True:
        if cancelled():
            return PlacementResult('cancelled', working, passes, tested, forced)
        passes += 1
        pass_forced = 0
        candidates = [index for index, box in enumerate(analysis.boxes) if box is None]
        for index in candidates:
            if analysis.boxes[index] is not None:
                continue
            branches = []
            for assignment in (True, False):
                if cancelled():
                    return PlacementResult('cancelled', working, passes, tested, forced)
                if progress:
                    progress(PlacementProgress(passes, index, assignment, tested, forced))
                branch = deepcopy(working)
                branch[index]['shading'] = 2 if assignment else 1
                branch_analysis = analyze_grid(branch, rows, columns)
                branches.append((branch, branch_analysis))
            if cancelled():
                return PlacementResult('cancelled', working, passes, tested, forced)
            tested += 1
            valid = [branch for branch in branches if not branch[1].conflicts]
            if not valid:
                conflicts = tuple(f'{"In-box" if assignment else "Out-box"}: ' + '; '.join(branch[1].conflicts)
                                  for assignment, branch in zip((True, False), branches))
                return PlacementResult('contradiction', working, passes, tested, forced, index, conflicts)
            if len(valid) == 1:
                working, analysis = valid[0]
                forced += 1
                pass_forced += 1
                if progress:
                    progress(PlacementProgress(passes, index, None, tested, forced))
        if not pass_forced:
            return PlacementResult('stable', working, passes, tested, forced)
