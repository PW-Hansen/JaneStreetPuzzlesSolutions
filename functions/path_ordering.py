"""Cheap pairwise checks used to avoid incompatible combination branches."""

from functions.regions import region_map


class PathCompatibility:
    def __init__(self, grid, groups):
        regions = region_map(grid)
        self.region_cells = {}
        for cell, region in regions.items():
            self.region_cells.setdefault(region, set()).add(cell)
        self.base_non = {tuple(cell) for cell in grid["non_towers"]}
        self.profiles = []
        self.cache = {}
        for group in groups:
            profiles = []
            for path in group:
                cells = {(r, c): (score, visit, height) for r, c, score, visit, height in path}
                visits = {visit: (r, c) for r, c, score, visit, height in path}
                towers = {regions[(r, c)]: (r, c) for r, c, score, visit, height in path if height}
                non = {(r, c) for r, c, score, visit, height in path if not height}
                profiles.append((cells, visits, towers, non))
            self.profiles.append(profiles)

    def compatible(self, first, second):
        cells, visits, towers, non = first
        other_cells, other_visits, other_towers, other_non = second
        if any(cells[cell] != other_cells[cell] for cell in cells.keys() & other_cells.keys()):
            return False
        if any(visits[visit] != other_visits[visit] for visit in visits.keys() & other_visits.keys()):
            return False
        if any(towers[region] != other_towers[region] for region in towers.keys() & other_towers.keys()):
            return False
        exclusions = self.base_non | non | other_non
        return not any(cells <= exclusions for cells in self.region_cells.values())

    def allowed(self, group, path, other_group):
        key = group, path, other_group
        if key not in self.cache:
            first = self.profiles[group][path]
            self.cache[key] = frozenset(i for i, second in enumerate(self.profiles[other_group])
                                        if self.compatible(first, second))
        return self.cache[key]
