"""Alternate clue search that extends an existing region rather than reflooding."""

from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache

from clue_analysis import ClueAnalysis, PI_HIGH, PI_LOW, STEPS, fragment_for_edge
from puzzle_gui import Region, allowed_arc_configurations, arc_endpoints


@dataclass
class _Partial:
    fragments: set = field(default_factory=set)
    frontier: dict = field(default_factory=dict)
    reached: set = field(default_factory=set)
    corners: dict = field(default_factory=dict)
    sharp_corners: set = field(default_factory=set)
    counts: tuple = (0, 0, 0)


def analyze_clue_incremental(state, selected, accepted_limit=25, stop_event=None,
                             progress=None):
    """Use the original branching order and bounds with incremental region data.

    Parent snapshots are read-only. Each branch adds only newly reached
    fragments, updates its frontier and area counts, and rechecks sharp joins
    only at affected corners. Geometry is cached for this immutable search.
    """
    r, c = selected
    rows, columns = state["rows"], state["columns"]
    if not (0 <= r < rows and 0 <= c < columns):
        raise ValueError("Select a cell within the grid.")
    target = state["cells"][r][c]["number"]
    if target is None:
        raise ValueError("Select a cell containing a clue.")
    domains = {(r, c): allowed_arc_configurations(state, r, c)
               for r in range(rows) for c in range(columns)}
    if any(not domain for domain in domains.values()):
        return ClueAnalysis(invalid_pruned=1)
    fixed = {cell: domain[0] for cell, domain in domains.items() if len(domain) == 1}

    @lru_cache(maxsize=None)
    def geometry(r, c, orientation, side):
        neighbors, endpoints = [], []
        if orientation is not None:
            endpoints.extend((corner, tangent, True)
                             for corner, tangent in arc_endpoints(r, c, orientation))
        for edge, dr, dc, opposite in STEPS:
            if fragment_for_edge(orientation, edge) != side:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < columns:
                neighbors.append((nr, nc, opposite))
            else:
                if edge == "N":
                    border = (((r, c), (1, 0)), ((r, c + 1), (-1, 0)))
                elif edge == "S":
                    border = (((r + 1, c), (1, 0)), ((r + 1, c + 1), (-1, 0)))
                elif edge == "W":
                    border = (((r, c), (0, 1)), ((r + 1, c), (0, -1)))
                else:
                    border = (((r, c + 1), (0, 1)), ((r + 1, c + 1), (0, -1)))
                endpoints.extend((corner, tangent, False) for corner, tangent in border)
        return tuple(neighbors), tuple(endpoints)

    @lru_cache(maxsize=None)
    def incident_cells(vr, vc):
        return tuple((r, c) for r in (vr - 1, vr) for c in (vc - 1, vc)
                     if 0 <= r < rows and 0 <= c < columns)

    def expand(parent, assigned, seed):
        partial = _Partial(set(parent.fragments), dict(parent.frontier),
                           set(parent.reached), dict(parent.corners),
                           set(parent.sharp_corners), parent.counts)
        counts = list(parent.counts)
        affected = set()
        queue = deque([seed])
        while queue:
            r, c, side = queue.popleft()
            if (r, c, side) in partial.fragments:
                continue
            orientation = assigned[(r, c)]
            if orientation is not None and (r, c, 1 - side) in partial.fragments:
                return None
            if side == 0 and state["cells"][r][c]["number"] not in (None, target):
                return None
            partial.fragments.add((r, c, side))
            partial.reached.add((r, c))
            partial.frontier.pop((r, c), None)
            counts[0 if orientation is None else 1 if side == 0 else 2] += 1
            affected.update(((r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1)))
            neighbors, endpoints = geometry(r, c, orientation, side)
            for corner, tangent, arc in endpoints:
                partial.corners[corner] = partial.corners.get(corner, ()) + ((tangent, arc),)
            for nr, nc, opposite in neighbors:
                cell = (nr, nc)
                if cell in assigned:
                    queue.append((nr, nc, fragment_for_edge(assigned[cell], opposite)))
                else:
                    partial.frontier[cell] = partial.frontier.get(cell, frozenset()) | {opposite}
        for corner in affected:
            entries = partial.corners.get(corner, ())
            sharp = (len(entries) == 2 and any(arc for _, arc in entries)
                     and all(cell in partial.reached for cell in incident_cells(*corner))
                     and entries[0][0] != (-entries[1][0][0], -entries[1][0][1]))
            if sharp:
                partial.sharp_corners.add(corner)
            else:
                partial.sharp_corners.discard(corner)
        partial.counts = tuple(counts)
        return partial

    def minimum_area(partial):
        whole, inside, outside = partial.counts
        count = len(partial.frontier)
        constant = whole + outside + count
        coefficient = inside - outside - count
        lower = constant + coefficient * (PI_LOW if coefficient >= 0 else PI_HIGH) / 4
        rounded = -(-lower.numerator // lower.denominator)
        return max(rounded, whole + max(inside, outside))

    empty = _Partial()
    stack = [(fixed | {selected: orientation}, empty, (*selected, 0))
             for orientation in reversed(domains[selected])]
    result, signatures = ClueAnalysis(), set()
    while stack:
        if stop_event is not None and stop_event.is_set():
            result.cancelled = True
            break
        assigned, parent, seed = stack.pop()
        result.explored += 1
        if progress and result.explored % 256 == 0:
            progress(result.explored, len(result.accepted_states))
        partial = expand(parent, assigned, seed)
        if partial is None:
            result.invalid_pruned += 1
            continue
        area = minimum_area(partial)
        if area > target:
            result.area_pruned += 1
            continue
        if area * max(1, len(partial.sharp_corners)) > target:
            result.score_pruned += 1
            continue
        if not partial.frontier:
            # Only reached cells matter to this Region; copy just those cells.
            candidate = {**state, "cells": [list(row) for row in state["cells"]]}
            for r, c in partial.reached:
                candidate["cells"][r][c] = {**state["cells"][r][c], "arc": assigned[(r, c)]}
            region = Region(0, frozenset(partial.fragments), *partial.counts)
            if region.determine_score(candidate) != target:
                result.score_pruned += 1
                continue
            signature = tuple((r, c, assigned[(r, c)]) for r, c in sorted(partial.reached))
            if signature not in signatures:
                signatures.add(signature)
                result.accepted_states.append(signature)
                if len(result.accepted_states) > accepted_limit:
                    result.limit_reached = True
                    break
            continue
        cell = min(partial.frontier, key=lambda cell: (-len(partial.frontier[cell]), cell))
        for orientation in reversed(domains[cell]):
            required = {fragment_for_edge(orientation, edge) for edge in partial.frontier[cell]}
            if len(required) == 1:
                stack.append((assigned | {cell: orientation}, partial, (*cell, next(iter(required)))))
    return result
