"""Answer key: product of areas of connected empty-cell regions."""
from collections import Counter
from dataclasses import dataclass
from math import prod

from .display_state import displayed_entries
from .pentominoes import has_filled_square, filled_region_connected


@dataclass(frozen=True)
class AnswerKey:
    areas: tuple
    value: int

    def report(self):
        factors = ' x '.join(map(str,self.areas)) if self.areas else '1 (no empty regions)'
        return f'Empty region areas: {factors}\nAnswer key: {self.value}'


def compute_answer_key(data):
    rows, cols = data['rows'], data['cols']
    if rows != cols:
        raise ValueError('Answer generation requires a completed square hooks grid.')
    filled = {}
    for key,value in displayed_entries(data).items():
        r,c = map(int,key.split(','))
        if 0 <= r < rows and 0 <= c < cols and value.isdecimal():
            filled[r,c] = int(value)
    if Counter(filled.values()) != Counter({digit:digit for digit in range(1,rows+1)}):
        raise ValueError('The displayed grid is incomplete: each digit n must occur exactly n times.')
    if has_filled_square(set(filled)):
        raise ValueError('The displayed grid contains a filled 2x2 region.')
    if not filled_region_connected(set(filled)):
        raise ValueError('The filled cells must form one orthogonally connected region.')
    remaining = {(r,c) for r in range(rows) for c in range(cols)}-set(filled)
    areas = []
    while remaining:
        pending = [remaining.pop()]
        area = 0
        while pending:
            r,c = pending.pop()
            area += 1
            for cell in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)):
                if cell in remaining:
                    remaining.remove(cell)
                    pending.append(cell)
        areas.append(area)
    areas = tuple(sorted(areas))
    return AnswerKey(areas,prod(areas))
