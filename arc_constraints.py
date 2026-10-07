"""Persistent conditional arc deductions and branch-local propagation."""
from puzzle_gui import ARC_CYCLE, allowed_arc_configurations


def propagate_arc_domains(state, assigned=None, domains=None):
    domains = ({(r, c): set(allowed_arc_configurations(state, r, c))
                for r in range(state['rows']) for c in range(state['columns'])}
               if domains is None else {cell: set(values) for cell, values in domains.items()})
    for cell, value in (assigned or {}).items():
        domains[cell].intersection_update(value.options if hasattr(value, 'options') else (value,))
    changed = True
    while changed:
        if any(not values for values in domains.values()):
            return None
        changed = False
        for rule in state.get('arc_implications', []):
            r, c, trigger = rule['if']
            nr, nc, allowed = rule['then']
            source, target = domains[(r, c)], domains[(nr, nc)]
            if trigger in source and not target.intersection(allowed):
                source.remove(trigger)
                changed = True
            if source == {trigger}:
                narrowed = target.intersection(allowed)
                if narrowed != target:
                    domains[(nr, nc)] = narrowed
                    changed = True
    return {cell: tuple(arc for arc in ARC_CYCLE if arc in values) for cell, values in domains.items()}


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
