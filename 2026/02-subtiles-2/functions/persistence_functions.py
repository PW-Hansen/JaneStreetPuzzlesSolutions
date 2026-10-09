"""Grid validation, JSON persistence, snapshot serialization, and migration."""

import argparse
import json
import re
from fractions import Fraction
from pathlib import Path

PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent
DATA_DIRECTORY = PROJECT_DIRECTORY / "grids"

def grid_name(value):
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value)
            or value.upper() in {"CON", "PRN", "AUX", "NUL",
                                 *(f"COM{i}" for i in range(1, 10)),
                                 *(f"LPT{i}" for i in range(1, 10))}):
        raise argparse.ArgumentTypeError("Use a name of up to 64 letters, digits, hyphens, or underscores.")
    return value


def read_state(path):
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("Expected saved grid settings")
    expressions = state.get("expressions")
    size = state.get("size", len(expressions) if isinstance(expressions, list) else 0)
    if (type(size) is not int or size < 1
            or not isinstance(expressions, list) or len(expressions) != size
            or any(not isinstance(row, list) or len(row) != size
                   or any(not isinstance(cell, str) for cell in row) for row in expressions)):
        raise ValueError("Expected a square grid of expressions")
    variables = state.get("variables", {})
    if (not isinstance(variables, dict)
            or any(not isinstance(name, str) or not re.fullmatch(r"[a-z]+", name)
                   or not isinstance(value, str) for name, value in variables.items())
            or type(state.get("show_values", False)) is not bool):
        raise ValueError("Invalid saved settings")
    state["size"] = size
    disabled = state.get("disabled_cells", [])
    if (not isinstance(disabled, list) or any(type(cell) is not int or not 0 <= cell < size*size for cell in disabled)):
        raise ValueError("Invalid disabled cells")
    return state


def encode_overlay(value):
    """JSON-safe representation retaining cell keys, sets, and tuples."""
    if isinstance(value,dict):
        return {'type':'dict','items':[[encode_overlay(key),encode_overlay(item)] for key,item in value.items()]}
    if isinstance(value,(set,frozenset,tuple)):
        return {'type':type(value).__name__,'items':[encode_overlay(item) for item in value]}
    if isinstance(value,list): return [encode_overlay(item) for item in value]
    return value


def decode_overlay(value):
    if isinstance(value,list): return [decode_overlay(item) for item in value]
    if isinstance(value,dict):
        kind,items = value['type'],value['items']
        if kind == 'dict': return {decode_overlay(key):decode_overlay(item) for key,item in items}
        constructors = {'set':set,'frozenset':frozenset,'tuple':tuple}
        return constructors[kind](decode_overlay(item) for item in items)
    return value


def write_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def make_grid_state(size, expressions, disabled, variables, target, show_values, assignments, steps):
    state = {'size':size,'expressions':expressions,'disabled_cells':sorted(disabled),
             'variables':variables,'overlay_region':target,'show_values':show_values}
    if assignments is not None:
        state['analysis'] = {
            'assignments':[{name:None if value is None else str(value) for name,value in item.items()}
                           for item in assignments], 'steps':steps}
    return state


def make_saved_state(state, snapshot, undo, redo, selected, valid_values, search_message, connectivity_message):
    return {**state,'overlay_snapshot':encode_overlay(snapshot),
            'overlay_history':encode_overlay({'undo':undo,'redo':redo}),
            'selected':list(selected),'valid_values':valid_values,
            'search_message':search_message,'connectivity_message':connectivity_message}


def load_snapshot(path, size, variable_names):
    state = read_state(path)
    if state['size'] != size or set(state['variables']) != set(variable_names):
        raise ValueError('Saved state has a different grid size or variable configuration.')
    snapshot = decode_overlay(state['overlay_snapshot'])
    required = {'states','index','highest','base','tested','target','message','labels','palette'}
    if not isinstance(snapshot,dict) or not required <= snapshot.keys():
        raise ValueError('Invalid saved overlay snapshot.')
    history = decode_overlay(state.get('overlay_history',encode_overlay({'undo':[],'redo':[]})))
    selected = state.get('selected',[0,0])
    if (not isinstance(selected,list) or len(selected) != 2
            or any(type(value) is not int or not 0 <= value < size for value in selected)):
        raise ValueError('Invalid selected cell.')
    analysis = state.get('analysis')
    assignments = None if analysis is None else [
        {name:None if value is None else Fraction(value) for name,value in item.items()}
        for item in analysis['assignments']]
    return state,snapshot,history,selected,analysis,assignments


def migrate_example():
    """Preserve the previous single grid as the named example grid."""
    old_path = PROJECT_DIRECTORY / "grid_state.json"
    new_path = DATA_DIRECTORY / "example.json"
    if old_path.exists() and not new_path.exists():
        write_state(new_path, read_state(old_path))
