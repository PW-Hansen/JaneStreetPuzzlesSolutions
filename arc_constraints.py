"""Persistent conditional arc deductions and branch-local propagation."""
from puzzle_gui import ARC_CYCLE, allowed_arc_configurations
from collections import deque
from functools import lru_cache

_BITS = {arc: 1 << index for index, arc in enumerate(ARC_CYCLE)}
_VALUES = {mask: tuple(arc for arc in ARC_CYCLE if mask & _BITS[arc]) for mask in range(32)}
_MASKS = {values: mask for mask, values in _VALUES.items()}


def _mask(values):
    values = tuple(values)
    known = _MASKS.get(values)
    return known if known is not None else sum(_BITS[arc] for arc in set(values))


def make_arc_domain_propagator(state):
    """Compile a search's immutable rule snapshot once, rather than per branch."""
    signature = tuple((*rule['if'], *rule['then'][:2], tuple(rule['then'][2]))
                      for rule in state.get('arc_implications', []))
    compiled = _compile_rules(signature)
    def propagate(snapshot, assigned=None, domains=None):
        return propagate_arc_domains(snapshot, assigned, domains, _compiled=compiled)
    return propagate


@lru_cache(maxsize=32)
def _compile_rules(signature):
    rules, watchers = [], {}
    for r, c, trigger, nr, nc, allowed in signature:
        source, target = (r, c), (nr, nc)
        index = len(rules)
        rules.append((source, _BITS[trigger], target, sum(_BITS[arc] for arc in allowed)))
        for cell in {source, target}:
            watchers.setdefault(cell, []).append(index)
    return rules, watchers


def propagate_arc_domains(state, assigned=None, domains=None, _compiled=None):
    domains = ({(r, c): allowed_arc_configurations(state, r, c)
                for r in range(state['rows']) for c in range(state['columns'])}
               if domains is None else domains)
    domains = {cell: _mask(values) for cell, values in domains.items()}
    for cell, value in (assigned or {}).items():
        domains[cell] &= _mask(value.options if hasattr(value, 'options') else (value,))
    if any(not mask for mask in domains.values()):
        return None
    if _compiled is None:
        signature = tuple((*rule['if'], *rule['then'][:2], tuple(rule['then'][2]))
                          for rule in state.get('arc_implications', []))
        _compiled = _compile_rules(signature)
    rules, watchers = _compiled
    queue, pending = deque(range(len(rules))), set(range(len(rules)))
    while queue:
        index = queue.popleft()
        pending.remove(index)
        source, trigger, target, allowed = rules[index]
        updates = []
        if domains[source] & trigger and not domains[target] & allowed:
            updates.append((source, domains[source] & ~trigger))
        elif domains[source] == trigger:
            updates.append((target, domains[target] & allowed))
        for cell, narrowed in updates:
            if not narrowed:
                return None
            if narrowed == domains[cell]:
                continue
            domains[cell] = narrowed
            for affected in watchers[cell]:
                if affected not in pending:
                    pending.add(affected)
                    queue.append(affected)
    return {cell: _VALUES[mask] for cell, mask in domains.items()}


def learn_arc_implications(state, assignments, mandatory):
    rules = {(tuple(rule['if']), tuple(rule['then'][:2])): set(rule['then'][2])
             for rule in state.get('arc_implications', [])}
    added = 0
    for source in sorted(mandatory):
        triggers = {values[source] for values in assignments}
        if len(triggers) < 2:
            continue
        for trigger in ARC_CYCLE:
            subset = [values for values in assignments if values[source] == trigger]
            if not subset:
                continue
            for target in sorted(mandatory - {source}):
                supported = {values[target] for values in subset}
                unconditional = {values[target] for values in assignments}
                if supported == unconditional:
                    continue
                key = ((*source, trigger), target)
                previous = rules.get(key)
                narrowed = supported if previous is None else previous & supported
                if not narrowed:
                    raise ValueError('Analysis contradicts a recorded conditional deduction.')
                if previous != narrowed:
                    rules[key] = narrowed
                    added += 1
    if rules:
        state['arc_implications'] = [{'if': list(source), 'then': [*target, [arc for arc in ARC_CYCLE if arc in allowed]]}
                                     for (source, target), allowed in rules.items()]
    return added
