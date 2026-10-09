"""Exercise the normal entry point with temporary puzzle files and save previews."""

from pathlib import Path
import runpy
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch
from PIL import ImageGrab

from functions.rendering import export_png


def capture(root, path):
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height())).save(path)


def run():
    project = Path(__file__).resolve().parents[1]
    previews = project / "docs" / "previews"
    previews.mkdir(exist_ok=True)
    original = tk.Tk.mainloop
    failures = []
    def mainloop(root, *args, **kwargs):
        def launch():
            try:
                capture(root, previews / "launcher.png")
                launcher = next(iter(root.children.values()))
                launcher.name.set("Visual verification")
                launcher.rows.set("6")
                launcher.columns.set("8")
                launcher.create()
                editor = launcher.editor
                editor.session.select((1, 2))
                editor.change_mode("Score")
                editor.value.set("27")
                editor.apply_value()
                editor.change_mode("Visit number")
                editor.value.set("4")
                editor.apply_value()
                editor.change_mode("Cell border drawing")
                editor.session.toggle_edge([1, 2, 1, 3])
                editor.refresh()
                root.after(500, lambda: finish(root, editor))
            except Exception as error:
                failures.append(error)
                root.destroy()
        root.after(500, launch)
        return original(root, *args, **kwargs)
    def finish(root, editor):
        try:
            capture(root, previews / "score_layout.png")
            editor.change_mode("Visit number")
            root.update()
            capture(root, previews / "visit_layout.png")
            export_png(editor.session, "grid_export")
            editor.flush_save()
        except Exception as error:
            failures.append(error)
        finally:
            root.destroy()
    with tempfile.TemporaryDirectory() as folder:
        with (patch("functions.persistence.GRIDS_DIRECTORY", Path(folder) / "grids"),
              patch("functions.persistence.SNAPSHOTS_DIRECTORY", Path(folder) / "states"),
              patch("functions.rendering.PROJECT_ROOT", previews),
              patch.object(tk.Tk, "mainloop", mainloop), patch.object(sys, "argv", ["puzzle_gui.py"])):
            runpy.run_path(str(project / "puzzle_gui.py"), run_name="__main__")
    if failures:
        raise failures[0]
    print(previews)


if __name__ == "__main__":
    run()
