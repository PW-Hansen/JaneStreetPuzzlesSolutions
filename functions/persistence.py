"""Atomic working files and named snapshots."""

import json
import os
import tempfile
from pathlib import Path

from functions.constants import GRIDS_DIRECTORY, SNAPSHOTS_DIRECTORY
from functions.state import Session, valid_name


def write_session(path, session):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(session.serialize(), stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_session(path, name=None):
    try:
        with Path(path).open(encoding="utf-8") as stream:
            session = Session.deserialize(json.load(stream))
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid saved puzzle data.") from error
    if name is not None and session.grid["name"] != name:
        raise ValueError("Saved state belongs to a different puzzle.")
    return session


def working_path(name):
    return GRIDS_DIRECTORY / (valid_name(name) + ".json")


def snapshot_path(puzzle, name):
    return SNAPSHOTS_DIRECTORY / valid_name(puzzle) / (valid_name(name) + ".json")


def puzzles():
    return sorted(path.stem for path in GRIDS_DIRECTORY.glob("*.json"))


def snapshots(name):
    return sorted(path.stem for path in (SNAPSHOTS_DIRECTORY / valid_name(name)).glob("*.json"))
