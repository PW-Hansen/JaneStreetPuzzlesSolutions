"""Clue-local region search with conservative, exact pruning bounds."""

from collections import deque
from dataclasses import dataclass, field
from fractions import Fraction

from puzzle_gui import ARC_CYCLE, Region, arc_endpoints, allowed_arc_configurations, clue_factorizations


INSIDE_EDGES = {"tl": "NW", "tr": "NE", "br": "SE", "bl": "SW"}
STEPS = (("N", -1, 0, "S"), ("E", 0, 1, "W"),
         ("S", 1, 0, "N"), ("W", 0, -1, "E"))
PI_LOW = Fraction("3.14159265358979323846264338327950288419716939937510")
PI_HIGH = PI_LOW + Fraction(1, 10 ** 50)


def frontier_priorities(state):
    """One point per category, using orthogonal neighbors and outer borders."""
    rows, columns = state["rows"], state["columns"]
    priorities = {}
    for r in range(rows):
        for c in range(columns):
            neighbors = [state["cells"][r + dr][c + dc] for _, dr, dc, _ in STEPS
                         if 0 <= r + dr < rows and 0 <= c + dc < columns]
            priorities[(r, c)] = (int(any(cell["green"] for cell in neighbors))
                                  + int(any(cell["number"] is not None for cell in neighbors))
                                  + int(r in (0, rows - 1) or c in (0, columns - 1)))
    return priorities


def choose_frontier_cell(frontier, priorities, prioritize_connections=True, choice_counts=None):
    """Add +2 once when a frontier cell connects through multiple edges."""
    def score(cell):
        return priorities[cell] + 2 * (prioritize_connections and len(frontier[cell]) >= 2)
    return min(frontier, key=lambda cell: (
        choice_counts[cell] if choice_counts is not None else -len(frontier[cell]),
        -score(cell), -len(frontier[cell]), cell))


@dataclass
class ClueAnalysis:
    accepted_states: list = field(default_factory=list)
    explored: int = 0
    area_pruned: int = 0
    score_pruned: int = 0
    invalid_pruned: int = 0
    limit_reached: bool = False
    cancelled: bool = False
    elapsed_seconds: float = field(default=0.0, compare=False)
    factorizations: tuple = ()
    factorization_pruned: int = 0
    worklist_limit_reached: bool = False
    secondary_checks: int = 0
    secondary_branches: int = 0
    secondary_pruned: int = 0
    secondary_cutoffs: int = 0
    regular_switches: int = 0
    secondary_cache_hits: int = 0
    perimeter_capacity_pruned: int = 0
    source_clue: tuple | None = field(default=None, compare=False)


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


def minimum_perimeter_pieces(confirmed_sharp_joins, confirmed_quarter_turns=0):
    """A valid integer-area region cannot have just one sharp perimeter join.

    Quarter-circle turning contributes the same pi/4 coefficient as area.
    Integer area requires that coefficient to vanish. With exactly one sharp
    join (a nonzero quarter/half turn), total boundary turning cannot satisfy
    this, even allowing smooth holes. Thus any confirmed sharp join rules out
    a one-piece perimeter; separate open chains are still not counted.
    """
    # Balanced quarter-disc contributions give zero net smooth turning for
    # integer area. Total boundary turning is a multiple of a full turn, so
    # an odd number of 90-degree joins needs another 90-degree join. Cusps
    # contribute 180 degrees and do not change this parity.
    required = confirmed_sharp_joins + confirmed_quarter_turns % 2
    return max(2, required) if confirmed_sharp_joins else 1


def compatible_factorizations(factorizations, minimum_area, minimum_pieces):
    """Retain score pairs whose area and piece count can still be reached."""
    return tuple((area, pieces) for area, pieces in factorizations
                 if area >= minimum_area and pieces >= minimum_pieces)


def confirmed_smooth_piece_bound(state, assigned, fragments):
    """Count only irrevocable sharp joins, never current disconnected chains.

    A corner is resolved only when all incident in-grid cells are decided
    and already reached by this region (so no extra boundary can arrive later).
    With exactly two known perimeter endpoints, a nonmatching tangent pair
    is a forced sharp join, including bends at grid corners. Such joins cannot disappear as
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
    sharp = quarter_turns = 0
    for (vr, vc), entries in corners.items():
        if len(entries) != 2:
            continue
        incident = [(r, c) for r in (vr - 1, vr) for c in (vc - 1, vc)
                    if 0 <= r < state["rows"] and 0 <= c < state["columns"]]
        reached_cells = {(r, c) for r, c, side in fragments}
        if not all(cell in assigned and cell in reached_cells for cell in incident):
            continue
        a, b = entries[0][0], entries[1][0]
        if a != (-b[0], -b[1]):
            sharp += 1
            quarter_turns += a[0] * b[0] + a[1] * b[1] == 0
    return minimum_perimeter_pieces(sharp, quarter_turns)


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
    factorizations = tuple(clue_factorizations(state, selected))
    priorities = frontier_priorities(state)
    domains = {(r, c): allowed_arc_configurations(state, r, c)
               for r, row in enumerate(state["cells"]) for c, cell in enumerate(row)}
    from arc_constraints import propagate_arc_domains
    domains = propagate_arc_domains(state, domains=domains)
    if domains is None:
        return ClueAnalysis(invalid_pruned=1, factorizations=factorizations)
    if any(not domain for domain in domains.values()):
        return ClueAnalysis(invalid_pruned=1, factorizations=factorizations)
    fixed = {cell: domain[0] for cell, domain in domains.items() if len(domain) == 1}
    choices = domains[selected]
    stack = [fixed | {selected: orientation} for orientation in reversed(choices)]
    result, signatures = ClueAnalysis(factorizations=factorizations, source_clue=selected), set()
    while stack:
        if stop_event is not None and stop_event.is_set():
            result.cancelled = True
            break
        assigned = stack.pop()
        branch_domains = propagate_arc_domains(state, assigned, domains) if state.get('arc_implications') else domains
        if branch_domains is None:
            result.invalid_pruned += 1
            continue
        if state.get('arc_implications'):
            assigned.update({cell: values[0] for cell, values in branch_domains.items() if len(values) == 1})
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
        if not compatible_factorizations(factorizations, minimum_area, 1):
            result.area_pruned += 1
            result.factorization_pruned += 1
            continue
        minimum_pieces = confirmed_smooth_piece_bound(state, assigned, fragments)
        if not compatible_factorizations(factorizations, minimum_area, minimum_pieces):
            result.score_pruned += 1
            result.factorization_pruned += 1
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
        choice_counts = {cell: sum(len({fragment_for_edge(arc, edge) for edge in edges}) == 1
                                   for arc in branch_domains[cell]) for cell, edges in frontier.items()}
        cell = choose_frontier_cell(frontier, priorities, choice_counts=choice_counts)
        for orientation in reversed(branch_domains[cell]):
            required_sides = {fragment_for_edge(orientation, edge) for edge in frontier[cell]}
            if len(required_sides) == 1:
                stack.append(assigned | {cell: orientation})
    return result


def incorporate_analysis(state, result):
    """Learn supported domains and apply configurations conclusively forced.

    A cell absent from any accepted local region has no restriction inferred:
    its unenumerated external configurations might all still be possible.
    """
    changes = {"removed": 0, "applied": False}
    if result.limit_reached or result.cancelled or result.worklist_limit_reached:
        return changes
    if not result.accepted_states:
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
        if len(domains[r][c]) == 1:
            orientation = domains[r][c][0]
            if len(old) > 1 or state["cells"][r][c]["arc"] != orientation:
                state["cells"][r][c]["arc"] = orientation
                changes["forced"] = changes.get("forced", 0) + 1
    state["arc_domains"] = domains
    from arc_constraints import learn_arc_implications
    learned = learn_arc_implications(state, assignments, mandatory, result.source_clue)
    if learned:
        changes['implications'] = learned
        from arc_constraints import apply_arc_deductions
        forced = apply_arc_deductions(state)
        if forced:
            changes['forced'] = changes.get('forced', 0) + forced
    if len(assignments) == 1:
        for (r, c), orientation in assignments[0].items():
            state["cells"][r][c]["arc"] = orientation
        changes["applied"] = True
    return changes
