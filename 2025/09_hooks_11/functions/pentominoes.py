"""Clue-directed pentomino placements and joint compatibility search."""
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
import math

from .constants import (PENTOMINO_SHAPES, PENTOMINO_NODE_LIMIT,
                        PENTOMINO_CANDIDATE_LIMIT, PENTOMINO_PLACEMENT_LIMIT,
                        PENTOMINO_SUM_MODULUS, PENTOMINO_CELL_COUNT,
                        REMAINING_PENTOMINO_COUNT, EXCLUDED_PENTOMINOES)
from .hooks import (small_hook_digits_allowed, outside_two_rays, three_cell_hook_visible,
                    available_five_cell_digits, outside_digit_rays, five_cell_digits_from_clues)
from .constants import HOOK_ALLOWED_DIGITS


def orientations(shape):
    variants = set()
    for reflection in (1, -1):
        cells = [(r, c*reflection) for r, c in shape]
        for _ in range(4):
            top, left = min(r for r, c in cells), min(c for r, c in cells)
            variants.add(tuple(sorted((r-top, c-left) for r, c in cells)))
            cells = [(c, -r) for r, c in cells]
    return tuple(sorted(variants))


def hook_digest(data):
    analysis = data.get('analysis')
    payload = None if analysis is None else (analysis['candidates'], analysis['outcome'])
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def preview_record(data):
    analysis = data.get('pentomino_analysis')
    if analysis is None or analysis['preview'] < 0:
        return None
    records = analysis_records(analysis)
    return records[analysis['preview']]


def analysis_records(analysis, view=None):
    field_name = {'combinations':'candidates', 'placements':'placements', 'extensions':'extensions'}[view or analysis['view']]
    return analysis.get(field_name, [])


def translated_placements(name, rows, cols):
    if name in EXCLUDED_PENTOMINOES:
        return
    for variant in orientations(PENTOMINO_SHAPES[name]):
        height = max(r for r,c in variant)+1
        width = max(c for r,c in variant)+1
        for row in range(rows-height+1):
            for col in range(cols-width+1):
                yield frozenset((row+r,col+c) for r,c in variant)


def clue_rays(data):
    """Group all sightlines for each required shape, nearest cell first."""
    rows, cols = data['rows'], data['cols']
    clues = {}
    for key, value in data['entries'].items():
        r, c = map(int, key.split(','))
        if 0 <= r < rows and 0 <= c < cols:
            continue
        if value.isdecimal():
            continue
        name = value.upper()
        if name not in PENTOMINO_SHAPES:
            raise ValueError(f'Unknown outside pentomino clue: {value}.')
        if r == -1:
            ray = [(row, c) for row in range(rows)]
        elif r == rows:
            ray = [(row, c) for row in reversed(range(rows))]
        elif c == -1:
            ray = [(r, col) for col in range(cols)]
        else:
            ray = [(r, col) for col in reversed(range(cols))]
        clues.setdefault(name, []).append(tuple(ray))
    return clues


def hook_regions(borders, rows, cols):
    remaining = {(r, c) for r in range(rows) for c in range(cols)}
    groups = []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        group, pending = {start}, [start]
        while pending:
            r, c = pending.pop()
            for nr, nc, edge in ((r-1,c,f'h,{r},{c}'), (r+1,c,f'h,{r+1},{c}'),
                                 (r,c-1,f'v,{r},{c}'), (r,c+1,f'v,{r},{c+1}')):
                if (nr, nc) in remaining and edge not in borders:
                    remaining.remove((nr, nc))
                    group.add((nr, nc))
                    pending.append((nr, nc))
        groups.append(frozenset(group))
    return tuple(sorted(groups, key=lambda cells: (len(cells), min(cells))))


def has_filled_square(filled):
    return any({(r+1,c), (r,c+1), (r+1,c+1)} <= filled for r,c in filled)


def filled_region_connected(filled):
    if not filled:
        return True
    remaining = set(filled)
    pending = [remaining.pop()]
    while pending:
        r,c = pending.pop()
        for cell in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)):
            if cell in remaining:
                remaining.remove(cell)
                pending.append(cell)
    return not remaining


@dataclass(frozen=True)
class Placement:
    name: str
    cells: frozenset
    empty: frozenset


def visible_placement(name, cells, clues, filled):
    """Require every clue for this shape to see it before any filled cell."""
    empty = set()
    for ray in clues[name]:
        for cell in ray:
            if cell in cells:
                break
            empty.add(cell)
        else:
            return None
    if empty & filled:
        return None
    return Placement(name, frozenset(cells), frozenset(empty))


@dataclass
class HookContext:
    data: dict
    borders: dict

    def __post_init__(self):
        self.rows, self.cols = self.data['rows'], self.data['cols']
        self.hooks = hook_regions(self.borders, self.rows, self.cols)
        if self.rows != self.cols or sorted(map(len, self.hooks)) != list(range(1, 2*self.rows, 2)):
            raise ValueError('Stored hook layout is not a complete partition into nested hooks. Redraw hooks first.')
        self.owner = {cell: index for index, hook in enumerate(self.hooks) for cell in hook}
        self.digits = {}
        for key, value in self.data['entries'].items():
            r, c = map(int, key.split(','))
            if 0 <= r < self.rows and 0 <= c < self.cols and value.isdecimal():
                self.digits[r,c] = int(value)
        self.filled = frozenset(self.digits)
        self.two_rays = outside_two_rays(self.data)
        self.five_rays = {digit: outside_digit_rays(self.data, {digit}) for digit in HOOK_ALLOWED_DIGITS[5]}
        anchor = next(iter(self.hooks[0]))
        self.domains = []
        for hook in self.hooks:
            known = {self.digits[cell] for cell in hook if cell in self.digits}
            possible = known if known else set(range(1, len(self.hooks)+1))
            if len(known) > 1:
                possible = set()
            if len(hook) == 5:
                possible = possible & available_five_cell_digits(hook, anchor, self.digits)
            self.domains.append(frozenset(digit for digit in possible
                if 1 <= digit <= len(self.hooks) and digit <= len(hook)
                and small_hook_digits_allowed(hook, {digit}, anchor)))

    def constraints(self, pieces):
        occupied, empty = set(self.filled), set()
        assigned_cells = set()
        coefficients = []
        for piece in pieces:
            if assigned_cells & piece.cells:
                return None
            assigned_cells.update(piece.cells)
            occupied.update(piece.cells)
            empty.update(piece.empty)
            counts = Counter(self.owner[cell] for cell in piece.cells)
            coefficients.append(counts)
        if occupied & empty or has_filled_square(occupied):
            return None
        if self.two_rays and (len(self.hooks) < 2 or not three_cell_hook_visible(self.hooks[1], self.two_rays, occupied)):
            return None
        # Counts use a union: a given already covered by a piece counts once.
        counts = Counter(self.owner[cell] for cell in occupied)
        domains = [set(digit for digit in possible if counts[index] <= digit <= len(hook-empty))
                   for index, (hook, possible) in enumerate(zip(self.hooks, self.domains))]
        if len(self.hooks) >= 3:
            domains[2] = five_cell_digits_from_clues(domains[2], self.hooks[2], self.hooks[1], self.five_rays, occupied)
        if any(not possible for possible in domains):
            return None
        return domains, coefficients


class SearchStopped(Exception):
    pass


@dataclass
class PentominoSearch:
    data: dict
    node_limit: int = PENTOMINO_NODE_LIMIT
    candidate_limit: int = PENTOMINO_CANDIDATE_LIMIT
    placement_limit: int = PENTOMINO_PLACEMENT_LIMIT
    candidates: list = field(default_factory=list, init=False)
    placements: list = field(default_factory=list, init=False)
    rejected_layouts: set = field(default_factory=set, init=False)
    nodes: int = field(default=0, init=False)
    outcome: str = field(default='running', init=False)
    cancelled: bool = field(default=False, init=False)
    progress: str = field(default='Preparing pentominoes', init=False)

    def __post_init__(self):
        analysis = self.data.get('analysis')
        if not analysis or not analysis['candidates']:
            raise ValueError('Draw hooks first and obtain at least one hook layout.')
        self.layouts = analysis['candidates']
        self.source_incomplete = analysis['outcome'] != 'complete'
        self.clues = clue_rays(self.data)
        if not self.clues:
            raise ValueError('Enter at least one outside pentomino letter clue first.')

    def step(self):
        if self.cancelled:
            self.outcome = 'cancelled'
            raise SearchStopped
        if self.nodes >= self.node_limit:
            self.outcome = 'limit'
            raise SearchStopped
        self.nodes += 1
        yield None

    def witness(self, context, pieces):
        constraints = context.constraints(pieces)
        if constraints is None:
            return None
        domains, coefficients = constraints
        assigned = {}

        def solve(used):
            yield from self.step()
            if len(assigned) == len(domains):
                if any(sum(count*assigned[index] for index,count in counts.items()) % PENTOMINO_SUM_MODULUS for counts in coefficients):
                    return None
                return tuple(assigned[index] for index in range(len(domains)))
            available = {index: values-used for index, values in enumerate(domains) if index not in assigned}
            if any(not values for values in available.values()) or len(set().union(*available.values())) < len(available):
                return None
            # Every piece must have some remaining way to reach a multiple of five.
            for counts in coefficients:
                residues = {sum(count*assigned[index] for index,count in counts.items() if index in assigned) % PENTOMINO_SUM_MODULUS}
                for index,count in counts.items():
                    if index not in assigned:
                        residues = {(total+count*digit) % PENTOMINO_SUM_MODULUS for total in residues for digit in available[index]}
                if 0 not in residues:
                    return None
            index = min(available, key=lambda key: (len(available[key]), key))
            for digit in sorted(available[index]):
                assigned[index] = digit
                result = yield from solve(used | {digit})
                if result is not None:
                    return result
                del assigned[index]
            return None

        return (yield from solve(set()))

    def record(self, context, hook_index, pieces, digits):
        return dict(hook_index=hook_index,
                    pieces=[dict(shape=piece.name, cells=[f'{r},{c}' for r,c in sorted(piece.cells)]) for piece in pieces],
                    entries={f'{r},{c}': str(digits[context.owner[r,c]]) for piece in pieces for r,c in sorted(piece.cells)},
                    hook_digits=list(digits))

    def run(self):
        try:
            for hook_index, borders in enumerate(self.layouts):
                yield from self.step()
                context = HookContext(self.data, borders)
                if (yield from self.witness(context, [])) is None:
                    self.rejected_layouts.add(hook_index)
                    continue
                by_shape = {}
                for name in sorted(self.clues):
                    self.progress = f'Hook layout {hook_index+1}/{len(self.layouts)} · placing {name}'
                    found = []
                    for cells in translated_placements(name, context.rows, context.cols):
                        yield from self.step()
                        piece = visible_placement(name, cells, self.clues, context.filled)
                        if piece is None:
                            continue
                        digits = yield from self.witness(context, [piece])
                        if digits is not None:
                            if len(self.placements) >= self.placement_limit:
                                self.outcome = 'limit'
                                raise SearchStopped
                            found.append(piece)
                            self.placements.append(self.record(context, hook_index, [piece], digits))
                    by_shape[name] = found
                self.progress = f'Hook layout {hook_index+1}/{len(self.layouts)} · testing combinations'
                names = sorted(by_shape, key=lambda name: (len(by_shape[name]), name))

                def combine(index, pieces):
                    yield from self.step()
                    if index == len(names):
                        return
                    for piece in by_shape[names[index]]:
                        selected = pieces + [piece]
                        digits = yield from self.witness(context, selected)
                        if digits is None:
                            continue
                        if index+1 == len(names):
                            if len(self.candidates) >= self.candidate_limit:
                                self.outcome = 'limit'
                                raise SearchStopped
                            self.candidates.append(self.record(context, hook_index, selected, digits))
                        else:
                            yield from combine(index+1, selected)

                candidate_start = len(self.candidates)
                yield from combine(0, [])
                if len(self.candidates) == candidate_start:
                    # Only an exhausted search of this layout proves it impossible.
                    self.rejected_layouts.add(hook_index)
            self.outcome = 'cancelled' if self.cancelled else ('limit' if self.source_incomplete else 'complete')
        except SearchStopped:
            return


@dataclass
class RemainingPentominoSearch(PentominoSearch):
    rejected_combinations: set = field(default_factory=set, init=False)

    def __post_init__(self):
        super().__post_init__()
        analysis = self.data.get('pentomino_analysis')
        if not analysis or not analysis['candidates']:
            raise ValueError('Run Draw pentominoes first and obtain at least one compatible combination.')
        self.bases = analysis['candidates']
        self.source_incomplete = self.source_incomplete or analysis['outcome'] != 'complete'
        self.progress = 'Preparing remaining pentominoes'

    def run(self):
        try:
            for base_index, record in enumerate(self.bases):
                yield from self.step()
                hook_index = record['hook_index']
                context = HookContext(self.data, self.layouts[hook_index])
                fixed = []
                for piece in record['pieces']:
                    cells = frozenset(tuple(map(int,key.split(','))) for key in piece['cells'])
                    placement = visible_placement(piece['shape'], cells, self.clues, context.filled)
                    if placement is None or piece['shape'] in EXCLUDED_PENTOMINOES:
                        break
                    fixed.append(placement)
                used = {piece.name for piece in fixed}
                unused = sorted(set(PENTOMINO_SHAPES) - used - EXCLUDED_PENTOMINOES)
                minimum_filled = (len(fixed)+REMAINING_PENTOMINO_COUNT)*PENTOMINO_CELL_COUNT
                if (len(fixed) != len(record['pieces']) or len(unused) < REMAINING_PENTOMINO_COUNT
                    or minimum_filled > sum(range(1,len(context.hooks)+1))
                    or (yield from self.witness(context, fixed)) is None):
                    self.rejected_combinations.add(base_index)
                    continue
                by_shape = {}
                for name in unused:
                    self.progress = f'Combination {base_index+1}/{len(self.bases)} · placing {name}'
                    found = []
                    for cells in translated_placements(name, context.rows, context.cols):
                        yield from self.step()
                        piece = Placement(name, cells, frozenset())
                        if (yield from self.witness(context, fixed+[piece])) is not None:
                            if len(self.placements) >= self.placement_limit:
                                self.outcome = 'limit'
                                raise SearchStopped
                            found.append(piece)
                            self.placements.append(dict(base_index=base_index, shape=name))
                    if found:
                        by_shape[name] = found
                names = sorted(by_shape)
                candidate_start = len(self.candidates)
                self.progress = f'Combination {base_index+1}/{len(self.bases)} · testing three additional pieces'

                def extend(start, additional):
                    yield from self.step()
                    needed = REMAINING_PENTOMINO_COUNT-len(additional)
                    if len(names)-start < needed:
                        return
                    for index in range(start, len(names)-needed+1):
                        for piece in by_shape[names[index]]:
                            selected = additional+[piece]
                            digits = yield from self.witness(context, fixed+selected)
                            if digits is None:
                                continue
                            if len(selected) == REMAINING_PENTOMINO_COUNT:
                                filled = set(context.filled).union(*(placement.cells for placement in fixed+selected))
                                if len(filled) == sum(digits) and not filled_region_connected(filled):
                                    continue
                                if len(self.candidates) >= self.candidate_limit:
                                    self.outcome = 'limit'
                                    raise SearchStopped
                                candidate = self.record(context, hook_index, fixed+selected, digits)
                                candidate['base_index'] = base_index
                                self.candidates.append(candidate)
                            else:
                                yield from extend(index+1, selected)

                yield from extend(0, [])
                if len(self.candidates) == candidate_start:
                    self.rejected_combinations.add(base_index)
            self.outcome = 'cancelled' if self.cancelled else ('limit' if self.source_incomplete else 'complete')
        except SearchStopped:
            return


def validate_pentomino_analysis(data, analysis):
    """Validate saved preview records before replacing a live puzzle."""
    if not isinstance(analysis, dict) or analysis.get('source_entries') != data['entries'] or analysis.get('source_borders') != data['borders'] or analysis.get('source_hook_digest') != hook_digest(data):
        raise ValueError('Pentomino analysis does not match the current puzzle and hooks.')
    if analysis.get('outcome') not in ('complete', 'cancelled', 'limit'):
        raise ValueError('Invalid pentomino outcome.')
    elapsed = analysis.get('elapsed')
    if not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed < 0 or type(analysis.get('nodes')) is not int or analysis['nodes'] < 0:
        raise ValueError('Invalid pentomino search statistics.')
    view = analysis.get('view')
    if view not in ('combinations', 'placements', 'extensions'):
        raise ValueError('Invalid pentomino view.')
    for field_name in ('candidates', 'placements', *(['extensions'] if 'extensions' in analysis else [])):
        if not isinstance(analysis.get(field_name), list):
            raise ValueError('Invalid pentomino candidates.')
        for record in analysis[field_name]:
            if not isinstance(record, dict):
                raise ValueError('Invalid pentomino placement.')
            if field_name == 'extensions':
                base_index = record.get('base_index')
                if type(base_index) is not int or not 0 <= base_index < len(analysis['candidates']):
                    raise ValueError('Invalid extended combination reference.')
                base = analysis['candidates'][base_index]
                if record.get('hook_index') != base['hook_index'] or len(record.get('pieces', [])) != len(base['pieces'])+REMAINING_PENTOMINO_COUNT or record['pieces'][:len(base['pieces'])] != base['pieces']:
                    raise ValueError('Invalid three-pentomino extension.')
                if any(not isinstance(piece, dict) or piece.get('shape') in EXCLUDED_PENTOMINOES for piece in record['pieces']):
                    raise ValueError('A prohibited pentomino appears in an extension.')
            index = record.get('hook_index')
            if type(index) is not int or not data.get('analysis') or not 0 <= index < len(data['analysis']['candidates']):
                raise ValueError('Invalid pentomino hook layout.')
            if not isinstance(record.get('pieces'), list) or not record['pieces']:
                raise ValueError('Invalid pentomino pieces.')
            occupied, names = set(), set()
            for piece in record['pieces']:
                if not isinstance(piece, dict) or piece.get('shape') not in PENTOMINO_SHAPES or not isinstance(piece.get('cells'), list) or len(piece['cells']) != 5:
                    raise ValueError('Invalid pentomino shape.')
                if piece['shape'] in names:
                    raise ValueError('A pentomino shape is repeated.')
                names.add(piece['shape'])
                cells = set()
                for key in piece['cells']:
                    if not isinstance(key, str):
                        raise ValueError('Invalid pentomino cell.')
                    r, c = map(int, key.split(','))
                    if not (0 <= r < data['rows'] and 0 <= c < data['cols']):
                        raise ValueError('Pentomino cell outside grid.')
                    cells.add((r,c))
                top, left = min(r for r,c in cells), min(c for r,c in cells)
                normalized = tuple(sorted((r-top,c-left) for r,c in cells))
                if normalized not in orientations(PENTOMINO_SHAPES[piece['shape']]) or occupied & cells:
                    raise ValueError('Invalid or overlapping pentomino shape.')
                occupied.update(cells)
            entries = record.get('entries')
            if not isinstance(entries, dict) or set(entries) != {f'{r},{c}' for r,c in occupied}:
                raise ValueError('Pentomino cells must all be filled.')
            if any(not isinstance(value, str) or not value.isdecimal() or not 1 <= int(value) <= data['rows'] for value in entries.values()):
                raise ValueError('Invalid pentomino digits.')
            if not isinstance(record.get('hook_digits'), list) or len(record['hook_digits']) != data['rows'] or any(type(digit) is not int for digit in record['hook_digits']) or set(record['hook_digits']) != set(range(1,data['rows']+1)):
                raise ValueError('Invalid hook digit assignment.')
    preview = analysis.get('preview')
    if 'remaining_outcome' in analysis:
        elapsed = analysis.get('remaining_elapsed')
        if analysis['remaining_outcome'] not in ('complete', 'cancelled', 'limit') or not isinstance(elapsed, (int,float)) or not math.isfinite(elapsed) or elapsed < 0 or type(analysis.get('remaining_nodes')) is not int or analysis['remaining_nodes'] < 0:
            raise ValueError('Invalid remaining-pentomino search statistics.')
    records = analysis_records(analysis)
    if type(preview) is not int or not -1 <= preview < len(records):
        raise ValueError('Invalid pentomino preview index.')
