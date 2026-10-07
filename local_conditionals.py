"""Sound conditional exclusions from short forced region connections."""
from collections import deque
import copy

from arc_constraints import propagate_arc_domains
from clue_analysis import STEPS, fragment_for_edge
from puzzle_gui import ARC_CYCLE


def local_conflict(state, source, domains, max_distance=3):
    """Only follow singleton decisions; unknown configurations end a path.

    Distance counts orthogonal cell-edge crossings from the source clue.
    A truncated path cannot prove anything; a forced conflicting clue or
    reconnection of both sides of an arc is a contradiction at any depth.
    """
    if len(domains[source]) != 1:
        return False
    target = state['cells'][source[0]][source[1]]['number']
    queue = deque([(*source, 0, 0)])
    seen = set()
    while queue:
        r, c, side, distance = queue.popleft()
        fragment = (r, c, side)
        if fragment in seen:
            continue
        arc = domains[(r, c)][0]
        if arc is not None and (r, c, 1 - side) in seen:
            return True
        if side == 0 and state['cells'][r][c]['number'] not in (None, target):
            return True
        seen.add(fragment)
        if distance == max_distance:
            continue
        for edge, dr, dc, opposite in STEPS:
            if fragment_for_edge(arc, edge) != side:
                continue
            cell = (r + dr, c + dc)
            if cell not in domains or len(domains[cell]) != 1:
                continue
            queue.append((*cell, fragment_for_edge(domains[cell][0], opposite), distance + 1))
    return False


def scan_local_conditionals(state, max_distance=3):
    """Return a new state and scan counts; never change the input state."""
    if max_distance < 1:
        raise ValueError('Scan distance must be positive.')
    work = copy.deepcopy(state)
    base = propagate_arc_domains(work)
    if base is None:
        raise ValueError('The current arc deductions are contradictory.')
    rules = {(tuple(rule['if']), tuple(rule['then'][:2])): set(rule['then'][2])
             for rule in work.get('arc_implications', [])}
    counts = {'clues': 0, 'pairs': 0, 'implications': 0, 'removed': 0}
    rejected = set()
    for source, source_domain in base.items():
        if work['cells'][source[0]][source[1]]['number'] is None:
            continue
        counts['clues'] += 1
        nearby = [cell for cell in base if cell != source
                  and abs(cell[0] - source[0]) + abs(cell[1] - source[1]) <= max_distance
                  and len(base[cell]) > 1]
        for trigger in source_domain:
            fixed = {source: trigger}
            source_domains = propagate_arc_domains(work, fixed, base)
            if source_domains is None or local_conflict(work, source, source_domains, max_distance):
                rejected.add((source, trigger))
                continue
            for cell in nearby:
                allowed = set()
                for arc in base[cell]:
                    counts['pairs'] += 1
                    domains = propagate_arc_domains(work, fixed | {cell: arc}, base)
                    if domains is not None and not local_conflict(work, source, domains, max_distance):
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
    work['arc_domains'] = [[list(propagated[(r, c)]) for c in range(work['columns'])]
                           for r in range(work['rows'])]
    return work, counts
