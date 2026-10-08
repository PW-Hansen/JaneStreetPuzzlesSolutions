"""Puzzle state validation, persistence, candidate caches, and clue ordering."""
import argparse
import json
import os
import re
from pathlib import Path
from functions.constants import ARC_CYCLE, DATA_DIRECTORY, SOLUTION_ORDER_PATH, DEFAULT_ANALYSIS_WEIGHTS
from functions.puzzle_model import allowed_arc_configurations


def grid_name(value):
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value)
            or value.upper() in {"CON", "PRN", "AUX", "NUL",
                                 *(f"COM{i}" for i in range(1, 10)),
                                 *(f"LPT{i}" for i in range(1, 10))}):
        raise argparse.ArgumentTypeError("Use up to 64 letters, digits, hyphens, or underscores, starting with a letter or digit; avoid reserved Windows names.")
    return value



def parse_grid_size(value):
    parts = re.split(r"\s*[xX×]\s*", value.strip())
    if len(parts) not in (1, 2):
        raise ValueError("Enter a size such as 10 or 8x12 (rows x columns).")
    try:
        rows = int(parts[0])
        columns = int(parts[-1])
    except ValueError:
        raise ValueError("Enter a size such as 10 or 8x12 (rows x columns).") from None
    if not (1 <= rows <= 50 and 1 <= columns <= 50):
        raise ValueError("Use 1–50 rows and columns.")
    return rows, columns



def read_state(path):
    try:
        return validate_state(json.loads(path.read_text(encoding="utf-8")))
    except (KeyError, TypeError) as exc:
        raise ValueError("Invalid saved puzzle data.") from exc



def prepare_grid(name, size=None):
    path = DATA_DIRECTORY / f"{name}.json"
    if path.exists():
        state = read_state(path)
        if size is not None and (state["rows"], state["columns"]) != size:
            raise ValueError("That name already has a different grid size. Use its saved size or choose another name.")
    else:
        if size is None:
            raise ValueError("A grid size is required for a new puzzle.")
        rows, columns = size
        state = {"version": 1, "rows": rows, "columns": columns,
                 "cells": blank_grid(rows, columns)}
        validate_state(state)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    return path



def blank_grid(rows, columns):
    return [[{"green": False, "number": None, "arc": None}
             for _ in range(columns)] for _ in range(rows)]



def ordered_clues(state, weights=DEFAULT_ANALYSIS_WEIGHTS):
    from fractions import Fraction
    conditional_weight, edge_weight, green_weight = map(lambda value: Fraction(str(value)), weights)
    # Equivalent trigger orientations are one grouped conditional, matching
    # the display and propagation rather than inflating their importance.
    conditionals = {(tuple(rule['if'][:2]), tuple(rule['then'][:2]), frozenset(rule['then'][2]))
                    for rule in state.get('arc_implications', [])}
    ranked = []
    for r, row in enumerate(state['cells']):
        for c, cell in enumerate(row):
            if cell['number'] is None:
                continue
            nearby = {(r, c), (r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)}
            count = sum(source in nearby or target in nearby for source, target, _ in conditionals)
            green = int(cell['green']) + sum(state['cells'][nr][nc]['green']
                for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1))
                if 0 <= nr < state['rows'] and 0 <= nc < state['columns'])
            edge = r in (0, state['rows'] - 1) or c in (0, state['columns'] - 1)
            score = Fraction(cell['number']) * conditional_weight ** count * green_weight ** green
            if edge:
                score *= edge_weight
            ranked.append((score, r, c))
    return [(r, c) for _, r, c in sorted(ranked)]



def fixed_clue_order(state, puzzle_name, order_path=None):
    path = Path(order_path) if order_path is not None else SOLUTION_ORDER_PATH
    try:
        orders = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'Cannot read set orders from {path.name}: {exc}') from exc
    if not isinstance(orders, dict) or puzzle_name not in orders:
        raise ValueError(f'No set order is configured for puzzle {puzzle_name}.')
    entries = orders[puzzle_name]
    if not isinstance(entries, list) or not entries:
        raise ValueError(f'The set order for {puzzle_name} must be a nonempty list.')
    sequence = []
    for entry in entries:
        if not isinstance(entry, dict) or any(type(entry.get(key)) is not int for key in ('row', 'column', 'clue')):
            raise ValueError('Each set-order entry needs integer row, column, and clue fields.')
        r, c, clue = entry['row'] - 1, entry['column'] - 1, entry['clue']
        if not (0 <= r < state['rows'] and 0 <= c < state['columns']):
            raise ValueError(f'Set-order cell r{r + 1}c{c + 1} is outside the grid.')
        if state['cells'][r][c]['number'] != clue:
            raise ValueError(f'The expected {clue} at r{r + 1}c{c + 1} is missing.')
        if (r, c) in sequence:
            raise ValueError(f'Set-order cell r{r + 1}c{c + 1} is repeated.')
        sequence.append((r, c))
    return sequence



def save_accepted_states(state, selected, result):
    if (result.heuristic or result.cancelled or result.limit_reached or result.worklist_limit_reached
            or len(result.accepted_states) >= 25):
        return False
    r, c = selected
    state.setdefault('saved_analyses', {})[f'{r},{c}'] = {
        'clue': state['cells'][r][c]['number'],
        'states': [[list(placement) for placement in accepted] for accepted in result.accepted_states]}
    return True



def prune_saved_states(state):
    """Discard local previews conflicting with actual drawn arcs, not omissions."""
    removed = 0
    saved = state.get('saved_analyses', {})
    for key, entry in list(saved.items()):
        surviving = [accepted for accepted in entry['states']
                     if all(state['cells'][r][c]['arc'] is None
                            or state['cells'][r][c]['arc'] == arc for r, c, arc in accepted)]
        removed += len(entry['states']) - len(surviving)
        if surviving:
            entry['states'] = surviving
        else:
            del saved[key]
    return removed



def validate_state(state):
    rows, columns = state["rows"], state["columns"]
    if type(rows) is not int or type(columns) is not int or not (1 <= rows <= 50 and 1 <= columns <= 50):
        raise ValueError("Grid dimensions must be integers between 1 and 50.")
    cells = state["cells"]
    if len(cells) != rows or any(len(row) != columns for row in cells):
        raise ValueError("Cell data does not match the grid dimensions.")
    for row in cells:
        for cell in row:
            if type(cell["green"]) is not bool:
                raise ValueError("Invalid green-cell value.")
            number = cell["number"]
            if number is not None and (type(number) is not int or number < 0):
                raise ValueError("Clues must be nonnegative integers.")
            if cell["arc"] not in (None, "tl", "tr", "br", "bl"):
                raise ValueError("Invalid arc orientation.")
            if cell["green"] and cell["arc"] is not None:
                raise ValueError("Green cells cannot contain arcs.")
    domains = state.get("arc_domains")
    if domains is not None:
        if (not isinstance(domains, list) or len(domains) != rows
                or any(not isinstance(row, list) or len(row) != columns for row in domains)):
            raise ValueError("Arc master list does not match the grid dimensions.")
        for r, row in enumerate(domains):
            for c, domain in enumerate(row):
                if (not isinstance(domain, list) or not domain
                        or any(orientation not in ARC_CYCLE for orientation in domain)
                        or len(set(domain)) != len(domain)):
                    raise ValueError("Invalid arc master-list entry.")
                if not allowed_arc_configurations(state, r, c):
                    raise ValueError("Arc master list contradicts the cell markings.")
    rules = state.get('arc_implications', [])
    if not isinstance(rules, list):
        raise ValueError('Conditional arc deductions must be a list.')
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {'if', 'then'}:
            raise ValueError('Invalid conditional arc deduction.')
        source, target = rule['if'], rule['then']
        if (not isinstance(source, list) or not isinstance(target, list) or len(source) != 3 or len(target) != 3
            or any(not isinstance(v, int) or isinstance(v, bool) for v in source[:2] + target[:2])
            or not (0 <= source[0] < rows and 0 <= source[1] < columns
                    and 0 <= target[0] < rows and 0 <= target[1] < columns)
            or source[2] not in ARC_CYCLE or not isinstance(target[2], list) or not target[2]
            or any(arc not in ARC_CYCLE for arc in target[2])):
            raise ValueError('Invalid conditional arc deduction.')
    if rules:
        from functions.arc_constraints import propagate_arc_domains
        if propagate_arc_domains(state) is None:
            raise ValueError('Conditional deductions contradict the current markings or master list.')
    saved = state.get('saved_analyses', {})
    if not isinstance(saved, dict):
        raise ValueError('Saved clue analyses must be a mapping.')
    for key, entry in saved.items():
        try:
            r, c = map(int, key.split(','))
            if not (0 <= r < rows and 0 <= c < columns):
                raise ValueError()
            if entry['clue'] != cells[r][c]['number'] or entry['clue'] is None:
                raise ValueError()
            accepted = entry['states']
            if not isinstance(accepted, list) or len(accepted) >= 25:
                raise ValueError()
            for placements in accepted:
                if not isinstance(placements, list):
                    raise ValueError()
                seen = set()
                for nr, nc, arc in placements:
                    if (type(nr) is not int or type(nc) is not int or
                            not (0 <= nr < rows and 0 <= nc < columns) or arc not in ARC_CYCLE
                            or (nr, nc) in seen or cells[nr][nc]['green'] and arc is not None):
                        raise ValueError()
                    seen.add((nr, nc))
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ValueError('Invalid saved clue analysis.') from None
    return state

