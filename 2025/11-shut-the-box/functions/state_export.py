"""Save a matching named snapshot and displayed-grid PNG."""
from .rendering import export_png
from .model import validate_name


def print_state(puzzle, storage, state_name):
    validate_name(state_name)
    snapshot = storage.snapshot_path(puzzle.name, state_name)
    png = storage.root / (state_name + '.png')
    export_png(puzzle, png)
    storage.save(puzzle, snapshot)
    return snapshot, png
