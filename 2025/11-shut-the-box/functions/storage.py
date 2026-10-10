"""Atomic JSON persistence for working puzzles and separate snapshots."""
import json
import os
from pathlib import Path
from .model import Puzzle, validate_name


class Storage:
    def __init__(self, root):
        self.root = Path(root)

    def working_path(self, name):
        return self.root / 'grids' / (validate_name(name) + '.json')

    def snapshot_path(self, name, snapshot):
        return self.root / 'saved states' / validate_name(name) / (validate_name(snapshot) + '.json')

    def load(self, path, expected_name=None):
        with Path(path).open(encoding='utf-8') as stream:
            puzzle = Puzzle.from_dict(json.load(stream))
        if expected_name is not None and puzzle.name != expected_name:
            raise ValueError('This state belongs to a different puzzle.')
        return puzzle

    def save(self, puzzle, path=None):
        path = Path(path) if path else self.working_path(puzzle.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.json.tmp')
        try:
            with temporary.open('w', encoding='utf-8') as stream:
                json.dump(puzzle.to_dict(), stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def puzzles(self):
        return sorted((self.root / 'grids').glob('*.json'))

    def snapshots(self, name):
        return sorted((self.root / 'saved states' / validate_name(name)).glob('*.json'))
