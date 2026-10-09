"""Trial tower assertions against all retained path groups together."""

from copy import deepcopy
from types import SimpleNamespace

from functions.path_combinations import CombinationSearch
from functions.regions import propagate_towers, region_map


class TowerPlacementSearch:
    def __init__(self, session):
        self.original = deepcopy(session.grid)
        self.groups = deepcopy(session.pending_paths)
        regions = region_map(self.original)
        occupied = {regions[tuple(cell)] for cell in self.original["towers"]}
        excluded = {tuple(cell) for cell in self.original["non_towers"]}
        self.cells = [cell for cell, region in regions.items()
                      if region not in occupied and cell not in excluded]
        self.possible = []
        self.impossible = []
        self.index = 0
        self.phase = "Checking current paths"
        self.baseline_valid = not self.groups
        self.search = self._combinations(self.original) if self.groups else None
        if not self.groups:
            self.phase = "Trying placements"

    def _combinations(self, grid):
        return CombinationSearch(SimpleNamespace(grid=grid, pending_paths=self.groups))

    @property
    def done(self):
        return self.phase == "Complete"

    def advance(self):
        """Try one placement or advance its compatibility check by one step."""
        if self.done:
            return
        if self.search is not None:
            self.search.advance()
            if not self.search.combinations and not self.search.done:
                return
            valid = bool(self.search.combinations)
            self.search = None
            if self.phase == "Checking current paths":
                self.baseline_valid = valid
                self.phase = "Trying placements" if valid else "Complete"
            else:
                (self.possible if valid else self.impossible).append(self.cells[self.index])
                self.index += 1
            return
        if self.index == len(self.cells):
            self.phase = "Complete"
            return
        cell = self.cells[self.index]
        candidate = deepcopy(self.original)
        candidate["tower_marks"].append(list(cell))
        try:
            propagate_towers(candidate)
        except ValueError:
            self.impossible.append(cell)
            self.index += 1
            return
        if self.groups:
            self.search = self._combinations(candidate)
        else:
            # Without retained path constraints, every locally consistent placement is possible.
            self.possible.append(cell)
            self.index += 1


def apply_tower_placements(session, search):
    if not search.done:
        return False
    if session.grid != search.original or session.pending_paths != search.groups:
        raise ValueError("The grid or retained paths changed during analysis. Run attempt tower placements again.")
    if not search.baseline_valid:
        raise ValueError("The current retained paths have no valid combination. No tower deductions applied.")
    candidate = deepcopy(session.grid)
    for cell in search.impossible:
        if list(cell) not in candidate["non_tower_marks"]:
            candidate["non_tower_marks"].append(list(cell))
    propagate_towers(candidate)
    return session._change(lambda: setattr(session, "grid", candidate))
