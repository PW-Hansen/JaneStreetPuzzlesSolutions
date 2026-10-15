"""Shared construction, application and reporting of analysis operations."""
from copy import deepcopy

from .hooks import HookSearch
from .pentominoes import PentominoSearch, RemainingPentominoSearch


def create_analysis(puzzle, operation):
    constructors = {'hooks':HookSearch, 'pentominoes':PentominoSearch,
                    'remaining pentominoes':RemainingPentominoSearch}
    return constructors[operation](deepcopy(puzzle.data))


def apply_analysis(puzzle, operation, search, elapsed):
    handlers = {'hooks':puzzle.set_hook_analysis, 'pentominoes':puzzle.set_pentomino_analysis,
                'remaining pentominoes':puzzle.set_remaining_pentomino_analysis}
    handlers[operation](search, elapsed)


def analysis_summary(operation, search, elapsed):
    return (f'{operation.capitalize()} search {search.outcome}: '
            f'{len(search.candidates)} candidates, {search.nodes} branches, {elapsed:.2f} s')


def missing_prerequisite(puzzle, operation):
    if operation != 'hooks' and not puzzle.data.get('analysis', {}).get('candidates'):
        return 'no hook layouts remain'
    if operation == 'remaining pentominoes' and not puzzle.data.get('pentomino_analysis', {}).get('candidates'):
        return 'no compatible pentomino combinations remain'
    return None
