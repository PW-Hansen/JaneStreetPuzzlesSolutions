"""Solve a named puzzle from saved states/<name>/initial_state.json, without a GUI."""
import argparse
import copy
import json
import os
from pathlib import Path
from time import perf_counter

from functions.arc_constraints import apply_arc_deductions
from functions.clue_analysis import incorporate_analysis, analysis_timing_summary
from functions.incremental_analysis import analyze_clue_with_sanity
from functions.local_conditionals import scan_local_conditionals
from functions.solver_analysis import GreedySolveSession
from functions.constants import SAVED_STATES_DIRECTORY, SOLUTION_ORDER_PATH, DEFAULT_ANALYSIS_WEIGHTS
from functions.dialogs import AnalysisWeightsDialog
from functions.puzzle_model import determine_regions, compute_answer_key
from functions.puzzle_state import (grid_name, validate_state, fixed_clue_order,
                                    ordered_clues, save_accepted_states, prune_saved_states)


def load_initial_state(name, folder=None):
    folder = SAVED_STATES_DIRECTORY if folder is None else folder
    path = Path(folder) / name / 'initial_state.json'
    if not path.is_file():
        raise ValueError(f'Initial state not found: {path}')
    data = json.loads(path.read_text(encoding='utf-8'))
    if 'state' in data:
        if data.get('puzzle_name') != name:
            raise ValueError(f'Initial state belongs to a different puzzle: {path}')
        data = data['state']
    try:
        return validate_state(data)
    except (KeyError, TypeError) as exc:
        raise ValueError(f'Invalid initial state: {path}') from exc


def prompt_weights():
    """Use the editor's validated modal dialog without opening the editor."""
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        return AnalysisWeightsDialog(root, title='Dynamic analysis weights').result
    finally:
        root.destroy()


def configured_order(state, name, path=None):
    path = SOLUTION_ORDER_PATH if path is None else path
    path = Path(path)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Solution clue orders must be a mapping of puzzle names.')
    return fixed_clue_order(state, name, path) if name in data else None


def write_result(path, name, state, elapsed):
    """Write a snapshot that the GUI's Load state button can restore."""
    snapshot = {'puzzle_name': name, 'state': state, 'undo': [], 'redo': [],
        'view': {'selected': None, 'mode': 'select', 'preview_index': 0, 'accepted_states': [],
                 'source_clue': None, 'smooth_colors': [], 'region_colors': [],
                 'area_labels': None, 'search_time': None, 'total_time': elapsed}}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(snapshot, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def solve(state, name, output, order=None, weights=DEFAULT_ANALYSIS_WEIGHTS, log=print, greedy=False):
    output = Path(output)
    checkpoint = output.with_name('checkpoint_state.json')
    verified = False
    started = perf_counter()
    log('Scanning local conditionals...')
    state, counts = scan_local_conditionals(copy.deepcopy(state))
    if state.get('arc_implications'):
        apply_arc_deductions(state)
    prune_saved_states(state)
    log(f'Local scan: {counts["removed"]} configurations removed.')
    options = state.get('analysis_options', {})
    kwargs = {'simplify_nonclue': options.get('simplify_arcs', True),
              'prioritize_frontier': options.get('prioritize_cells', True),
              'check_other_clues': options.get('check_other_clues', True)}
    passes = 0
    session = None
    try:
        while True:
            if greedy:
                session = GreedySolveSession(state, order, weights, kwargs, log,
                    lambda current: write_result(checkpoint, name, current, perf_counter() - started))
                state = session.run()
                regions = set(determine_regions(state)[0].values())
                if all(region.verify(state) for region in regions):
                    log(f'Answer key: {compute_answer_key(state)["answer"]}')
                    verified = True
                break
            passes += 1
            previous_arcs = {(r, c, cell['arc']) for r, row in enumerate(state['cells'])
                             for c, cell in enumerate(row) if cell['arc'] is not None}
            pending = list(order) if order is not None else ordered_clues(state, weights)
            while pending:
                if order is None:
                    remaining = set(pending)
                    pending = [cell for cell in ordered_clues(state, weights) if cell in remaining]
                selected = pending.pop(0)
                r, c = selected
                clue = state['cells'][r][c]['number']
                log(f'Pass {passes}: starting analysis of clue {clue} at r{r + 1}c{c + 1}')
                clue_started = perf_counter()
                result = analyze_clue_with_sanity(state, selected,
                    timer=perf_counter, started_at=clue_started, **kwargs)
                if result.sanity_pruned:
                    log(f'Sanity checks rejected {result.sanity_pruned} accepted states '
                        f'for clue {clue} at r{r + 1}c{c + 1}.')
                updated = copy.deepcopy(state)
                incorporate_analysis(updated, result)
                save_accepted_states(updated, selected, result)
                if updated.get('arc_implications'):
                    apply_arc_deductions(updated)
                prune_saved_states(updated)
                state = updated
                write_result(checkpoint, name, state, perf_counter() - started)
                log(f'Clue {clue} at r{r + 1}c{c + 1}: {result.elapsed_seconds:.2f} seconds; '
                    f'{len(result.accepted_states)} accepted states'
                    + f'; {analysis_timing_summary(result)}'
                    + (' (stopped early)' if result.limit_reached else ''))
            regions = set(determine_regions(state)[0].values())
            complete = all(region.verify(state) for region in regions)
            current_arcs = {(r, c, cell['arc']) for r, row in enumerate(state['cells'])
                            for c, cell in enumerate(row) if cell['arc'] is not None}
            log(f'Pass {passes} complete: {perf_counter() - started:.2f} seconds total')
            if complete or not current_arcs - previous_arcs:
                log('Puzzle verified complete.' if complete else 'Stopped: no new arcs placed in the last pass.')
                if complete:
                    log(f'Answer key: {compute_answer_key(state)["answer"]}')
                    verified = True
                break
    finally:
        if session is not None:
            state = session.state
        elapsed = perf_counter() - started
        write_result(checkpoint, name, state, elapsed)
        if verified:
            write_result(output, name, state, elapsed)
        log(f'Total analysis time: {elapsed:.2f} seconds. Saved: {output if verified else checkpoint}')
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', type=grid_name, help='Puzzle name with a saved initial_state.json')
    parser.add_argument('-greedy', '--greedy', action='store_true',
                        help='Try provisional greedy deductions with cascading normal-search fallback')
    ordering = parser.add_mutually_exclusive_group()
    ordering.add_argument('--set', action='store_true', dest='set_order',
                          help='Use the named order in solution_clue_analysis_order.json')
    ordering.add_argument('--custom-weights', action='store_true',
                          help='Choose dynamic ordering weights in a popup window')
    args = parser.parse_args(argv)
    try:
        state = load_initial_state(args.name)
        order = configured_order(state, args.name) if args.set_order else None
        if args.set_order and order is None:
            raise ValueError(f'No configured set order for puzzle {args.name!r}.')
        weights = prompt_weights() if args.custom_weights else DEFAULT_ANALYSIS_WEIGHTS
        if weights is None:
            print('Analysis cancelled.', flush=True)
            return 0
        print('Using dynamic order.' if order is None else 'Using configured set order.', flush=True)
        solve(state, args.name, SAVED_STATES_DIRECTORY / args.name / 'solved_state.json', order, weights,
              log=lambda message: print(message, flush=True), greedy=args.greedy)
    except KeyboardInterrupt:
        print('\nAnalysis interrupted; completed results preserved.', flush=True)
        return 130
    except (OSError, ValueError, KeyError, TypeError, EOFError) as exc:
        parser.exit(1, f'Error: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
