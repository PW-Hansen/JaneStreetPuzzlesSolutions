"""Shared PNG-and-snapshot export for the GUI and command-line workflow."""
from pathlib import Path

from .model import safe_name, save_snapshot
from .rendering import export_png


def print_state(puzzle, root, state_name, selected=None):
    name = safe_name(state_name)
    root = Path(root)
    snapshot = root / 'saved states' / puzzle.data['name'] / f'{name}.json'
    png = root / f'{name}.png'
    export_png(png, puzzle.data, selected)
    save_snapshot(snapshot, puzzle, selected)
    return snapshot, png
