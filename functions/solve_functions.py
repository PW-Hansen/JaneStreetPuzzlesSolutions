"""Shared solver orchestration and candidate handling for GUI and CLI."""

import threading
from copy import deepcopy
from queue import Empty, Queue
from time import perf_counter

from .display_functions import format_candidates, region_colors
from .equations_functions import analyze_clues, evaluate
from .persistence_functions import make_grid_state, make_saved_state
from .region_functions import (
    attempt_region_completions, canonical_shape, compare_incomplete_regions,
    continue_region_overlays, find_region_overlays, max_region_size, minimum_region_size,
    RegionOperationAborted, _region_work,
)

def overlay_board(state, base, current):
    board = dict(state.get('assumptions', base))
    board.update({cell: current for cell in state['cells']})
    return board


def completed_regions(states, base, current, identical=False):
    if not states:
        return set()
    boards = [overlay_board(state, base, current) for state in states]
    regions = [{number: frozenset(cell for cell,value in board.items() if value == number)
                for number in set(board.values())} for board in boards]
    return {number for number,cells in regions[0].items()
            if len(cells) == number and all(len(other.get(number,())) == number
                and (not identical or other[number] == cells) for other in regions[1:])}


def region_complete_in_all(number, states, base, current):
    """Skip a region when every surviving candidate has its required size."""
    return number in completed_regions(states,base,current)


def included_expressions(expressions, disabled=()):
    size,disabled = len(expressions),set(disabled)
    return [['' if r*size+c in disabled else text for c,text in enumerate(row)]
            for r,row in enumerate(expressions)]


def analyze_grid(expressions, names):
    return analyze_clues([text for row in expressions for text in row if text.strip()],
                         names,max_region_size(len(expressions)))


def candidate_labels(assignments, names):
    result = {}
    for name in names:
        values = {assignment.get(name) for assignment in assignments}
        result[name] = 'Unknown' if None in values else format_candidates(values)
    return result


def elapsed_text(started):
    return f'Time: {perf_counter()-started:.2f} seconds'


def make_overlay_snapshot(states, index, current, base, tested, target, message, labels, palette, elapsed=''):
    return deepcopy({'states':states,'index':index,'highest':current,'base':base,'tested':tested,
                     'target':target,'message':message,'labels':labels,'palette':palette,'elapsed':elapsed})


class BackgroundRegionOperation:
    """Run cancellable work; UI adapters consume progress and a final result."""
    def __init__(self, operation):
        self.started = perf_counter()
        self.cancel = threading.Event()
        self.results = Queue()
        def work():
            _region_work.cancel = self.cancel
            try:
                result = operation(lambda *counts:self.results.put(('progress',counts)))
                self.results.put(('result',result))
            except Exception as error:
                self.results.put(('error',str(error)))
            finally:
                del _region_work.cancel
        self.thread = threading.Thread(target=work,daemon=True)
        self.thread.start()

    def poll(self):
        progress,final = [],None
        try:
            while True:
                kind,data = self.results.get_nowait()
                if kind == 'progress': progress.append(data)
                else:
                    final = (kind,data)
                    break
        except Empty:
            pass
        if final is not None and self.cancel.is_set():
            final = ('error',str(RegionOperationAborted()))
        return progress,final


def is_solution(size, board, clues):
    """Validate clue preservation, exact sizes, connectivity, and containment."""
    if not board or any(board.get(cell) != value for cell, value in clues.items()):
        return False
    largest = max(board.values())
    for number in range(1, largest + 1):
        cells = {cell for cell, value in board.items() if value == number}
        if len(cells) != number or minimum_region_size(size, board, number, cells) != number:
            return False
        if number > 1:
            smaller = canonical_shape({cell for cell, value in board.items() if value == number - 1}, size)
            if not any(canonical_shape(cells - {removed}, size) == smaller for removed in cells):
                return False
    return True


def solve_sequence(state, regions, log=print):
    size = state['size']
    disabled = set(state.get('disabled_cells', []))
    expressions = included_expressions(state['expressions'],disabled)
    started = perf_counter()
    assignments, steps = analyze_grid(expressions,state['variables'])
    if len(assignments) != 1 or any(value is None for value in assignments[0].values()):
        raise ValueError('Analysis must yield one complete variable assignment to run this sequence.')
    variables = assignments[0]
    log(f"Analyze valid values: {dict((name, str(value)) for name, value in variables.items())} "
        f"({perf_counter() - started:.2f}s)")
    base = {r * size + c: int(evaluate(text, variables))
            for r, row in enumerate(expressions) for c, text in enumerate(row) if text.strip()}
    states, current, tested = [], None, 0
    last_elapsed = ''

    for number in regions:
        if region_complete_in_all(number, states, base, current):
            log(f'Region {number}: skipped (complete in all overlays).')
            continue
        log(f'Region {number}: searching...')
        started = perf_counter()
        last_progress = [started]
        def progress(*counts):
            now = perf_counter()
            if now - last_progress[0] >= 10:
                log(f'  Region {number}: progress {counts}; {now - started:.1f}s elapsed.')
                last_progress[0] = now
        if states:
            target, children, count = continue_region_overlays(
                size, base, current, states, progress, region=number)
        else:
            target, base, children, count = find_region_overlays(
                expressions, variables, progress, region=number)
        last_elapsed = elapsed_text(started)
        log(f'Region {number}: {len(children)} candidates; {last_elapsed}.')
        if children:
            current, states, tested = target, children, count
        else:
            log('  No surviving candidates; previous overlays retained, as in the GUI.')
    if not states:
        raise ValueError('No region overlays were found.')

    for label, operation in (
        ('Compare incomplete regions', compare_incomplete_regions),
        ('Attempt region completion', attempt_region_completions),
    ):
        log(f'{label}: running...')
        started = perf_counter()
        last_progress = [started]
        def progress(done, total, valid):
            now = perf_counter()
            if now - last_progress[0] >= 10:
                log(f'  {label}: {done}/{total} candidates checked; {valid} surviving; {now - started:.1f}s elapsed.')
                last_progress[0] = now
        children = operation(size, base, current, states, progress)
        last_elapsed = elapsed_text(started)
        log(f'{label}: {len(children)} candidates; {last_elapsed}.')
        if children:
            states = children
        else:
            log('  No surviving candidates; previous overlays retained, as in the GUI.')

    solutions = [index for index, candidate in enumerate(states)
                 if is_solution(size, overlay_board(candidate, base, current), base)]
    index = solutions[0] if solutions else 0
    board = overlay_board(states[index], base, current)
    snapshot = make_overlay_snapshot(states,index,current,base,tested,str(current),
        f'{len(solutions)} validated solutions among {len(states)} overlay candidates.',
        board,region_colors(size,board),last_elapsed)
    saved = make_grid_state(size, state['expressions'], disabled,
                           {name: str(value) for name, value in variables.items()},
                           str(current), True, assignments, steps)
    saved = make_saved_state(saved, snapshot, [], [], (0, 0),
                             candidate_labels(assignments,variables),
                             'One analytically valid assignment.', '',)
    return saved, len(solutions)
