"""Sound conditional exclusions from bounded local region searches."""
from collections import deque, OrderedDict
import copy

from arc_constraints import propagate_arc_domains
from clue_analysis import STEPS, fragment_for_edge
from puzzle_gui import ARC_CYCLE, Region


def local_conflict(state, source, domains, max_distance=3):
    """Only follow singleton decisions; unknown configurations end a path.

    Distance is a spatial Manhattan radius from the source clue.
    A truncated path cannot prove anything; a forced conflicting clue or
    reconnection of both sides of an arc is a contradiction at any depth.
    """
    if len(domains[source]) != 1:
        return False
    target = state['cells'][source[0]][source[1]]['number']
    queue = deque([(*source, 0)])
    seen = set()
    while queue:
        r, c, side = queue.popleft()
        fragment = (r, c, side)
        if fragment in seen:
            continue
        arc = domains[(r, c)][0]
        if arc is not None and (r, c, 1 - side) in seen:
            return True
        if side == 0 and state['cells'][r][c]['number'] not in (None, target):
            return True
        seen.add(fragment)
        for edge, dr, dc, opposite in STEPS:
            if fragment_for_edge(arc, edge) != side:
                continue
            cell = (r + dr, c + dc)
            if (cell not in domains or len(domains[cell]) != 1 or
                abs(cell[0] - source[0]) + abs(cell[1] - source[1]) > max_distance):
                continue
            queue.append((*cell, fragment_for_edge(domains[cell][0], opposite)))
    return False


class _LocalCutoff(Exception):
    pass


class LocalLookahead:
    """Bounded local CSP. False is a proof; None is an inconclusive cutoff."""
    def __init__(self, state, source, radius=3, max_decisions=4, node_limit=64, budget=None):
        self.state, self.source = state, source
        self.cells = {cell for cell in propagate_arc_domains(state)
                      if abs(cell[0] - source[0]) + abs(cell[1] - source[1]) <= radius}
        self.clues = [cell for cell in self.cells if state['cells'][cell[0]][cell[1]]['number'] is not None]
        self.max_decisions, self.node_limit = max_decisions, node_limit
        self.budget = budget if budget is not None else [20000]
        self.memo = OrderedDict()
        self.visited = 0
        self.inspections = 0

    def inspect(self, domains):
        if self.budget[0] <= 0 or self.inspections >= self.node_limit * 4:
            raise _LocalCutoff()
        self.inspections += 1
        self.budget[0] -= 1
        frontier = {}
        for clue in self.clues:
            if len(domains[clue]) != 1:
                frontier.setdefault(clue, set())
                continue
            target = self.state['cells'][clue[0]][clue[1]]['number']
            queue, seen, escaped, pending = deque([(*clue, 0)]), set(), False, False
            while queue:
                r, c, side = queue.popleft()
                if (r, c, side) in seen:
                    continue
                arc = domains[(r, c)][0]
                if (arc is not None and (r, c, 1 - side) in seen or
                    side == 0 and self.state['cells'][r][c]['number'] not in (None, target)):
                    return None
                seen.add((r, c, side))
                for edge, dr, dc, opposite in STEPS:
                    if fragment_for_edge(arc, edge) != side:
                        continue
                    cell = (r + dr, c + dc)
                    if cell not in domains:
                        continue
                    if cell not in self.cells:
                        escaped = True
                    elif len(domains[cell]) != 1:
                        frontier.setdefault(cell, set()).add(opposite)
                        pending = True
                    else:
                        queue.append((*cell, fragment_for_edge(domains[cell][0], opposite)))
            if not escaped and not pending:
                candidate = {**self.state, 'cells': [list(row) for row in self.state['cells']]}
                for r, c, _ in seen:
                    candidate['cells'][r][c] = {**self.state['cells'][r][c], 'arc': domains[(r, c)][0]}
                if Region.from_fragments(0, seen, candidate).determine_score(candidate) != target:
                    return None
        return frontier

    def feasible(self, domains):
        self.visited = 0
        self.inspections = 0
        try:
            return self._search(domains, 0)
        except _LocalCutoff:
            return None

    def _search(self, domains, depth):
        if self.visited >= self.node_limit or self.budget[0] <= 0:
            return None
        self.visited += 1
        key = tuple((cell, values) for cell, values in domains.items())
        if key in self.memo:
            self.memo.move_to_end(key)
            return self.memo[key]
        frontier = self.inspect(domains)
        if frontier is None:
            answer = False
        elif not frontier:
            answer = True
        elif depth >= self.max_decisions:
            return None
        else:
            choices = {}
            children = {}
            for cell in frontier:
                choices[cell] = []
                for arc in domains[cell]:
                    child = propagate_arc_domains(self.state, {cell: arc}, domains)
                    if child is not None and self.inspect(child) is not None:
                        choices[cell].append(arc)
                        children[(cell, arc)] = child
                if not choices[cell]:
                    self.memo[key] = False
                    return False
            cell = min(frontier, key=lambda cell: (len(choices[cell]), -len(frontier[cell]),
                       abs(cell[0] - self.source[0]) + abs(cell[1] - self.source[1]), cell))
            answer = False
            for arc in choices[cell]:
                child_answer = self._search(children[(cell, arc)], depth + 1)
                if child_answer is not False:
                    return child_answer  # One possible or unknown continuation prevents exclusion.
        self.memo[key] = answer
        if len(self.memo) > 2048:
            self.memo.popitem(last=False)
        return answer


def scan_local_conditionals(state, max_distance=3, max_decisions=4, node_limit=64, total_node_limit=20000):
    """Return a new state and scan counts; never change the input state."""
    if max_distance < 1:
        raise ValueError('Scan distance must be positive.')
    if max_decisions < 0 or node_limit < 1 or total_node_limit < 0:
        raise ValueError('Search depth and total budget must be nonnegative; node limit must be positive.')
    work = copy.deepcopy(state)
    base = propagate_arc_domains(work)
    if base is None:
        raise ValueError('The current arc deductions are contradictory.')
    rules = {(tuple(rule['if']), tuple(rule['then'][:2])): set(rule['then'][2])
             for rule in work.get('arc_implications', [])}
    counts = {'clues': 0, 'pairs': 0, 'implications': 0, 'removed': 0, 'lookahead_nodes': 0, 'cutoffs': 0}
    budget = [total_node_limit]
    rejected = set()
    probes = []
    # Give every source hypothesis its direct lookahead before spending the
    # remaining shared budget on the much larger set of conditional pairs.
    for source, source_domain in base.items():
        if work['cells'][source[0]][source[1]]['number'] is None:
            continue
        counts['clues'] += 1
        lookahead = LocalLookahead(work, source, max_distance, max_decisions, node_limit, budget)
        nearby = [cell for cell in base if cell != source
                  and abs(cell[0] - source[0]) + abs(cell[1] - source[1]) <= max_distance
                  and len(base[cell]) > 1]
        probes.append((source, source_domain, nearby, lookahead))
        for trigger in source_domain:
            fixed = {source: trigger}
            source_domains = propagate_arc_domains(work, fixed, base)
            if source_domains is None or local_conflict(work, source, source_domains, max_distance):
                rejected.add((source, trigger))
                continue
            feasible = lookahead.feasible(source_domains)
            if feasible is False:
                rejected.add((source, trigger))
                continue
            counts['cutoffs'] += feasible is None
    for source, source_domain, nearby, lookahead in probes:
        for trigger in source_domain:
            if (source, trigger) in rejected:
                continue
            fixed = {source: trigger}
            for cell in nearby:
                allowed = set()
                for arc in base[cell]:
                    counts['pairs'] += 1
                    domains = propagate_arc_domains(work, fixed | {cell: arc}, base)
                    if domains is not None and not local_conflict(work, source, domains, max_distance):
                        feasible = lookahead.feasible(domains)
                        counts['cutoffs'] += feasible is None
                        if feasible is not False:
                            allowed.add(arc)
                if not allowed:
                    rejected.add((source, trigger))
                    break
                if allowed == set(base[cell]):
                    continue
                key = ((*source, trigger), cell)
                previous = rules.get(key)
                narrowed = allowed if previous is None else previous & allowed
                if not narrowed:
                    rejected.add((source, trigger))
                    break
                if narrowed != previous:
                    rules[key] = narrowed
                    counts['implications'] += 1
    domains = {cell: tuple(arc for arc in values if (cell, arc) not in rejected)
               for cell, values in base.items()}
    if any(not values for values in domains.values()):
        raise ValueError('The local scan found a contradiction with the current markings.')
    if rules:
        work['arc_implications'] = [{'if': list(source), 'then': [*cell, [arc for arc in ARC_CYCLE if arc in allowed]]}
                                     for (source, cell), allowed in rules.items()
                                     if ((source[0], source[1]), source[2]) not in rejected]
    propagated = propagate_arc_domains(work, domains=domains)
    if propagated is None:
        raise ValueError('The local scan found incompatible conditional deductions.')
    counts['removed'] = sum(len(base[cell]) - len(values) for cell, values in propagated.items())
    counts['lookahead_nodes'] = total_node_limit - budget[0]
    work['arc_domains'] = [[list(propagated[(r, c)]) for c in range(work['columns'])]
                           for r in range(work['rows'])]
    return work, counts
