"""Clue search under the heuristic of one even, continuous boundary contact."""
from itertools import product
from time import perf_counter

from functions.puzzle_model import arc_endpoints
from functions.incremental_analysis import (SimplifiedArc, edge_side,
    analyze_clue_incremental, sanity_check_accepted_states)


class GreedyBoundary:
    def __init__(self, state):
        self.state = state
        rows, cols = state['rows'], state['columns']
        # Clockwise unit edges, with corners joining rather than interrupting.
        self.edges = ([(0, c, 'N', (0, c)) for c in range(cols)]
                    + [(r, cols - 1, 'E', (r, cols)) for r in range(rows)]
                    + [(rows - 1, c, 'S', (rows, c + 1)) for c in reversed(range(cols))]
                    + [(r, 0, 'W', (r + 1, 0)) for r in reversed(range(rows))])
        self.cell_edges = {}
        for index, (r, c, edge, _) in enumerate(self.edges):
            self.cell_edges.setdefault((r, c), []).append((index, edge))

    def contacts(self, assigned, fragments):
        contacts = set()
        for r, c, side in fragments:
            for index, edge in self.cell_edges.get((r, c), ()):
                if edge_side(assigned[(r, c)], edge) == side:
                    contacts.add(index)
        return frozenset(contacts)

    def endpoint_choices(self, vertex_index, interval, assigned, domains, simplify):
        """Either adjacent edge cell may own the terminating arc."""
        size = len(self.edges)
        vertex = self.edges[vertex_index][3]
        owners = {self.edges[index][:2] for index in ((vertex_index - 1) % size, vertex_index)}
        choices = []
        for cell in sorted(owners):
            groups = {}
            old = assigned.get(cell)
            old_options = old.options if isinstance(old, SimplifiedArc) else (old,)
            for arc in domains[cell]:
                if arc is None or cell in assigned and arc not in old_options:
                    continue
                if vertex not in {point for point, _ in arc_endpoints(*cell, arc)}:
                    continue
                for side in (0, 1):
                    if not all((edge_side(arc, edge) == side) == (index in interval)
                               for index, edge in self.cell_edges[cell]):
                        continue
                    exposed = ''.join(edge for edge in 'NESW' if edge_side(arc, edge) == side)
                    groups.setdefault(exposed, []).append(arc)
            for exposed, options in groups.items():
                options = tuple(dict.fromkeys(options))
                if simplify and self.state['cells'][cell[0]][cell[1]]['number'] is None:
                    choices.append((cell, SimplifiedArc(exposed, options)))
                else:
                    choices.extend((cell, arc) for arc in options)
        return choices

    def plans(self, assigned, fragments, domains, simplify):
        current = self.contacts(assigned, fragments)
        if not current:
            return None
        size = len(self.edges)
        plans, seen = [], set()
        minimum = max(2, len(current) + len(current) % 2)
        for length in range(size, minimum - 1, -2):
            starts = range(1) if length == size else range(size)
            for start in starts:
                interval = frozenset((start + offset) % size for offset in range(length))
                if not current <= interval:
                    continue
                claimed = {self.edges[index][:2] for index in interval}
                if length == size:
                    endings = [((), ())]
                else:
                    first = self.endpoint_choices(start, interval, assigned, domains, simplify)
                    last = self.endpoint_choices((start + length) % size, interval, assigned, domains, simplify)
                    endings = product(first, last)
                for first, last in endings:
                    updates = {}
                    if first:
                        updates[first[0]] = first[1]
                        if last[0] in updates and updates[last[0]] != last[1]:
                            continue
                        updates[last[0]] = last[1]
                    valid = True
                    for cell in claimed:
                        if cell in updates:
                            continue
                        if cell in assigned:
                            if assigned[cell] is not None:
                                valid = False
                                break
                        elif None not in domains[cell]:
                            valid = False
                            break
                        updates[cell] = None
                    if not valid:
                        continue
                    signature = (interval, frozenset(updates.items()))
                    if signature not in seen:
                        seen.add(signature)
                        plans.append((updates, interval))
        return plans


def analyze_clue_greedy(state, selected, *, timer=perf_counter, started_at=None,
                        sanity_progress=None, **options):
    started = timer() if started_at is None else started_at
    result = analyze_clue_incremental(state, selected, boundary_policy=GreedyBoundary(state), **options)
    main_finished = timer()
    result.main_search_seconds = main_finished - started
    sanity_check_accepted_states(state, result, selected,
        stop_event=options.get('stop_event'),
        simplify_nonclue=options.get('simplify_nonclue', True),
        prioritize_frontier=options.get('prioritize_frontier', True), progress=sanity_progress)
    finished = timer()
    result.sanity_check_seconds = finished - main_finished
    result.elapsed_seconds = finished - started
    result.heuristic = True
    return result
