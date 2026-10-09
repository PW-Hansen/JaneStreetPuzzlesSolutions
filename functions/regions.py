"""Orthogonally connected regions separated by thick borders."""


def region_map(grid):
    borders = {tuple(edge) for edge in grid["borders"]}
    regions = {}
    for row in range(grid["rows"]):
        for column in range(grid["columns"]):
            start = row, column
            if start in regions:
                continue
            region = len(set(regions.values()))
            worklist = [start]
            regions[start] = region
            while worklist:
                cell = worklist.pop()
                r, c = cell
                for neighbor in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                    nr, nc = neighbor
                    edge = min(cell, neighbor) + max(cell, neighbor)
                    if (0 <= nr < grid["rows"] and 0 <= nc < grid["columns"]
                            and neighbor not in regions and edge not in borders):
                        regions[neighbor] = region
                        worklist.append(neighbor)
    return regions


def check_tower_regions(grid):
    regions = region_map(grid)
    occupied = set()
    for tower in grid.get("towers", []):
        region = regions[tuple(tower)]
        if region in occupied:
            raise ValueError("A region may contain only one tower.")
        occupied.add(region)


def tower_colors(grid):
    regions = region_map(grid)
    towers = {tuple(cell) for cell in grid.get("towers", [])}
    occupied = {regions[cell] for cell in towers}
    return {cell: "#93c5fd" if cell in towers else
            "#e5e7eb" if region in occupied else "#dcfce7"
            for cell, region in regions.items()}
