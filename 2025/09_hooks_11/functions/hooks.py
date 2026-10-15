"""Incremental outward hook search, independent of Tkinter.

Only the requested geometry, digit-consistency, cell-capacity and small-hook
digit constraints are used. A hook's digit need not equal its arm length.
"""
from dataclasses import dataclass, field

from .constants import (HOOK_NODE_LIMIT, HOOK_CANDIDATE_LIMIT,
                        HOOK_ALLOWED_DIGITS, HOOK_ANCHOR_ADJACENT_ALLOWED_DIGITS,
                        HOOK_ANCHOR_SINGLE_EDGE_ALLOWED_DIGITS)


def anchor_cell(data):
    if data['rows'] != data['cols']:
        raise ValueError('Drawing nested hooks requires a square grid.')
    ones = []
    for key, value in data['entries'].items():
        r, c = map(int, key.split(','))
        if 0 <= r < data['rows'] and 0 <= c < data['cols'] and value.isdecimal() and int(value) == 1:
            ones.append((r, c))
    if len(ones) != 1:
        raise ValueError('Enter exactly one 1-clue inside the grid before drawing hooks.')
    return ones[0]


def hook_cells(inner, outer):
    """Cells added by growing a square by one row and one column."""
    top, left, size = inner
    new_top, new_left, new_size = outer
    row = new_top if new_top < top else new_top + new_size - 1
    col = new_left if new_left < left else new_left + new_size - 1
    return ([(row, c) for c in range(new_left, new_left + new_size)] +
            [(r, col) for r in range(new_top, new_top + new_size) if r != row])


def small_hook_digits_allowed(cells, digits, anchor):
    """Apply cell-count rules and orthogonal adjacency to the singleton."""
    allowed = HOOK_ALLOWED_DIGITS.get(len(cells))
    if allowed is not None and not digits <= allowed:
        return False
    adjacent_allowed = HOOK_ANCHOR_ADJACENT_ALLOWED_DIGITS.get(len(cells))
    if adjacent_allowed is not None:
        row, col = anchor
        shared_edges = sum(abs(r-row) + abs(c-col) == 1 for r, c in cells)
        if shared_edges == 1:
            adjacent_allowed = HOOK_ANCHOR_SINGLE_EDGE_ALLOWED_DIGITS.get(len(cells), adjacent_allowed)
        if shared_edges and not digits <= adjacent_allowed:
            return False
    return True


def available_five_cell_digits(cells, anchor, digits):
    """Possible digits for a five-cell hook, considering givens anywhere."""
    cells = set(cells)
    known = {digit for cell, digit in digits.items() if cell in cells}
    elsewhere = {digit for cell, digit in digits.items() if cell not in cells}
    possible = set(HOOK_ALLOWED_DIGITS[5]) - elsewhere
    if known:
        possible = possible & known if len(known) == 1 else set()
    return {digit for digit in possible if small_hook_digits_allowed(cells, {digit}, anchor)}


def outside_two_rays(data):
    """Only outside 2-clues participate in this special-case hook rule."""
    return outside_digit_rays(data, {2})


def outside_digit_rays(data, allowed_digits):
    """Sightlines for a selected set of outside numeric clue values."""
    rows, cols = data['rows'], data['cols']
    rays = []
    for key, value in data['entries'].items():
        r, c = map(int, key.split(','))
        if not value.isdecimal() or int(value) not in allowed_digits or (0 <= r < rows and 0 <= c < cols):
            continue
        if r == -1:
            ray = [(row,c) for row in range(rows)]
        elif r == rows:
            ray = [(row,c) for row in reversed(range(rows))]
        elif c == -1:
            ray = [(r,col) for col in range(cols)]
        else:
            ray = [(r,col) for col in reversed(range(cols))]
        rays.append(tuple(ray))
    return rays


def five_cell_digits_from_clues(possible, cells, three_cells, rays_by_digit, filled):
    """Filter candidate digits using only their own outside clue sightlines."""
    cells, three_cells, filled = set(cells), set(three_cells), set(filled)

    def can_see(ray):
        through_three = 0
        for cell in ray:
            if cell in cells:
                return True
            if cell in filled:
                return False
            if cell in three_cells:
                through_three += 1
                if through_three >= 2:
                    return False
        return False

    return {digit for digit in possible if all(can_see(ray) for ray in rays_by_digit.get(digit, ()))}


def three_cell_hook_visible(cells, rays, filled):
    """Every 2-clue needs an unobstructed possible filled cell in this hook."""
    cells, filled = set(cells), set(filled)
    room_for_two = len(cells & filled) < 2
    for ray in rays:
        for cell in ray:
            if cell in cells and (room_for_two or cell in filled):
                break
            if cell in filled:
                return False
        else:
            return False
    return True


def partition_borders(hooks, rows, cols):
    owner = {cell: index for index, hook in enumerate(hooks) for cell in hook}
    borders = {}
    for r in range(rows):
        for c in range(cols):
            if r and owner[r, c] != owner[r-1, c]:
                borders[f'h,{r},{c}'] = True
            if c and owner[r, c] != owner[r, c-1]:
                borders[f'v,{r},{c}'] = True
    return borders


def canonical_borders(candidates, outcome):
    """Only an exhaustive, nonempty set of layouts proves shared borders."""
    if outcome != 'complete' or not candidates:
        return {}
    shared = set(candidates[0])
    for candidate in candidates[1:]:
        shared.intersection_update(candidate)
    return {edge: True for edge in sorted(shared)}


@dataclass
class HookSearch:
    data: dict
    node_limit: int = HOOK_NODE_LIMIT
    candidate_limit: int = HOOK_CANDIDATE_LIMIT
    candidates: list = field(default_factory=list, init=False)
    nodes: int = field(default=0, init=False)
    size: int = field(default=1, init=False)
    outcome: str = field(default='running', init=False)
    cancelled: bool = field(default=False, init=False)

    def __post_init__(self):
        self.anchor = anchor_cell(self.data)

    def run(self):
        """Yield after every branch so callers can schedule bounded work."""
        n = self.data['rows']
        digits = {}
        for key, value in self.data['entries'].items():
            r, c = map(int, key.split(','))
            if 0 <= r < n and 0 <= c < n and value.isdecimal():
                digits[r, c] = int(value)
        two_rays = outside_two_rays(self.data)
        five_rays = {digit: outside_digit_rays(self.data, {digit}) for digit in HOOK_ALLOWED_DIGITS[5]}
        if n < 2 and two_rays:
            self.outcome = 'complete'
            return
        stack = [((*self.anchor, 1), [[self.anchor]])]
        while stack:
            if self.cancelled:
                self.outcome = 'cancelled'
                return
            if self.nodes >= self.node_limit or len(self.candidates) >= self.candidate_limit:
                self.outcome = 'limit'
                return
            square, hooks = stack.pop()
            self.nodes += 1
            self.size = square[2]
            if self.size == n:
                self.candidates.append(partition_borders(hooks, n, n))
            else:
                top, left, size = square
                for new_top in (top, top-1):
                    for new_left in (left, left-1):
                        outer = (new_top, new_left, size+1)
                        if new_top < 0 or new_left < 0 or new_top+size+1 > n or new_left+size+1 > n:
                            continue
                        cells = hook_cells(square, outer)
                        hook_digits = {digits[cell] for cell in cells if cell in digits}
                        if len(hook_digits) > 1 or any(digit > len(cells) for digit in hook_digits):
                            continue
                        if not small_hook_digits_allowed(cells, hook_digits, self.anchor):
                            continue
                        if len(cells) == 3 and not three_cell_hook_visible(cells, two_rays, digits):
                            continue
                        if len(cells) == 5:
                            possible = available_five_cell_digits(cells, self.anchor, digits)
                            if not five_cell_digits_from_clues(possible, cells, hooks[1], five_rays, digits):
                                continue
                        stack.append((outer, hooks + [cells]))
            yield None
        self.outcome = 'cancelled' if self.cancelled else 'complete'
