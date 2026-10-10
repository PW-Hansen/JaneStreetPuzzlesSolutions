"""Shared noninteractive workflow for solving a named puzzle from its initial state."""
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from time import perf_counter
from .constants import INITIAL_STATE_NAME, SOLVED_STATE_NAME
from .model import validate_name
from .placements import attempt_placements
from .folding import folding_trials, configured_anchor
from .fold_application import apply_unique_fold
from .answer_key import compute_answer_key
from .state_export import print_state
from .anchors import select_solver_anchor


@dataclass
class SolveResult:
    status: str
    puzzle: object
    survivors: int
    answer: object = None
    snapshot: object = None
    png: object = None


def load_initial_puzzle(storage, name):
    validate_name(name)
    explicit = storage.root / ('saved_states_' + name) / (INITIAL_STATE_NAME + '.json')
    snapshots = [path for path in storage.snapshots(name) if path.stem == INITIAL_STATE_NAME]
    path = explicit if explicit.exists() else snapshots[0] if snapshots else None
    if path is not None:
        return storage.load(path, name), path
    puzzle = storage.load(storage.working_path(name), name)
    puzzle.cells = deepcopy(puzzle.original)
    puzzle.undo_stack, puzzle.redo_stack = [], []
    puzzle.update_analysis()
    return puzzle, None


def solve_named_puzzle(storage, name, report=print, *, anchor_coordinates=None):
    started = perf_counter()
    puzzle, source = load_initial_puzzle(storage, name)
    report(f'Loaded initial state: {source if source else "original clues from working puzzle"}')
    # Loading performs the shared number, arrow, and region propagation.
    if puzzle.analysis.conflicts:
        raise ValueError('Initial state contradicts the rules: ' + '; '.join(puzzle.analysis.conflicts))
    report(f'Rules applied: {sum(box is True for box in puzzle.analysis.boxes)} box cells; '
           f'{sum(box is None for box in puzzle.analysis.boxes)} unknown cells.')
    report('Running attempt placement analysis...')
    placements = attempt_placements(puzzle.cells, puzzle.rows, puzzle.columns)
    if placements.status != 'stable':
        location = ''
        if placements.failed_cell is not None:
            row, column = divmod(placements.failed_cell, puzzle.columns)
            location = f' at R{row+1}C{column+1}'
        raise ValueError(f'Placement analysis {placements.status}{location}: ' + '; '.join(placements.conflicts))
    puzzle.apply_placements(placements.cells)
    report(f'Placement analysis complete: {placements.forced} forced placements; '
           f'{placements.tested} cells tested in {placements.passes} passes.')
    anchor = select_solver_anchor(puzzle.analysis.boxes, puzzle.rows, puzzle.columns, anchor_coordinates)
    row, column = divmod(anchor, puzzle.columns)
    report(f'Fold anchor: R{row+1}C{column+1}')
    report('Trying region folds and complete surface fillings...')
    survivors = []
    rejected = Counter()
    checked = 0
    for trial in folding_trials(puzzle.analysis.boxes, puzzle.rows, puzzle.columns, anchor, puzzle.cells,
                               use_anchor_region=True):
        checked += 1
        if trial.reason:
            rejected[trial.reason] += 1
        else:
            survivors.append(trial)
    report(f'Fold search complete: {checked} trials; {len(survivors)} surviving folds.')
    if rejected:
        report('Rejected: ' + ', '.join(f'{reason}: {count}' for reason, count in rejected.items()))
    if len(survivors) != 1:
        status = 'no fold' if not survivors else 'multiple folds'
        report(f'No unique answer: {status}. No solved state exported.')
        report(f'Elapsed: {perf_counter()-started:.1f}s')
        return SolveResult(status, puzzle, len(survivors))
    apply_unique_fold(puzzle, survivors)
    answer = compute_answer_key(puzzle)
    report(answer.report())
    snapshot, png = print_state(puzzle, storage, SOLVED_STATE_NAME)
    report(f'Saved {snapshot}\nExported {png}')
    report(f'Elapsed: {perf_counter()-started:.1f}s')
    return SolveResult('solved', puzzle, 1, answer, snapshot, png)
