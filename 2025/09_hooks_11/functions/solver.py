"""Run the configured analyses from a named puzzle's initial snapshot."""
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from .constants import INITIAL_STATE_NAME, SOLVED_STATE_NAME, SOLVER_OPERATIONS
from .model import Puzzle, read, safe_name
from .analysis_workflow import create_analysis, apply_analysis, analysis_summary, missing_prerequisite
from .state_export import print_state
from .answer_key import AnswerKey, compute_answer_key


@dataclass
class SolveResult:
    status: str
    puzzle: Puzzle
    stages: list
    snapshot: Path | None
    png: Path | None
    answer: AnswerKey | None = None


def load_initial_puzzle(root, name):
    name = safe_name(name)
    source = Path(root) / 'saved states' / name / f'{INITIAL_STATE_NAME}.json'
    data = read(source)
    if data['name'] != name:
        raise ValueError('The initial state belongs to a different named puzzle.')
    puzzle = Puzzle(name, data['rows'], data['cols'])
    puzzle.data = data
    return puzzle, source


def solve_named_puzzle(root, name, report=print):
    started = perf_counter()
    puzzle, source = load_initial_puzzle(root, name)
    report(f'Loaded initial state: {source}')
    stages = []
    incomplete = False
    for operation in SOLVER_OPERATIONS:
        reason = missing_prerequisite(puzzle, operation)
        if reason:
            report(f'Skipping Draw {operation}: {reason}.')
            stages.append(dict(operation=operation, outcome='skipped', reason=reason))
            continue
        report(f'Running Draw {operation}...')
        search = create_analysis(puzzle, operation)
        stage_started = perf_counter()
        last_report = stage_started
        for _ in search.run():
            now = perf_counter()
            if now-last_report >= 5:
                progress = getattr(search, 'progress', f'Hook size {getattr(search, "size", 1)}')
                report(f'{progress}: {search.nodes:,} branches, {len(search.candidates)} candidates, {now-stage_started:.1f} s')
                last_report = now
        elapsed = perf_counter()-stage_started
        apply_analysis(puzzle, operation, search, elapsed)
        report(analysis_summary(operation, search, elapsed))
        stages.append(dict(operation=operation, outcome=search.outcome,
                           candidates=len(search.candidates), nodes=search.nodes, elapsed=elapsed))
        incomplete |= search.outcome != 'complete'
    candidates = puzzle.data.get('pentomino_analysis', {}).get('extensions', [])
    status = 'complete' if not incomplete and len(candidates) == 1 else 'inconclusive'
    report(f'Pipeline {status}: {len(candidates)} three-pentomino extensions remain.')
    snapshot = png = None
    answer = None
    if status == 'complete':
        snapshot, png = print_state(puzzle, root, SOLVED_STATE_NAME)
        report(f'Saved {snapshot}\nExported {png}')
        try:
            answer = compute_answer_key(puzzle.data)
        except ValueError as exc:
            report(f'Answer key unavailable: {exc}')
        else:
            report(answer.report())
    else:
        reason = 'Search was incomplete.' if incomplete else 'Exactly one candidate is required.'
        report(f'Inconclusive result. {reason} No solved state exported.')
        report('Answer key not generated: result is inconclusive.')
    report(f'Elapsed: {perf_counter()-started:.2f} s')
    return SolveResult(status, puzzle, stages, snapshot, png, answer)
