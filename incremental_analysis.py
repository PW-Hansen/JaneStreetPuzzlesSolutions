"""Alternate clue search that extends an existing region rather than reflooding."""

from collections import deque, OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from fractions import Fraction

from clue_analysis import (ClueAnalysis, PI_HIGH, PI_LOW, STEPS, INSIDE_EDGES, fragment_for_edge,
                           compatible_factorizations, minimum_perimeter_pieces,
                           frontier_priorities, choose_frontier_cell)
from puzzle_gui import Region, allowed_arc_configurations, arc_endpoints, clue_factorizations
from arc_constraints import propagate_arc_domains, make_arc_domain_propagator


@dataclass(frozen=True)
class SimplifiedArc:
    """Region-facing adjacent edges, with the remaining concrete choices."""
    edges: str
    options: tuple


def edge_side(orientation, edge):
    if isinstance(orientation, SimplifiedArc):
        return 0 if edge in orientation.edges else 1
    return fragment_for_edge(orientation, edge)


def simplified_choices(domain, incoming):
    """Group arcs by the pair of edges reached from the incoming frontier."""
    choices = [None] if None in domain else []
    groups = {}
    for orientation in domain:
        if orientation is None:
            continue
        sides = {fragment_for_edge(orientation, edge) for edge in incoming}
        if len(sides) != 1:
            continue
        side = next(iter(sides))
        edges = ''.join(edge for edge in 'NESW'
                        if fragment_for_edge(orientation, edge) == side)
        groups.setdefault(edges, []).append(orientation)
    return choices + [SimplifiedArc(edges, tuple(options)) for edges, options in groups.items()]


@dataclass
class _Partial:
    fragments: set = field(default_factory=set)
    frontier: dict = field(default_factory=dict)
    reached: set = field(default_factory=set)
    corners: dict = field(default_factory=dict)
    sharp_corners: set = field(default_factory=set)
    counts: tuple = (0, 0, 0)
    half_cells: int = 0
    unresolved_corners: set = field(default_factory=set)
    quarter_turn_corners: set = field(default_factory=set)


def analyze_clue_incremental(state, selected, accepted_limit=25, stop_event=None,
                             progress=None, check_other_clues=True, worklist_limit=None,
                             secondary_worklist_limit=25, simplify_nonclue=True,
                             prioritize_frontier=True):
    """Expand regions with grouped non-clue arcs, then validate concrete curves.

    Parent snapshots are read-only. Each branch adds only newly reached
    fragments, updates its frontier and area counts, and rechecks sharp joins
    only at affected corners. Undecided non-clue curves with identical region
    edges share one branch and contribute a half-cell during expansion. Fixed
    curves and clue cells retain their concrete geometry. Geometry is cached.
    """
    propagate_arc_domains = make_arc_domain_propagator(state)
    r, c = selected
    rows, columns = state["rows"], state["columns"]
    if not (0 <= r < rows and 0 <= c < columns):
        raise ValueError("Select a cell within the grid.")
    target = state["cells"][r][c]["number"]
    if target is None:
        raise ValueError("Select a cell containing a clue.")
    factorizations = tuple(clue_factorizations(state, selected))
    factor_areas = sorted({a for a, _ in factorizations})
    complex_threshold = (factor_areas[-2] if len(factor_areas) > 1
                         else factor_areas[-1] if factor_areas else 0)
    priorities = (frontier_priorities(state) if prioritize_frontier else
                  {(r, c): 0 for r in range(rows) for c in range(columns)})
    domains = {(r, c): allowed_arc_configurations(state, r, c)
               for r in range(rows) for c in range(columns)}
    domains = propagate_arc_domains(state, domains=domains)
    if domains is None:
        return ClueAnalysis(invalid_pruned=1, factorizations=factorizations)
    if any(not domain for domain in domains.values()):
        return ClueAnalysis(invalid_pruned=1, factorizations=factorizations)
    propagate_arc_domains.restrict(domains)
    fixed = {cell: domain[0] for cell, domain in domains.items() if len(domain) == 1}
    secondary_cache = SecondarySearchCache(state, stop_event, secondary_worklist_limit,
                                            prioritize_frontier)

    @lru_cache(maxsize=None)
    def geometry(r, c, orientation, side):
        neighbors, endpoints = [], []
        if orientation is not None and not isinstance(orientation, SimplifiedArc):
            endpoints.extend((corner, tangent, True)
                             for corner, tangent in arc_endpoints(r, c, orientation))
        for edge, dr, dc, opposite in STEPS:
            if edge_side(orientation, edge) != side:
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

    def expand(parent, assigned, seed, extra_seeds=()):
        partial = _Partial(set(parent.fragments), dict(parent.frontier),
                           set(parent.reached), dict(parent.corners),
                           set(parent.sharp_corners), parent.counts,
                           parent.half_cells, set(parent.unresolved_corners),
                           set(parent.quarter_turn_corners))
        counts = list(parent.counts)
        affected = set()
        queue = deque([seed, *extra_seeds])
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
            if isinstance(orientation, SimplifiedArc):
                partial.half_cells += 1
                # Tangents cannot be confirmed until the concrete arc is chosen.
                representative = orientation.options[0]
                partial.unresolved_corners.update(corner for corner, _ in
                                                  arc_endpoints(r, c, representative))
            else:
                counts[0 if orientation is None else 1 if side == 0 else 2] += 1
            affected.update(((r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1)))
            neighbors, endpoints = geometry(r, c, orientation, side)
            for corner, tangent, arc in endpoints:
                partial.corners[corner] = partial.corners.get(corner, ()) + ((tangent, arc),)
            for nr, nc, opposite in neighbors:
                cell = (nr, nc)
                if cell in assigned:
                    queue.append((nr, nc, edge_side(assigned[cell], opposite)))
                else:
                    partial.frontier[cell] = partial.frontier.get(cell, frozenset()) | {opposite}
        for corner in affected:
            entries = partial.corners.get(corner, ())
            sharp = (corner not in partial.unresolved_corners
                     and len(entries) == 2
                     and all(cell in partial.reached for cell in incident_cells(*corner))
                     and entries[0][0] != (-entries[1][0][0], -entries[1][0][1]))
            if sharp:
                partial.sharp_corners.add(corner)
                a, b = entries[0][0], entries[1][0]
                if a[0] * b[0] + a[1] * b[1] == 0:
                    partial.quarter_turn_corners.add(corner)
                else:
                    partial.quarter_turn_corners.discard(corner)
            else:
                partial.sharp_corners.discard(corner)
                partial.quarter_turn_corners.discard(corner)
        partial.counts = tuple(counts)
        return partial

    def minimum_area(partial, regular=False):
        whole, inside, outside = partial.counts
        if simplify_nonclue and not regular:
            # Fixed arcs retain their proper quarter-disc/complement contribution.
            coefficient = inside - outside
            lower = (whole + outside + Fraction(partial.half_cells, 2)
                     + coefficient * (PI_LOW if coefficient >= 0 else PI_HIGH) / 4)
            for cell in partial.frontier:
                domain = domains[cell]
                if domain == (None,):
                    lower += 1
                elif state['cells'][cell[0]][cell[1]]['number'] is None and len(domain) > 1:
                    lower += Fraction(1, 2) if any(arc is not None for arc in domain) else 1
                else:
                    lower += 1 - PI_HIGH / 4
            # A concrete realization may exchange a simplified inside for an
            # outside. Its eventual integer area balances *all* arc fragments;
            # do not round the mixed approximation up past that balanced area.
            balanced = whole + Fraction(inside + outside + partial.half_cells, 2)
            balanced += sum(Fraction(1, 2) if any(arc is not None for arc in domains[cell])
                            else 1 for cell in partial.frontier)
            lower = min(lower, balanced)
            return -(-lower.numerator // lower.denominator)
        count = len(partial.frontier)
        constant = whole + outside + count
        coefficient = inside - outside - count
        lower = constant + coefficient * (PI_LOW if coefficient >= 0 else PI_HIGH) / 4
        rounded = -(-lower.numerator // lower.denominator)
        return max(rounded, whole + max(inside, outside))

    empty = _Partial()
    stack = [(fixed | {selected: orientation}, empty, (*selected, 0), not simplify_nonclue,
              domains, (selected, orientation))
             for orientation in reversed(domains[selected])]
    result, signatures = ClueAnalysis(factorizations=factorizations, source_clue=selected), set()
    while stack:
        if stop_event is not None and stop_event.is_set():
            result.cancelled = True
            break
        # Only secondary searches pass a worklist limit; main searches stay unlimited.
        if worklist_limit is not None and len(stack) > worklist_limit:
            result.worklist_limit_reached = True
            break
        assigned, parent, seed, regular, parent_domains, placement = stack.pop()
        extra_seeds = ()
        if state.get('arc_implications'):
            branch_domains, domain_changes = propagate_arc_domains.extend(parent_domains, *placement)
        else:
            branch_domains = domains
        if branch_domains is None:
            result.invalid_pruned += 1
            continue
        if state.get('arc_implications'):
            resolved = dict(assigned)
            for cell in domain_changes:
                values = branch_domains[cell]
                if len(values) == 1:
                    resolved[cell] = values[0]
                elif isinstance(resolved.get(cell), SimplifiedArc):
                    value = resolved[cell]
                    resolved[cell] = SimplifiedArc(value.edges, tuple(arc for arc in value.options if arc in values))
            if resolved != assigned:
                changed_cells = {cell for cell, value in resolved.items()
                                 if cell not in assigned or assigned[cell] != value}
                if changed_cells & parent.reached:
                    parent, seed = empty, (*selected, 0)
                else:
                    extra_seeds = tuple((*cell, edge_side(resolved[cell], edge))
                                        for cell in changed_cells if cell in parent.frontier
                                        for edge in parent.frontier[cell])
                assigned = resolved
        result.explored += 1
        if progress and result.explored % 256 == 0:
            progress(result.explored, len(result.accepted_states))
        partial = expand(parent, assigned, seed, extra_seeds)
        if partial is None:
            result.invalid_pruned += 1
            continue
        whole, inside, outside = partial.counts
        if not partial.frontier:
            enclosed_area = Fraction(2 * whole + inside + outside + partial.half_cells, 2)
            capacity = enclosed_perimeter_capacity(state, assigned, partial.fragments)
            if enclosed_area > 0 and Fraction(target, 1) / enclosed_area > capacity:
                result.perimeter_capacity_pruned += 1
                result.score_pruned += 1
                continue
        coefficient = inside - outside
        current_area = (whole + outside + Fraction(partial.half_cells, 2)
                        + coefficient * (PI_LOW if coefficient >= 0 else PI_HIGH) / 4)
        if not regular and current_area > complex_threshold:
            regular = True
            result.regular_switches += 1
        if regular and partial.half_cells:
            budgets = compatible_factorizations(factorizations, minimum_area(partial), 1)
            if not budgets or not partial_curve_feasible(
                    partial, assigned, incident_cells, max(p for _, p in budgets),
                    stop_event, worklist_limit, result):
                if stop_event is not None and stop_event.is_set():
                    result.cancelled = True
                    break
                result.score_pruned += 1
                continue
            if result.worklist_limit_reached:
                break
            # Resolve one grouped cell per worklist step, reflooding the same
            # topology with concrete sides and exact counts. Subsequent steps
            # stay in regular mode, even if this choice reduces the area.
            cell = next(cell for cell in sorted(partial.reached)
                        if isinstance(assigned[cell], SimplifiedArc))
            for orientation in reversed(assigned[cell].options):
                stack.append((assigned | {cell: orientation}, empty, (*selected, 0), True,
                              branch_domains, (cell, orientation)))
            continue
        area = minimum_area(partial, regular)
        if not compatible_factorizations(factorizations, area, 1):
            result.area_pruned += 1
            result.factorization_pruned += 1
            continue
        pieces = minimum_perimeter_pieces(len(partial.sharp_corners), len(partial.quarter_turn_corners))
        if not compatible_factorizations(factorizations, area, pieces):
            result.score_pruned += 1
            result.factorization_pruned += 1
            continue
        if check_other_clues:
            other_clues = sorted({(r, c) for r, c, side in partial.fragments
                                  if (r, c) != selected and assigned[(r, c)] is not None
                                  and state["cells"][r][c]["number"] is not None})
            rejected = False
            for other in other_clues:
                if not secondary_clue_constrained(state, assigned, other, domains):
                    continue
                secondary, cached = secondary_cache.check(assigned, other)
                result.secondary_checks += 1
                result.secondary_cache_hits += cached
                if not cached:
                    result.secondary_branches += secondary.explored
                if secondary.cancelled:
                    result.cancelled = True
                    break
                if secondary.worklist_limit_reached:
                    result.secondary_cutoffs += 1
                elif not secondary.accepted_states:
                    result.secondary_pruned += 1
                    rejected = True
                    break
            if result.cancelled:
                break
            if rejected:
                continue
        if not partial.frontier:
            if simplify_nonclue and not regular:
                whole, inside, outside = partial.counts
                area = Fraction(2 * whole + inside + outside + partial.half_cells, 2)
                if not any(a == area for a, _ in factorizations):
                    result.area_pruned += 1
                    result.factorization_pruned += 1
                    continue
                found = False
                for signature in concrete_completions(state, assigned, partial.fragments,
                                                       target, stop_event, worklist_limit, result):
                    found = True
                    if signature not in signatures:
                        signatures.add(signature)
                        result.accepted_states.append(signature)
                        if len(result.accepted_states) > accepted_limit:
                            result.limit_reached = True
                            break
                if stop_event is not None and stop_event.is_set():
                    result.cancelled = True
                    break
                if result.limit_reached:
                    break
                if result.worklist_limit_reached:
                    break
                if not found:
                    result.score_pruned += 1
                continue
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
        legal_choices = {}
        lookahead = {}
        for cell, edges in partial.frontier.items():
            choices = (simplified_choices(branch_domains[cell], edges)
                       if not regular and state['cells'][cell[0]][cell[1]]['number'] is None
                       else branch_domains[cell])
            viable = []
            for arc in choices:
                required = {edge_side(arc, edge) for edge in edges}
                if len(required) != 1:
                    continue
                seed = (*cell, next(iter(required)))
                # Count actual surviving placements, including forced green
                # growth and conflicting clue/arc-side checks, for MRV.
                grown = expand(partial, assigned | {cell: arc}, seed)
                if grown is not None:
                    viable.append(arc)
                    lookahead[(cell, arc)] = grown
            legal_choices[cell] = tuple(viable)
        cell = choose_frontier_cell(partial.frontier, priorities,
                                    prioritize_connections=prioritize_frontier,
                                    choice_counts={cell: len(choices) for cell, choices in legal_choices.items()})
        for orientation in reversed(legal_choices[cell]):
            side = edge_side(orientation, next(iter(partial.frontier[cell])))
            # Reuse the forced-growth snapshot; the seed is already reached.
            stack.append((assigned | {cell: orientation}, lookahead[(cell, orientation)],
                          (*cell, side), regular, branch_domains, (cell, orientation)))
    return result


def enclosed_perimeter_capacity(state, assigned, fragments):
    """Arc count plus distinct outer-grid sides touched by this region."""
    arcs, borders = set(), set()
    for r, c, side in fragments:
        orientation = assigned[(r, c)]
        if orientation is not None:
            arcs.add((r, c))
        for edge, on_border in (('N', r == 0), ('S', r == state['rows'] - 1),
                                ('W', c == 0), ('E', c == state['columns'] - 1)):
            if on_border and edge_side(orientation, edge) == side:
                borders.add(edge)
    return len(arcs) + len(borders)


def partial_curve_feasible(partial, assigned, incident_cells, max_pieces, stop_event=None,
                           worklist_limit=None, result=None):
    """Resolve curve domains at settled corners before the region is complete.

    Open perimeter chains may still merge; only settled sharp joins constrain
    the count. Success is feasibility of this bound, not a complete solution.
    """
    corners = {corner: [(None, (tangent,)) for tangent, _ in entries]
               for corner, entries in partial.corners.items()}
    variables = {}
    for cell in sorted(partial.reached):
        value = assigned[cell]
        if not isinstance(value, SimplifiedArc):
            continue
        variables[cell] = value.options
        for endpoint in (0, 1):
            corner = arc_endpoints(*cell, value.options[0])[endpoint][0]
            corners.setdefault(corner, []).append((cell, tuple(
                arc_endpoints(*cell, arc)[endpoint][1] for arc in value.options)))
    joins = [entries for corner, entries in corners.items()
             if len(entries) == 2 and all(cell in partial.reached for cell in incident_cells(*corner))]
    active = sorted({cell for entries in joins for cell, _ in entries if cell is not None})
    stack = [{}]
    while stack:
        if stop_event is not None and stop_event.is_set():
            return False
        if worklist_limit is not None and len(stack) > worklist_limit:
            if result is not None:
                result.worklist_limit_reached = True
            return True  # Unknown, rather than a contradiction.
        chosen = stack.pop()
        forced = possible = 0
        for entries in joins:
            domains = [(tangents[chosen[cell]],) if cell in chosen else tangents
                       for cell, tangents in entries]
            smooth = [a == (-b[0], -b[1]) for a in domains[0] for b in domains[1]]
            forced += not any(smooth)
            possible += not all(smooth)
        if minimum_perimeter_pieces(forced) > max_pieces:
            continue
        if minimum_perimeter_pieces(possible) <= max_pieces:
            return True
        cell = next((cell for cell in active if cell not in chosen), None)
        if cell is None:
            return True
        for option in reversed(range(len(variables[cell]))):
            stack.append(chosen | {cell: option})
    return False


def concrete_completions(state, assigned, fragments, target, stop_event=None,
                         worklist_limit=None, result=None):
    """Yield concrete realizations with balanced exact area and the right score.

    Topology remains unchanged: each choice exposes the same two region edges.
    Prune the realization tree when inside/outside balance cannot be recovered.
    """
    reached = sorted((r, c, side) for r, c, side in fragments)
    candidate = {**state, 'cells': [list(row) for row in state['cells']]}
    options = []
    for r, c, side in reached:
        value = assigned[(r, c)]
        choices = value.options if isinstance(value, SimplifiedArc) else (value,)
        options.append(tuple((arc, 0 if arc is None else
                              fragment_for_edge(arc, value.edges[0])
                              if isinstance(value, SimplifiedArc) else side)
                             for arc in choices))
        candidate['cells'][r][c] = dict(state['cells'][r][c])
    minimum, maximum = [0] * (len(options) + 1), [0] * (len(options) + 1)
    for index in range(len(options) - 1, -1, -1):
        contributions = [0 if arc is None else 1 if side == 0 else -1
                         for arc, side in options[index]]
        minimum[index] = minimum[index + 1] + min(contributions)
        maximum[index] = maximum[index + 1] + max(contributions)

    area = Fraction(sum(2 if assigned[(r, c)] is None else 1 for r, c, _ in reached), 2)
    if area.denominator != 1 or target % area:
        return
    wanted_pieces = int(target / area)
    # Boundary corners have fixed locations even while curve tangents are
    # undecided. Rule out sharp joins as soon as both remaining tangent domains
    # make them unavoidable, rather than constructing every complete Region.
    corners = {}
    for index, (r, c, original_side) in enumerate(reached):
        value = assigned[(r, c)]
        if value is not None:
            for endpoint in (0, 1):
                tangents = {arc: arc_endpoints(r, c, arc)[endpoint][1]
                            for arc, _ in options[index]}
                corner = arc_endpoints(r, c, options[index][0][0])[endpoint][0]
                corners.setdefault(corner, []).append((index, tangents))
        for edge, on_border, endpoints in (
            ('N', r == 0, (((r, c), (1, 0)), ((r, c + 1), (-1, 0)))),
            ('S', r == state['rows'] - 1, (((r + 1, c), (1, 0)), ((r + 1, c + 1), (-1, 0)))),
            ('W', c == 0, (((r, c), (0, 1)), ((r + 1, c), (0, -1)))),
            ('E', c == state['columns'] - 1, (((r, c + 1), (0, 1)), ((r + 1, c + 1), (0, -1)))),
        ):
            if on_border and edge_side(value, edge) == original_side:
                for corner, tangent in endpoints:
                    corners.setdefault(corner, []).append((-1, {None: tangent}))
    joins = [entries for entries in corners.values() if len(entries) == 2]
    affected = [[] for _ in options]
    for join, entries in enumerate(joins):
        for owner, _ in entries:
            if owner >= 0:
                affected[owner].append(join)

    def forced_sharp(entries, chosen):
        possible = []
        for owner, tangents in entries:
            possible.append((tangents[chosen[owner][0]],) if 0 <= owner < len(chosen)
                            else tuple(tangents.values()))
        return not any(a == (-b[0], -b[1]) for a in possible[0] for b in possible[1])

    initial_sharp = tuple(forced_sharp(entries, ()) for entries in joins)

    # Iterative DFS also supports long boundaries without a recursion limit.
    stack = [(0, 0, (), initial_sharp)]
    while stack:
        if stop_event is not None and stop_event.is_set():
            return
        if worklist_limit is not None and len(stack) > worklist_limit:
            if result is not None:
                result.worklist_limit_reached = True
            return
        index, balance, chosen, sharp = stack.pop()
        if not minimum[index] <= -balance <= maximum[index]:
            continue
        if minimum_perimeter_pieces(sum(sharp)) > wanted_pieces:
            continue
        if index < len(options):
            for arc, side in reversed(options[index]):
                contribution = 0 if arc is None else 1 if side == 0 else -1
                next_chosen = chosen + ((arc, side),)
                next_sharp = list(sharp)
                for join in affected[index]:
                    next_sharp[join] = forced_sharp(joins[join], next_chosen)
                stack.append((index + 1, balance + contribution, next_chosen, tuple(next_sharp)))
            continue
        concrete_fragments = set()
        for (r, c, _), (arc, side) in zip(reached, chosen):
            candidate['cells'][r][c]['arc'] = arc
            concrete_fragments.add((r, c, side))
        region = Region.from_fragments(0, concrete_fragments, candidate)
        if state.get('arc_implications') and propagate_arc_domains(state, assigned | {
            (r, c): arc for (r, c, _), (arc, _) in zip(reached, chosen)}) is None:
            continue
        if region.determine_score(candidate) == target:
            yield tuple((r, c, arc) for (r, c, _), (arc, _) in zip(reached, chosen))


def secondary_clue_constrained(state, assigned, selected, domains=None, frontier_limit=2):
    """Probe forced growth; avoid a search while the other clue has a wide frontier.

    No branching or area/perimeter analysis is done here. Closed regions and
    obvious contradictions are checked, as are regions with at most two unknown
    frontier cells. Probe from scratch so green chains expose all their exits.
    """
    rows, columns = state['rows'], state['columns']
    if domains is None:
        domains = {(r, c): allowed_arc_configurations(state, r, c)
                   for r in range(rows) for c in range(columns)}
    decided = {cell: domain[0] for cell, domain in domains.items() if len(domain) == 1}
    decided.update(assigned)
    if selected not in decided:
        return False
    target = state['cells'][selected[0]][selected[1]]['number']
    queue = deque([(*selected, 0)])
    fragments, frontier = set(), {}
    while queue:
        r, c, side = queue.popleft()
        if (r, c, side) in fragments:
            continue
        orientation = decided[(r, c)]
        if orientation is not None and (r, c, 1 - side) in fragments:
            return True
        if side == 0 and state['cells'][r][c]['number'] not in (None, target):
            return True
        fragments.add((r, c, side))
        for edge, dr, dc, opposite in STEPS:
            if edge_side(orientation, edge) != side:
                continue
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < columns):
                continue
            cell = (nr, nc)
            if cell in decided:
                queue.append((nr, nc, edge_side(decided[cell], opposite)))
            else:
                frontier[cell] = frontier.get(cell, frozenset()) | {opposite}
    for cell, edges in frontier.items():
        if not any(len({fragment_for_edge(arc, edge) for edge in edges}) == 1
                   for arc in domains[cell]):
            return True
    return len(frontier) <= frontier_limit


class SecondarySearchCache:
    """Run-local bounded memoization and reusable concrete feasibility witnesses."""
    def __init__(self, state, stop_event=None, worklist_limit=25, prioritize_frontier=True):
        self.state, self.stop_event = state, stop_event
        self.worklist_limit, self.prioritize_frontier = worklist_limit, prioritize_frontier
        self.memo = OrderedDict()
        self.witnesses = {}

    def check(self, assigned, selected):
        if self.stop_event is not None and self.stop_event.is_set():
            return ClueAnalysis(cancelled=True), False
        restrictions = {cell: frozenset(value.options if isinstance(value, SimplifiedArc) else (value,))
                        for cell, value in assigned.items()}
        if self.state.get('arc_implications'):
            propagated = propagate_arc_domains(self.state, assigned)
            if propagated is None:
                return ClueAnalysis(), False
            restrictions.update({cell: frozenset(values) for cell, values in propagated.items()})
        key = (selected, frozenset(restrictions.items()))
        if key in self.memo:
            self.memo.move_to_end(key)
            return self.memo[key], True
        for witness in self.witnesses.get(selected, ()):
            if all((r, c) not in restrictions or arc in restrictions[(r, c)]
                   for r, c, arc in witness):
                return ClueAnalysis(accepted_states=[witness]), True
        result = check_secondary_clue(self.state, assigned, selected, self.stop_event,
                                      self.worklist_limit, simplify_nonclue=True,
                                      prioritize_frontier=self.prioritize_frontier)
        if not result.cancelled:
            self.memo[key] = result
            if len(self.memo) > 4096:
                self.memo.popitem(last=False)
            if result.accepted_states:
                witnesses = self.witnesses.setdefault(selected, [])
                witnesses.append(result.accepted_states[0])
                if len(witnesses) > 256:
                    del witnesses[0]
        return result, False


def check_secondary_clue(state, assigned, selected, stop_event=None, worklist_limit=25,
                         simplify_nonclue=True, prioritize_frontier=True):
    """Check another clue under branch-local decisions without changing the grid.

    One acceptance is enough to establish local feasibility. Zero acceptances
    mean contradiction only on exhaustion; a worklist cutoff is inconclusive.
    Nested checks do not recursively launch more checks or apply deductions.
    """
    context = {**state, "cells": [list(row) for row in state["cells"]],
               "arc_domains": [[list(allowed_arc_configurations(state, r, c))
                                for c in range(state["columns"])] for r in range(state["rows"])]}
    for (r, c), orientation in assigned.items():
        if isinstance(orientation, SimplifiedArc):
            context['arc_domains'][r][c] = list(orientation.options)
        else:
            context["cells"][r][c] = {**state["cells"][r][c], "arc": orientation}
            context["arc_domains"][r][c] = [orientation]
    return analyze_clue_incremental(context, selected, accepted_limit=0,
                                    stop_event=stop_event, check_other_clues=False,
                                    worklist_limit=worklist_limit,
                                    simplify_nonclue=simplify_nonclue,
                                    prioritize_frontier=prioritize_frontier)
