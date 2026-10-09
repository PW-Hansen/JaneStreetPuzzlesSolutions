"""Arithmetic target filtering and short knight-path continuation."""

from copy import deepcopy

from functions.movements import MovementSearch
from functions.regions import propagate_towers


def assign_height(grid, cell, height):
    """Assert a candidate altitude, rejecting conflicts and region contradictions."""
    mark = list(cell)
    desired, opposite = ("towers", "non_towers") if height else ("non_towers", "towers")
    if mark in grid[opposite]:
        return False
    field = "tower_marks" if height else "non_tower_marks"
    if mark not in grid[field]:
        grid[field].append(mark)
    try:
        propagate_towers(grid)
    except ValueError:
        return False
    return True


class ContinuationSearch:
    def __init__(self, grid, start, lookahead=3):
        self.original = deepcopy(grid)
        self.start = start
        self.arithmetic = MovementSearch.from_cell(grid, start, lookahead)
        self.phase = "Arithmetic"
        self.targets = {}
        self.sequences = []
        self.worklist = []
        self.path_count = 0
        self.paths = []
        self.common = None
        self.message = ""
        for r in range(grid["rows"]):
            for c in range(grid["columns"]):
                score = grid["scores"][r][c]
                if score is not None and grid["visits"][r][c] is None:
                    self.targets.setdefault(score, []).append((r, c))
        self.matching_targets = set()

    @property
    def done(self):
        return self.phase == "Complete"

    def advance(self):
        """Process one worklist entry so the GUI can yield and abort."""
        if self.phase == "Arithmetic":
            if self.arithmetic.worklist:
                result = self.arithmetic.advance()
                if result is not None and result[0] in self.targets:
                    self.sequences.append((result[0], result[2]))
                    self.matching_targets.update(self.targets[result[0]])
                return
            if len(self.matching_targets) != 1:
                self.message = ("No matching unvisited score cell." if not self.matching_targets
                                else f"{len(self.matching_targets)} possible target cells; no deductions applied.")
                self.phase = "Complete"
                return
            self.target = next(iter(self.matching_targets))
            target_score = self.original["scores"][self.target[0]][self.target[1]]
            # Keep only sequences whose final score belongs to this target.
            start_score = self.original["scores"][self.start[0]][self.start[1]]
            start_visit = self.original["visits"][self.start[0]][self.start[1]]
            for height in (0, 1):
                candidate = deepcopy(self.original)
                if assign_height(candidate, self.start, height):
                    for final_score, sequence in self.sequences:
                        if final_score == target_score:
                            trace = [[*self.start, start_score, start_visit, height]]
                            self.worklist.append((candidate, self.start, height, start_score, start_visit, sequence, 0, trace))
            self.phase = "Paths"
            return
        if self.phase == "Paths":
            if not self.worklist:
                r, c = self.target
                self.message = f"Target r{r + 1}c{c + 1}: {self.path_count} valid paths."
                self.phase = "Complete"
                return
            grid, cell, height, score, visit, sequence, index, trace = self.worklist.pop()
            if index == len(sequence):
                if cell == self.target:
                    self.paths.append(trace)
                    self._accept(grid)
                return
            operation = sequence[index]
            move = visit + 1
            if operation == "+":
                new_height, new_score = height, score + move
                offsets = ((-2, -1), (-2, 1), (-1, -2), (-1, 2),
                           (1, -2), (1, 2), (2, -1), (2, 1))
            elif operation == "*":
                if height != 0:
                    return
                new_height, new_score = 1, score * move
                offsets = ((-2, 0), (2, 0), (0, -2), (0, 2))
            else:
                if height != 1 or score % move:
                    return
                new_height, new_score = 0, score // move
                offsets = ((-2, 0), (2, 0), (0, -2), (0, 2))
            for dr, dc in offsets:
                next_cell = cell[0] + dr, cell[1] + dc
                r, c = next_cell
                if not (0 <= r < grid["rows"] and 0 <= c < grid["columns"]):
                    continue
                if grid["visits"][r][c] is not None:
                    continue
                if index + 1 == len(sequence) and next_cell != self.target:
                    continue
                if grid["scores"][r][c] is not None and grid["scores"][r][c] != new_score:
                    continue
                candidate = deepcopy(grid)
                if not assign_height(candidate, next_cell, new_height):
                    continue
                candidate["scores"][r][c] = new_score
                candidate["visits"][r][c] = move
                self.worklist.append((candidate, next_cell, new_height, new_score, move, sequence, index + 1,
                                      trace + [[r, c, new_score, move, new_height]]))

    def _accept(self, grid):
        self.path_count += 1
        if self.common is None:
            self.common = deepcopy(grid)
            return
        for field in ("scores", "visits"):
            for r in range(grid["rows"]):
                for c in range(grid["columns"]):
                    if self.common[field][r][c] != grid[field][r][c]:
                        self.common[field][r][c] = None
        for field in ("towers", "non_towers"):
            self.common[field] = [cell for cell in self.common[field] if cell in grid[field]]


def apply_continuation(session, search):
    """Apply only completed, shared deductions as one undoable change."""
    if not search.done or search.common is None:
        return False
    if session.grid != search.original:
        raise ValueError("The grid changed during analysis. Run Continue path again.")
    candidate = deepcopy(session.grid)
    for field in ("scores", "visits"):
        for r in range(candidate["rows"]):
            for c in range(candidate["columns"]):
                if search.common[field][r][c] is not None:
                    candidate[field][r][c] = search.common[field][r][c]
    for inferred, explicit in (("towers", "tower_marks"), ("non_towers", "non_tower_marks")):
        for cell in search.common[inferred]:
            if cell not in candidate[explicit]:
                candidate[explicit].append(cell)
    propagate_towers(candidate)
    def operation():
        session.grid = candidate
        if search.path_count > 1 and search.paths not in session.pending_paths:
            session.pending_paths.append(deepcopy(search.paths))
    return session._change(operation)
