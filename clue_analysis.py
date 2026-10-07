"""Clue-local region search with conservative, exact pruning bounds."""

from collections import deque
from dataclasses import dataclass, field
from fractions import Fraction

from puzzle_gui import ARC_CYCLE, Region, arc_endpoints, allowed_arc_configurations


INSIDE_EDGES = {"tl": "NW", "tr": "NE", "br": "SE", "bl": "SW"}
STEPS = (("N", -1, 0, "S"), ("E", 0, 1, "W"),
         ("S", 1, 0, "N"), ("W", 0, -1, "E"))
PI_LOW = Fraction("3.14159265358979323846264338327950288419716939937510")
PI_HIGH = PI_LOW + Fraction(1, 10 ** 50)


@dataclass
class ClueAnalysis:
    accepted_states: list = field(default_factory=list)
    explored: int = 0
    area_pruned: int = 0
    score_pruned: int = 0
    invalid_pruned: int = 0
    limit_reached: bool = False
    cancelled: bool = False


def fragment_for_edge(orientation, edge):
    return 0 if orientation is None or edge in INSIDE_EDGES[orientation] else 1


def partial_region(state, selected, assigned):
    """Flood decided fragments and forced green cells; stop at undecided cells."""
    rows, columns = state["rows"], state["columns"]
    queue = deque([(*selected, 0)])  # The quarter-disc contains > half the clue.
    fragments, frontier = set(), {}
    while queue:
        r, c, side = queue.popleft()
        if (r, c, side) in fragments:
            continue
        orientation = assigned[(r, c)]
        if orientation is not None and (r, c, 1 - side) in fragments:
            return None, None
        fragments.add((r, c, side))
        for edge, dr, dc, opposite in STEPS:
            if fragment_for_edge(orientation, edge) != side:
                continue
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < columns):
                continue
            if (nr, nc) not in assigned:
                frontier.setdefault((nr, nc), set()).add(opposite)
            else:
                queue.append((nr, nc, fragment_for_edge(assigned[(nr, nc)], opposite)))
    return fragments, frontier


def area_lower_bound(state, assigned, fragments, frontier):
    """Lower bound on eventual integer area, using rational bounds for pi.

    Every frontier cell must contribute at least 1-pi/4, counted once even
    if several edges require it. Forced green cells have already been flooded,
    so their unassigned neighbors are included in this frontier too.
    """
    whole = inside = outside = 0
    for r, c, side in fragments:
        if assigned[(r, c)] is None:
            whole += 1
        elif side == 0:
            inside += 1
        else:
            outside += 1
    constant = whole + outside + len(frontier)
    coefficient = inside - outside - len(frontier)
    lower = constant + coefficient * (PI_LOW if coefficient >= 0 else PI_HIGH) / 4
    rounded = -(-lower.numerator // lower.denominator)
    # Balanced counts require at least max(inside, outside) of each kind.
    return max(rounded, whole + max(inside, outside))


def confirmed_smooth_piece_bound(state, assigned, fragments):
    """Count only irrevocable sharp joins, never current disconnected chains.

    A corner is resolved only when all incident in-grid cells are decided
    and already reached by this region (so no extra boundary can arrive later).
    With exactly two known perimeter endpoints, a nonmatching tangent pair
    involving an arc is a forced sharp join. Such joins cannot disappear as
    the region grows, even if its open smooth chains wrap around and merge.
    """
    corners = {}
    for r, c, side in fragments:
        orientation = assigned[(r, c)]
        if orientation is not None:
            for corner, tangent in arc_endpoints(r, c, orientation):
                corners.setdefault(corner, []).append((tangent, True))
        borders = (
            ("N", r == 0, (((r, c), (1, 0)), ((r, c + 1), (-1, 0)))),
            ("S", r == state["rows"] - 1,
             (((r + 1, c), (1, 0)), ((r + 1, c + 1), (-1, 0)))),
            ("W", c == 0, (((r, c), (0, 1)), ((r + 1, c), (0, -1)))),
            ("E", c == state["columns"] - 1,
             (((r, c + 1), (0, 1)), ((r + 1, c + 1), (0, -1)))),
        )
        for edge, on_border, endpoints in borders:
            if on_border and fragment_for_edge(orientation, edge) == side:
                for corner, tangent in endpoints:
                    corners.setdefault(corner, []).append((tangent, False))
    sharp = 0
    for (vr, vc), entries in corners.items():
        if len(entries) != 2 or not any(arc for _, arc in entries):
            continue
        incident = [(r, c) for r in (vr - 1, vr) for c in (vc - 1, vc)
                    if 0 <= r < state["rows"] and 0 <= c < state["columns"]]
        reached_cells = {(r, c) for r, c, side in fragments}
        if not all(cell in assigned and cell in reached_cells for cell in incident):
            continue
        a, b = entries[0][0], entries[1][0]
        if a != (-b[0], -b[1]):
            sharp += 1
    return max(1, sharp)


def analyze_clue(state, selected, accepted_limit=25, stop_event=None, progress=None):
    """Enumerate completed local clue regions, stopping after limit+1 accepts.

    Existing arcs are fixed; blank whites are undecided. Unreached cells are
    not enumerated, so accepted states are local region configurations rather
    than complete puzzle solutions. The input is never modified.
    """
    r, c = selected
    if not (0 <= r < state["rows"] and 0 <= c < state["columns"]):
        raise ValueError("Select a cell within the grid.")
    target = state["cells"][r][c]["number"]
    if target is None:
        raise ValueError("Select a cell containing a clue.")
    domains = {(r, c): allowed_arc_configurations(state, r, c)
               for r, row in enumerate(state["cells"]) for c, cell in enumerate(row)}
    if any(not domain for domain in domains.values()):
        return ClueAnalysis(invalid_pruned=1)
    fixed = {cell: domain[0] for cell, domain in domains.items() if len(domain) == 1}
    choices = domains[selected]
    stack = [fixed | {selected: orientation} for orientation in reversed(choices)]
    result, signatures = ClueAnalysis(), set()
    while stack:
        if stop_event is not None and stop_event.is_set():
            result.cancelled = True
            break
        assigned = stack.pop()
        result.explored += 1
        if progress and result.explored % 256 == 0:
            progress(result.explored, len(result.accepted_states))
        fragments, frontier = partial_region(state, selected, assigned)
        if fragments is None:
            result.invalid_pruned += 1
            continue
        # A region containing the majority of another clue must satisfy it too.
        if any(side == 0 and state["cells"][r][c]["number"] not in (None, target)
               for r, c, side in fragments):
            result.invalid_pruned += 1
            continue
        minimum_area = area_lower_bound(state, assigned, fragments, frontier)
        if minimum_area > target:
            result.area_pruned += 1
            continue
        if minimum_area * confirmed_smooth_piece_bound(state, assigned, fragments) > target:
            result.score_pruned += 1
            continue
        if not frontier:
            candidate = {**state, "cells": [[dict(cell) for cell in row] for row in state["cells"]]}
            for (r, c), orientation in assigned.items():
                candidate["cells"][r][c]["arc"] = orientation
            region = Region.from_fragments(0, fragments, candidate)
            if region.determine_score(candidate) != target:
                result.score_pruned += 1
                continue
            reached = {(r, c) for r, c, side in fragments}
            signature = tuple((r, c, assigned[(r, c)]) for r, c in sorted(reached))
            if signature not in signatures:
                signatures.add(signature)
                result.accepted_states.append(signature)
                if len(result.accepted_states) > accepted_limit:
                    result.limit_reached = True
                    break
            continue
        # Most constrained frontier first, with deterministic tie-breaking.
        cell = min(frontier, key=lambda cell: (-len(frontier[cell]), cell))
        for orientation in reversed(domains[cell]):
            required_sides = {fragment_for_edge(orientation, edge) for edge in frontier[cell]}
            if len(required_sides) == 1:
                stack.append(assigned | {cell: orientation})
    return result


def incorporate_analysis(state, result):
    """Learn only from exhaustive, nonempty results and apply unique states.

    A cell absent from any accepted local region has no restriction inferred:
    its unenumerated external configurations might all still be possible.
    """
    changes = {"removed": 0, "applied": False}
    if result.limit_reached or result.cancelled or not result.accepted_states:
        return changes
    assignments = [{(r, c): orientation for r, c, orientation in accepted}
                   for accepted in result.accepted_states]
    mandatory = set(assignments[0]).intersection(*(set(accepted) for accepted in assignments[1:]))
    domains = [[list(allowed_arc_configurations(state, r, c)) for c in range(state["columns"])]
               for r in range(state["rows"])]
    for r, c in mandatory:
        supported = {accepted[(r, c)] for accepted in assignments}
        old = domains[r][c]
        domains[r][c] = [orientation for orientation in old if orientation in supported]
        if not domains[r][c]:
            raise ValueError("Analysis contradicts the current master list.")
        changes["removed"] += len(old) - len(domains[r][c])
    state["arc_domains"] = domains
    if len(assignments) == 1:
        for (r, c), orientation in assignments[0].items():
            state["cells"][r][c]["arc"] = orientation
        changes["applied"] = True
    return changes
