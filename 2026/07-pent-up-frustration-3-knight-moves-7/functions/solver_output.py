"""Write solver state and a matching PNG using the shared exporter."""

from copy import copy
from pathlib import Path

from functions.persistence import write_session
from functions.rendering import export_png


def save_solver_result(session, output, png=None):
    output = Path(output)
    png = Path(png) if png is not None else output.with_suffix(".png")
    if output.resolve() == png.resolve():
        raise ValueError("JSON and PNG outputs must use different paths.")
    write_session(output, session)
    printed = copy(session)
    printed.mode = "Select"
    printed.selected = None
    export_png(printed, output.stem, path=png)
    return output, png
