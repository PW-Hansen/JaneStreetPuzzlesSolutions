"""Check whether a continuous known path can still reach all region towers."""

from copy import deepcopy

from functions.regions import propagate_towers, region_map


class CompletionSearch:
    def __init__(self, grid, collect=False):
        self.possible = False
        self.collect = collect
        self.solutions = []
        self.worklist = []
        visits = {value: (r, c) for r, row in enumerate(grid["visits"])
                  for c, value in enumerate(row) if value is not None}
        # Separate path fragments cannot yet establish where the knight currently ends.
        if not visits or min(visits) != 0 or set(visits) != set(range(max(visits) + 1)):
            self.possible = True
            return
        cell = visits[max(visits)]
        score = grid["scores"][cell[0]][cell[1]]
        if score is None:
            self.possible = True
            return
        self.regions = region_map(grid)
        for height in (0, 1):
            candidate = self._height(grid, cell, height)
            if candidate is not None:
                self.worklist.append((candidate, cell, height, score, max(visits)))

    @property
    def done(self):
        return (self.possible and not self.collect) or not self.worklist

    @staticmethod
    def _height(grid, cell, height):
        if list(cell) in grid["non_towers" if height else "towers"]:
            return None
        candidate = deepcopy(grid)
        field = "tower_marks" if height else "non_tower_marks"
        if list(cell) not in candidate[field]:
            candidate[field].append(list(cell))
        try:
            propagate_towers(candidate)
        except ValueError:
            return None
        return candidate

    def advance(self):
        if self.done:
            return
        grid, cell, height, score, visit = self.worklist.pop()
        visited_towers = {self.regions[tuple(tower)] for tower in grid["towers"]
                          if grid["visits"][tower[0]][tower[1]] is not None}
        if visited_towers == set(self.regions.values()):
            self._accept(grid)
            return
        move = visit + 1
        for next_height in (height, 1 - height):
            if next_height == height:
                next_score = score + move
                offsets = ((-2, -1), (-2, 1), (-1, -2), (-1, 2),
                           (1, -2), (1, 2), (2, -1), (2, 1))
            elif next_height:
                next_score = score * move
                offsets = ((-2, 0), (2, 0), (0, -2), (0, 2))
            else:
                if score % move:
                    continue
                next_score = score // move
                offsets = ((-2, 0), (2, 0), (0, -2), (0, 2))
            for dr, dc in offsets:
                r, c = cell[0] + dr, cell[1] + dc
                if not (0 <= r < grid["rows"] and 0 <= c < grid["columns"]):
                    continue
                if grid["visits"][r][c] is not None or grid["scores"][r][c] not in (None, next_score):
                    continue
                candidate = self._height(grid, (r, c), next_height)
                if candidate is not None:
                    candidate["scores"][r][c] = next_score
                    candidate["visits"][r][c] = move
                    self.worklist.append((candidate, (r, c), next_height, next_score, move))

    def _accept(self, grid):
        self.possible = True
        if self.collect:
            self.solutions.append(grid)
