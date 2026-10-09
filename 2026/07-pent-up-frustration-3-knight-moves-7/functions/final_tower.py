"""Find and apply continuations reaching the last unvisited region tower."""

from copy import deepcopy
from types import SimpleNamespace

from functions.path_completion import CompletionSearch
from functions.path_combinations import CombinationSearch
from functions.regions import region_map


class FinalTowerSearch(CompletionSearch):
    def __init__(self, session):
        self.original = deepcopy(session.grid)
        self.groups = deepcopy(session.pending_paths)
        grid = self.original
        visits = [(v, r, c) for r, row in enumerate(grid["visits"])
                  for c, v in enumerate(row) if v is not None]
        numbers = [v for v, r, c in visits]
        if not numbers or sorted(numbers) != list(range(max(numbers) + 1)):
            raise ValueError("Fill in a continuous path from visit 0 before visiting the final tower.")
        self.start_visit, r, c = max(visits)
        self.start = (r, c)
        if grid["scores"][r][c] is None:
            raise ValueError("The current endpoint needs a score.")
        regions = region_map(grid)
        visited = {regions[tuple(cell)] for cell in grid["towers"]
                   if grid["visits"][cell[0]][cell[1]] is not None}
        remaining = set(regions.values()) - visited
        if len(remaining) != 1:
            raise ValueError("There must be exactly one region whose tower has not been visited.")
        self.final_region = next(iter(remaining))
        self.paths = []
        self._seen_paths = set()
        self.verification = None
        self._proposed_grid = None
        super().__init__(grid, collect=True)

    @property
    def done(self):
        return super().done and self.verification is None

    def advance(self):
        if self.verification is None:
            super().advance()
            return
        self.verification.advance()
        if self.verification.combinations:
            self._record(self._proposed_grid)
            self.verification = None
        elif self.verification.done:
            self.verification = None

    def _accept(self, grid):
        end_visit, r, c = max((v, r, c) for r, row in enumerate(grid["visits"])
                              for c, v in enumerate(row) if v is not None)
        if (end_visit <= self.start_visit or self.regions[(r, c)] != self.final_region
                or [r, c] not in grid["towers"]):
            return
        if self.groups:
            self._proposed_grid = grid
            self.verification = CombinationSearch(SimpleNamespace(grid=grid, pending_paths=self.groups))
        else:
            self._record(grid)

    def _record(self, grid):
        path = sorted([[r, c, grid["scores"][r][c], v, int([r, c] in grid["towers"])]
                       for r, row in enumerate(grid["visits"]) for c, v in enumerate(row)
                       if v is not None and v >= self.start_visit], key=lambda cell: cell[3])
        key = tuple(tuple(cell) for cell in path)
        if key not in self._seen_paths:
            self._seen_paths.add(key)
            self.paths.append(path)
            super()._accept(grid)


def apply_final_tower(session, search):
    if not search.done:
        return False
    if session.grid != search.original or session.pending_paths != search.groups:
        raise ValueError("The grid or retained paths changed during analysis. Run visit final tower again.")
    if not search.paths:
        return False
    def operation():
        if search.paths not in session.pending_paths:
            session.pending_paths.append(deepcopy(search.paths))
    return session._change(operation)
