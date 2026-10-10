"""Answer-key calculation from an applied, face-labelled fold."""
from dataclasses import dataclass
from math import prod
from .constants import FACE_COLORS


@dataclass(frozen=True)
class AnswerKey:
    face_sums: dict
    value: int

    def report(self):
        lines = [f'{face}: {total}' for face, total in self.face_sums.items()]
        factors = ' × '.join(str(total) for total in self.face_sums.values())
        return '\n'.join(lines) + f'\n\nAnswer key: {factors} = {self.value}'


def compute_answer_key(puzzle):
    if puzzle.analysis.conflicts:
        raise ValueError('Resolve the grid contradictions before computing the answer key.')
    sums = dict.fromkeys(FACE_COLORS, 0)
    present = set()
    for cell in puzzle.cells:
        if cell['shading'] == 0:
            raise ValueError('Apply a unique fold before computing the answer key: unknown cells remain.')
        if cell['shading'] != 2:
            continue
        face = cell.get('face')
        if face not in sums:
            raise ValueError('Apply a unique fold first so every box cell has a face assignment.')
        present.add(face)
        if cell['digit'] is not None:
            sums[face] += int(cell['digit'])
    if present != set(sums):
        raise ValueError('The applied fold must include all six faces.')
    return AnswerKey(sums, prod(sums.values()))
