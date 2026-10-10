"""Shared completion action for fold searches."""


def apply_unique_fold(puzzle, survivors, complete=True):
    if not complete or len(survivors) != 1:
        return False
    return puzzle.apply_fold(survivors[0])
