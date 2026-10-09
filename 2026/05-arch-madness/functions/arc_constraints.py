"""Persistent conditional arc deductions and branch-local propagation."""
from functions.constants import ARC_CYCLE
from functions.puzzle_model import allowed_arc_configurations
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
    def restrict(domains):
        """Discard rules permanently satisfied within this search's root domains."""
        nonlocal compiled
        rules, _ = compiled
        active, watchers = [], {}
        for source, triggers, target, allowed in rules:
            triggers &= _mask(domains[source])
            if not triggers or not _mask(domains[target]) & ~allowed:
                continue
            index = len(active)
            active.append((source, triggers, target, allowed))
            for cell in {source, target}:
                watchers.setdefault(cell, []).append(index)
        compiled = active, watchers
    def extend(domains, cell, value):
        """Extend an already propagated parent without rescanning unrelated rules."""
        rules, watchers = compiled
        narrowed = _mask(domains[cell]) & _mask(value.options if hasattr(value, 'options') else (value,))
        if not narrowed:
            return None, ()
        if _VALUES[narrowed] == domains[cell]:
            return domains, ()
        result = dict(domains)
        result[cell] = _VALUES[narrowed]
        changed = {cell}
        queue = deque(watchers.get(cell, ()))
        pending = set(queue)
        while queue:
            index = queue.popleft()
            pending.remove(index)
            source, trigger, target, allowed = rules[index]
            source_mask, target_mask = _mask(result[source]), _mask(result[target])
            if source_mask & trigger and not target_mask & allowed:
                affected, narrowed = source, source_mask & ~trigger
            elif not source_mask & ~trigger:
                affected, narrowed = target, target_mask & allowed
            else:
                continue
            if not narrowed:
                return None, ()
            values = _VALUES[narrowed]
            if values == result[affected]:
                continue
            result[affected] = values
            changed.add(affected)
            for next_rule in watchers[affected]:
                if next_rule not in pending:
                    pending.add(next_rule)
                    queue.append(next_rule)
        return result, changed
    propagate.extend = extend
    propagate.restrict = restrict
    return propagate


@lru_cache(maxsize=32)
def _compile_rules(signature):
    rules, watchers = [], {}
    grouped = {}
    for r, c, trigger, nr, nc, allowed in signature:
        source, target = (r, c), (nr, nc)
        key = (source, target, sum(_BITS[arc] for arc in allowed))
        grouped[key] = grouped.get(key, 0) | _BITS[trigger]
    for (source, target, allowed), triggers in grouped.items():
        index = len(rules)
        rules.append((source, triggers, target, allowed))
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
        elif not domains[source] & ~trigger:
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


def learn_arc_implications(state, assignments, mandatory, source_clue=None):
    rules = {(tuple(rule['if']), tuple(rule['then'][:2])): set(rule['then'][2])
             for rule in state.get('arc_implications', [])}
    original = {key: set(values) for key, values in rules.items()}
    added = 0
    touched = set().union(*(set(values) for values in assignments))
    baseline = {cell: set(allowed_arc_configurations(state, *cell)) for cell in touched}
    context_propagate = make_arc_domain_propagator(state)
    context_domains = context_propagate(state)
    for source in sorted(touched):
        for trigger in ARC_CYCLE:
            if trigger not in baseline[source]:
                continue
            # A cell outside a local region is unenumerated, not empty. Such
            # a state remains possible under every allowed source orientation.
            subset = [values for values in assignments
                      if (source not in values or values[source] == trigger)
                      and context_propagate(state, values | {source: trigger}, context_domains) is not None]
            if not subset:
                continue
            for target in sorted(touched - {source}):
                if any(target not in values for values in subset):
                    continue
                supported = {values[target] for values in subset}
                unconditional = (baseline[target] if any(target not in values for values in assignments)
                                 else {values[target] for values in assignments})
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
    def serialize(mapping):
        return [{'if': list(source), 'then': [*target, [arc for arc in ARC_CYCLE if arc in allowed]]}
                for (source, target), allowed in mapping.items()]
    if source_clue is not None:
        # Route deductions through the analyzed clue first. Keep a direct
        # relationship only when the hub cannot express it (e.g. two states
        # use the same clue arc but differ elsewhere).
        retained, candidates = {}, {}
        for key, allowed in rules.items():
            source, target = key
            if (tuple(source[:2]) == source_clue or target == source_clue or
                    tuple(source[:2]) not in touched or target not in touched):
                retained[key] = allowed
            else:
                candidates[key] = allowed
        probe = {**state, 'arc_implications': serialize(retained)}
        propagate = make_arc_domain_propagator(probe)
        base = propagate(probe)
        for key, allowed in candidates.items():
            source, target = key
            inferred = propagate(probe, {tuple(source[:2]): source[2]}, base) if base is not None else None
            if inferred is None or set(inferred[target]) <= allowed:
                continue
            retained[key] = allowed
            probe['arc_implications'] = serialize(retained)
            propagate = make_arc_domain_propagator(probe)
            base = propagate(probe)
        rules = retained
    if rules:
        state['arc_implications'] = serialize(rules)
    else:
        state.pop('arc_implications', None)
    return sum(original.get(key) != allowed for key, allowed in rules.items())


def apply_arc_deductions(state):
    """Materialize the propagated master domains and their forced arc marks."""
    domains = propagate_arc_domains(state)
    if domains is None:
        raise ValueError('This edit conflicts with a recorded conditional deduction.')
    state['arc_domains'] = [[list(domains[(r, c)]) for c in range(state['columns'])]
                           for r in range(state['rows'])]
    forced = 0
    for (r, c), values in domains.items():
        if len(values) == 1 and state['cells'][r][c]['arc'] != values[0]:
            state['cells'][r][c]['arc'] = values[0]
            forced += 1
    return forced


def describe_arc_implications(state, selected):
    names = {None: 'no arc', 'tl': 'top-left', 'tr': 'top-right',
             'br': 'bottom-right', 'bl': 'bottom-left'}
    grouped = {}
    for rule in state.get('arc_implications', []):
        r, c, trigger = rule['if']
        nr, nc, allowed = rule['then']
        if selected in ((r, c), (nr, nc)):
            grouped.setdefault((r, c, nr, nc, tuple(allowed)), set()).add(trigger)
    descriptions = []
    for (r, c, nr, nc, allowed), triggers in grouped.items():
        excluded = set(ARC_CYCLE) - triggers
        if len(excluded) == 1:
            condition = 'anything other than ' + names[next(iter(excluded))]
        else:
            condition = ' or '.join(names[arc] for arc in ARC_CYCLE if arc in triggers)
        descriptions.append(f'If r{r + 1}c{c + 1} is {condition}, r{nr + 1}c{nc + 1} must be '
                            + ' or '.join(names[value] for value in allowed))
    return '\n'.join(descriptions)
