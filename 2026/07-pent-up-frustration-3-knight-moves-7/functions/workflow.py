"""Shared creation, loading, and export workflows."""

from functions.persistence import read_session, write_session, working_path, snapshot_path
from functions.rendering import export_png
from functions.state import Session, new_grid, valid_name


def create_named(name, rows, columns):
    try:
        rows, columns = int(rows), int(columns)
    except ValueError:
        raise ValueError("Rows and columns must be positive integers.") from None
    session = Session(new_grid(name, rows, columns))
    path = working_path(session.grid["name"])
    if path.exists():
        raise ValueError("That puzzle already exists. Open it instead or choose a new name.")
    write_session(path, session)
    return session


def open_named(name, snapshot=None):
    name = valid_name(name)
    path = snapshot_path(name, snapshot) if snapshot else working_path(name)
    session = read_session(path, name)
    session.mode = "Select"
    if snapshot:
        write_session(working_path(name), session)
    return session


def autosave(session):
    write_session(working_path(session.grid["name"]), session)


def save_snapshot(session, name):
    path = snapshot_path(session.grid["name"], name)
    write_session(path, session)
    return path


def load_snapshot(session, name):
    restored = read_session(snapshot_path(session.grid["name"], name), session.grid["name"])
    autosave(restored)
    return restored


def print_state(session, name):
    image_path = export_png(session, name)
    snapshot = save_snapshot(session, name)
    return image_path, snapshot
