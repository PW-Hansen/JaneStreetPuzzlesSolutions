"""Validated puzzle state, edit rules, and history; independent of the GUI."""
from copy import deepcopy
from .constants import DIRECTIONS
from .analysis import analyze_grid


def blank_cell():
    return dict(digit=None, arrows=[], shape=None, shading=0)


def validate_name(name):
    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise ValueError('Enter a name without leading or trailing spaces.')
    if any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name) or name.endswith('.'):
        raise ValueError('The name contains characters that cannot be used in a filename.')
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        raise ValueError('That name is reserved by Windows.')
    return name


def validate_cells(cells, rows, columns):
    if not isinstance(cells, list) or len(cells) != rows * columns:
        raise ValueError('The cell count does not match the dimensions.')
    for cell in cells:
        if not isinstance(cell, dict) or set(cell) != {'digit', 'arrows', 'shape', 'shading'}:
            raise ValueError('Invalid cell data.')
        if cell['digit'] is not None and (not isinstance(cell['digit'], str) or len(cell['digit']) != 1 or cell['digit'] not in '0123456789'):
            raise ValueError('Digits must be a single character from 0 to 9.')
        arrows = cell['arrows']
        if not isinstance(arrows, list) or any(a not in DIRECTIONS for a in arrows) or len(set(arrows)) != len(arrows):
            raise ValueError('Invalid arrows.')
        if cell['shape'] not in (None, 'circle', 'square') or type(cell['shading']) is not int or cell['shading'] not in (0, 1, 2):
            raise ValueError('Invalid shape or shading.')
        if arrows and (cell['digit'] is not None or cell['shape'] is not None):
            raise ValueError('Arrows cannot coexist with digits or shapes.')


class Puzzle:
    def __init__(self, name, rows, columns):
        validate_name(name)
        if type(rows) is not int or type(columns) is not int or not 1 <= rows <= 100 or not 1 <= columns <= 100:
            raise ValueError('Dimensions must be integers between 1 and 100.')
        self.name, self.rows, self.columns = name, rows, columns
        self.cells = [blank_cell() for _ in range(rows * columns)]
        self.original = deepcopy(self.cells)
        self.undo_stack, self.redo_stack = [], []
        self.selected = None
        self.update_analysis()

    def update_analysis(self):
        self.analysis = analyze_grid(self.cells, self.rows, self.columns)

    def display_cells(self):
        cells = deepcopy(self.cells)
        for cell, box in zip(cells, self.analysis.boxes):
            cell['shading'] = 0 if box is None else 2 if box else 1
        return cells

    def to_dict(self):
        return deepcopy(dict(version=1, name=self.name, rows=self.rows, columns=self.columns,
                             cells=self.cells, original=self.original, undo=self.undo_stack,
                             redo=self.redo_stack, selected=self.selected))

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get('version') != 1:
            raise ValueError('Unsupported puzzle file.')
        try:
            puzzle = cls(data['name'], data['rows'], data['columns'])
            for key in ('cells', 'original'):
                validate_cells(data[key], puzzle.rows, puzzle.columns)
            for key in ('undo', 'redo'):
                if not isinstance(data[key], list):
                    raise ValueError('Invalid history.')
                for cells in data[key]:
                    validate_cells(cells, puzzle.rows, puzzle.columns)
            selected = data.get('selected')
            if selected is not None and (type(selected) is not int or not 0 <= selected < len(puzzle.cells)):
                raise ValueError('Invalid selection.')
            puzzle.cells, puzzle.original = deepcopy(data['cells']), deepcopy(data['original'])
            puzzle.undo_stack, puzzle.redo_stack = deepcopy(data['undo']), deepcopy(data['redo'])
            puzzle.selected = selected
            puzzle.update_analysis()
            return puzzle
        except (KeyError, TypeError) as exc:
            raise ValueError('Incomplete or invalid puzzle file.') from exc

    def change(self, operation):
        before = deepcopy(self.cells)
        operation()
        if before == self.cells:
            return False
        self.undo_stack.append(before)
        self.redo_stack.clear()
        self.update_analysis()
        return True

    def edit(self, index, mode, action='click', direction=None, digit=None):
        cell = self.cells[index]
        if mode == 'Select':
            return False
        clear = action in ('clear', 'right')
        def apply():
            if mode == 'Digit Entering':
                if clear:
                    cell['digit'] = None
                elif digit is not None and not cell['arrows']:
                    cell['digit'] = digit
            elif mode == 'Arrow Entering':
                if action == 'clear':
                    cell['arrows'] = []
                elif direction and not (cell['digit'] is not None or cell['shape']):
                    if direction in cell['arrows']:
                        cell['arrows'].remove(direction)
                    elif not clear:
                        cell['arrows'].append(direction)
            elif mode == 'Circle/Square':
                if clear:
                    cell['shape'] = None
                elif not cell['arrows']:
                    options = (None, 'circle', 'square')
                    cell['shape'] = options[(options.index(cell['shape']) + 1) % 3]
            elif mode == 'Shading':
                cell['shading'] = 0 if clear else (cell['shading'] + 1) % 3
        return self.change(apply)

    def undo(self):
        if not self.undo_stack:
            return False
        self.redo_stack.append(deepcopy(self.cells))
        self.cells = self.undo_stack.pop()
        self.update_analysis()
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        self.undo_stack.append(deepcopy(self.cells))
        self.cells = self.redo_stack.pop()
        self.update_analysis()
        return True

    def reset(self, shading_only=False):
        def apply():
            if shading_only:
                for cell, original in zip(self.cells, self.original):
                    cell['shading'] = original['shading']
            else:
                self.cells = deepcopy(self.original)
        return self.change(apply)


def click_direction(x, y, size):
    dx, dy = x - size / 2, y - size / 2
    if abs(dx) > abs(dy):
        return 'east' if dx >= 0 else 'west'
    return 'south' if dy >= 0 else 'north'
