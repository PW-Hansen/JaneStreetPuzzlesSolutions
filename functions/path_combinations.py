"""Check combinations containing one alternative from each retained path group."""

from copy import deepcopy

from functions.path_candidates import compatible_grid
from functions.path_completion import CompletionSearch
from functions.path_ordering import PathCompatibility


class CombinationSearch:
    def __init__(self, session, ordered=True):
        self.original = deepcopy(session.grid)
        self.groups = deepcopy(session.pending_paths)
        self.worklist = [(self.original, 0, [], 0)] if self.groups else []
        self.combinations = []
        self._seen = set()
        self.completion = None
        self._completion_cells = None
        self.ordered = ordered
        if ordered:
            self.compatibility = PathCompatibility(self.original, self.groups)
            allowed = tuple(frozenset(range(len(group))) for group in self.groups)
            self.worklist = [(self.original, allowed, [])] if self.groups else []

    @property
    def done(self):
        return not self.worklist and self.completion is None

    def advance(self):
        """Check one alternative, allowing the GUI to yield or abort."""
        if self.done:
            return
        if self.completion is not None:
            self.completion.advance()
            if self.completion.done:
                if self.completion.possible:
                    self._accept(self._completion_cells)
                self.completion = None
            return
        if self.ordered:
            self._advance_ordered()
            return
        grid, group_index, cells, choice = self.worklist.pop()
        if group_index == len(self.groups):
            self.completion = CompletionSearch(grid)
            self._completion_cells = cells
            return
        group = self.groups[group_index]
        if choice + 1 < len(group):
            self.worklist.append((grid, group_index, cells, choice + 1))
        path = group[choice]
        candidate = compatible_grid(grid, path)
        if candidate is not None:
            # A shared endpoint at the same visit is one visit, not a revisited cell.
            combined = cells + [cell for cell in path if cell not in cells]
            self.worklist.append((candidate, group_index + 1, combined, 0))

    def _advance_ordered(self):
        grid, allowed, cells = self.worklist.pop()
        remaining = [i for i, choices in enumerate(allowed) if choices is not None]
        if not remaining:
            self.completion = CompletionSearch(grid)
            self._completion_cells = cells
            return
        group_index = min(remaining, key=lambda i: (len(allowed[i]), i))
        choices = allowed[group_index]
        choice = min(choices)
        siblings = list(allowed)
        siblings[group_index] = choices - {choice}
        if siblings[group_index]:
            self.worklist.append((grid, tuple(siblings), cells))
        following = list(allowed)
        following[group_index] = None
        for other in remaining:
            if other == group_index:
                continue
            following[other] &= self.compatibility.allowed(group_index, choice, other)
            if not following[other]:
                return
        path = self.groups[group_index][choice]
        candidate = compatible_grid(grid, path)
        if candidate is not None:
            combined = cells + [cell for cell in path if cell not in cells]
            self.worklist.append((candidate, tuple(following), combined))

    def _accept(self, cells):
        key = tuple(sorted(tuple(cell) for cell in cells))
        if key not in self._seen:
            self._seen.add(key)
            self.combinations.append([list(cell) for cell in key])


def apply_combinations(session, search):
    """Retain compatible combinations and apply their shared deductions atomically."""
    if not search.done:
        return False
    if session.grid != search.original or session.pending_paths != search.groups:
        raise ValueError("The grid or retained paths changed during analysis. Run Find valid combinations again.")
    if not search.combinations:
        return False
    # Keeping combinations together preserves their compatibility for future edits.
    return session._change(lambda: setattr(session, "pending_paths", [deepcopy(search.combinations)]))
