"""GUI-independent editing model and validated JSON storage."""
import copy
import json
import os
import re
import math
from pathlib import Path
from .constants import COLORS
from .hooks import canonical_borders
from .pentominoes import hook_digest, validate_pentomino_analysis, analysis_records


def safe_name(name):
    if not isinstance(name, str):
        raise ValueError('Puzzle name must be text.')
    name = name.strip()
    if not re.fullmatch(r'[\w -]{1,80}', name) or name.endswith(('.', ' ')):
        raise ValueError('Use 1–80 letters, digits, spaces, hyphens or underscores.')
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        raise ValueError('That name is reserved by Windows.')
    return name


def validate(data):
    if not isinstance(data, dict) or not all(key in data for key in ('name', 'rows', 'cols', 'entries', 'colors', 'borders')):
        raise ValueError('Invalid puzzle file.')
    safe_name(data['name'])
    rows, cols = data['rows'], data['cols']
    if type(rows) is not int or type(cols) is not int or not (1 <= rows <= 50 and 1 <= cols <= 50):
        raise ValueError('Dimensions must be between 1 and 50.')
    for field in ('entries', 'colors', 'borders'):
        if not isinstance(data[field], dict):
            raise ValueError('Invalid puzzle contents.')
    for key, value in data['entries'].items():
        r, c = map(int, key.split(','))
        if not ((0 <= r < rows and -1 <= c <= cols) or (0 <= c < cols and -1 <= r <= rows)):
            raise ValueError('Entry outside puzzle.')
        if not isinstance(value, str) or len(value) > 12 or not value.isalnum():
            raise ValueError('Entries must contain 1–12 letters or digits.')
    for key, value in data['colors'].items():
        r, c = map(int, key.split(','))
        if not (0 <= r < rows and 0 <= c < cols and type(value) is int and 1 <= value < len(COLORS)):
            raise ValueError('Invalid cell color.')
    for key, value in data['borders'].items():
        axis, r, c = key.split(',')
        r, c = int(r), int(c)
        if value is not True or not ((axis == 'h' and 0 < r < rows and 0 <= c < cols) or (axis == 'v' and 0 <= r < rows and 0 < c < cols)):
            raise ValueError('Invalid internal border.')
    result = copy.deepcopy({key: data[key] for key in ('name', 'rows', 'cols', 'entries', 'colors', 'borders')})
    if data.get('analysis') is not None:
        analysis = data['analysis']
        if not isinstance(analysis, dict) or analysis.get('source_entries') != data['entries']:
            raise ValueError('Hook analysis does not match the puzzle entries.')
        candidates = analysis.get('candidates')
        if not isinstance(candidates, list):
            raise ValueError('Invalid hook candidates.')
        for candidate in candidates:
            validate(dict(result, borders=candidate))
        preview = analysis.get('preview')
        if type(preview) is not int or not -1 <= preview < len(candidates):
            raise ValueError('Invalid hook preview.')
        if analysis.get('outcome') not in ('complete', 'cancelled', 'limit'):
            raise ValueError('Invalid hook search outcome.')
        elapsed = analysis.get('elapsed')
        if not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('Invalid analysis elapsed time.')
        if type(analysis.get('nodes')) is not int or analysis['nodes'] < 0:
            raise ValueError('Invalid analysis branch count.')
        result['analysis'] = copy.deepcopy(analysis)
        result['analysis']['canonical_borders'] = canonical_borders(candidates, analysis['outcome'])
    if data.get('pentomino_analysis') is not None:
        validate_pentomino_analysis(result, data['pentomino_analysis'])
        result['pentomino_analysis'] = copy.deepcopy(data['pentomino_analysis'])
    return result


def read(path):
    return validate(json.loads(Path(path).read_text(encoding='utf-8')))


def write(path, data):
    validate(data)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def save_snapshot(path, puzzle, selected):
    payload = dict(puzzle.data, session={
        'undo': puzzle.undo_stack, 'redo': puzzle.redo_stack,
        'selected': selected,
    })
    write(path, payload)


def load_snapshot(path, puzzle):
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    data = validate(payload)
    session = payload.get('session', {})
    if not isinstance(session, dict):
        raise ValueError('Invalid snapshot session.')
    history = []
    for field in ('undo', 'redo'):
        values = session.get(field, [])
        if not isinstance(values, list):
            raise ValueError('Invalid snapshot history.')
        validated = [validate(value) for value in values]
        for value in validated + [data]:
            if any(value[key] != puzzle.data[key] for key in ('name', 'rows', 'cols')):
                raise ValueError('Saved state belongs to a different puzzle or dimensions.')
        history.append(validated)
    selected = session.get('selected')
    if selected is not None:
        if not isinstance(selected, (list, tuple)) or len(selected) != 2 or any(type(v) is not int for v in selected):
            raise ValueError('Invalid saved selection.')
        r, c = selected
        rows, cols = data['rows'], data['cols']
        if not ((0 <= r < rows and -1 <= c <= cols) or (0 <= c < cols and -1 <= r <= rows)):
            raise ValueError('Invalid saved selection.')
    # Validate the entire file before changing any live data.
    previous = copy.deepcopy(puzzle.data)
    puzzle.data = data
    puzzle.undo_stack = history[0] + [previous]
    puzzle.redo_stack = history[1]
    return tuple(selected) if selected is not None else None


class Puzzle:
    def __init__(self, name, rows, cols):
        self.data = validate(dict(name=safe_name(name), rows=rows, cols=cols, entries={}, colors={}, borders={}))
        self.undo_stack, self.redo_stack = [], []

    def change(self, field, key, value):
        new = copy.deepcopy(self.data)
        if value is None:
            new[field].pop(key, None)
        else:
            new[field][key] = value
        self.replace(new)

    def replace(self, new):
        if new.get('entries') != self.data['entries'] and new.get('analysis') == self.data.get('analysis'):
            new = dict(new, analysis=None)
        if new.get('pentomino_analysis') == self.data.get('pentomino_analysis') and (
            new.get('entries') != self.data['entries'] or new.get('borders') != self.data['borders']
            or hook_digest(new) != hook_digest(self.data)):
            new = dict(new, pentomino_analysis=None)
        new = validate(new)
        if (new['name'], new['rows'], new['cols']) != (self.data['name'], self.data['rows'], self.data['cols']):
            raise ValueError('Saved state belongs to a different puzzle or dimensions.')
        if new != self.data:
            self.undo_stack.append(copy.deepcopy(self.data))
            self.data, self.redo_stack = new, []

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.data)
            self.data = self.undo_stack.pop()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.data)
            self.data = self.redo_stack.pop()

    def reset_edits(self):
        self.replace(dict(self.data, entries={}, colors={}, borders={}, analysis=None, pentomino_analysis=None))

    def clear_cell_borders(self, row, col):
        new = copy.deepcopy(self.data)
        for edge in (f'h,{row},{col}', f'h,{row+1},{col}', f'v,{row},{col}', f'v,{row},{col+1}'):
            new['borders'].pop(edge, None)
        self.replace(new)

    def set_hook_analysis(self, search, elapsed):
        analysis = dict(source_entries=copy.deepcopy(self.data['entries']),
                        candidates=copy.deepcopy(search.candidates), preview=0 if search.candidates else -1,
                        outcome=search.outcome, elapsed=elapsed, nodes=search.nodes)
        self.replace(dict(self.data, analysis=analysis, pentomino_analysis=None))

    def preview_hooks(self, index):
        analysis = self.data.get('analysis')
        if analysis is not None and -1 <= index < len(analysis['candidates']):
            analysis['preview'] = index
            if self.data.get('pentomino_analysis'):
                self.data['pentomino_analysis']['preview'] = -1

    def use_hook_preview(self):
        analysis = self.data.get('analysis')
        if analysis is not None and analysis['preview'] >= 0:
            new = copy.deepcopy(self.data)
            new['borders'].update(analysis['candidates'][analysis['preview']])
            new['analysis']['preview'] = -1
            self.replace(new)

    def set_pentomino_analysis(self, search, elapsed):
        hooks = copy.deepcopy(self.data['analysis'])
        retained = [index for index in range(len(hooks['candidates'])) if index not in search.rejected_layouts]
        remap = {old: new for new, old in enumerate(retained)}
        hooks['candidates'] = [hooks['candidates'][index] for index in retained]
        hooks['preview'] = remap.get(hooks['preview'], 0 if retained else -1)
        new = dict(self.data, analysis=hooks)

        def surviving_records(records):
            return [dict(copy.deepcopy(record), hook_index=remap[record['hook_index']])
                    for record in records if record['hook_index'] in remap]

        candidates = surviving_records(search.candidates)
        placements = surviving_records(search.placements)
        analysis = dict(source_entries=copy.deepcopy(self.data['entries']),
                        source_borders=copy.deepcopy(self.data['borders']), source_hook_digest=hook_digest(new),
                        candidates=candidates, placements=placements,
                        view='combinations', preview=0 if candidates else -1,
                        outcome=search.outcome, elapsed=elapsed, nodes=search.nodes,
                        source_incomplete=search.source_incomplete,
                        discarded_hook_layouts=len(search.rejected_layouts))
        new['pentomino_analysis'] = analysis
        if candidates:
            new['analysis']['preview'] = candidates[0]['hook_index']
        self.replace(new)

    def preview_pentominoes(self, index, view=None):
        analysis = self.data.get('pentomino_analysis')
        if analysis is None:
            return
        if view is not None:
            analysis['view'] = view
        records = analysis_records(analysis)
        if -1 <= index < len(records):
            analysis['preview'] = index
            if index >= 0:
                self.data['analysis']['preview'] = records[index]['hook_index']

    def set_remaining_pentomino_analysis(self, search, elapsed):
        analysis = copy.deepcopy(self.data['pentomino_analysis'])
        surviving = [index for index in range(len(analysis['candidates'])) if index not in search.rejected_combinations]
        base_remap = {old:new for new,old in enumerate(surviving)}
        analysis['candidates'] = [analysis['candidates'][index] for index in surviving]
        hooks = copy.deepcopy(self.data['analysis'])
        keep_hooks = {record['hook_index'] for record in analysis['candidates']}
        retained = [index for index in range(len(hooks['candidates']))
                    if analysis['outcome'] != 'complete' or index in keep_hooks]
        hook_remap = {old:new for new,old in enumerate(retained)}
        discarded_hooks = len(hooks['candidates'])-len(retained)
        hooks['candidates'] = [hooks['candidates'][index] for index in retained]
        hooks['preview'] = hook_remap.get(hooks['preview'], 0 if retained else -1)
        for record in analysis['candidates']:
            record['hook_index'] = hook_remap[record['hook_index']]
        analysis['placements'] = [dict(record, hook_index=hook_remap[record['hook_index']])
                                  for record in analysis['placements'] if record['hook_index'] in hook_remap]
        analysis['extensions'] = [dict(copy.deepcopy(record), hook_index=hook_remap[record['hook_index']],
                                       base_index=base_remap[record['base_index']])
                                  for record in search.candidates if record['base_index'] in base_remap]
        analysis.update(remaining_outcome=search.outcome, remaining_elapsed=elapsed,
                        remaining_nodes=search.nodes, remaining_source_incomplete=search.source_incomplete,
                        discarded_combinations=len(search.rejected_combinations),
                        discarded_hook_layouts=analysis.get('discarded_hook_layouts',0)+discarded_hooks,
                        view='extensions', preview=0 if search.candidates else -1)
        new = dict(self.data, analysis=hooks, pentomino_analysis=analysis)
        analysis['source_hook_digest'] = hook_digest(new)
        if analysis['extensions']:
            hooks['preview'] = analysis['extensions'][0]['hook_index']
        self.replace(new)
