"""Exercise the real Tk window and capture it for visual inspection."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from PIL import ImageGrab
from puzzle_gui import Editor, launcher
from functions.model import Puzzle
from functions.storage import Storage
from functions.rendering import export_png

artifacts = Path(__file__).parent / 'artifacts'
artifacts.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as directory:
    storage = Storage(directory)
    root = tk.Tk()
    root.geometry('+40+40')
    p = Puzzle('Visual check', 20, 20)
    editor = Editor(root, p, storage)
    root.update()
    assert editor.mode.get() == 'Select'
    editor.click(SimpleNamespace(x=18, y=18))
    editor.key(SimpleNamespace(state=0, keysym='5', char='5'))
    assert p.cells[0]['digit'] is None
    editor.set_mode('Digit Entering')
    editor.key(SimpleNamespace(state=0, keysym='5', char='5'))
    assert p.cells[0]['digit'] == '5'
    editor.set_mode('Digit Entering')
    assert editor.mode.get() == 'Select'
    editor.set_mode('Circle/Square')
    editor.click(SimpleNamespace(x=18, y=18))
    editor.set_mode('Shading')
    editor.click(SimpleNamespace(x=18, y=18))
    editor.undo()
    assert p.cells[0]['shading'] == 0
    editor.redo()
    assert p.cells[0]['shading'] == 1
    for index in range(1, 10):
        p.edit(index, 'Digit Entering', digit=str(index))
        p.edit(index, 'Circle/Square')
        if index % 2: p.edit(index, 'Circle/Square')
        p.edit(index, 'Shading')
        if index % 2: p.edit(index, 'Shading')
    for direction in ('north', 'east', 'south', 'west'):
        p.edit(20, 'Arrow Entering', direction=direction)
    p.edit(20, 'Shading')
    p.edit(399, 'Digit Entering', digit='9')
    editor.persist()
    editor.set_mode('Select')
    root.update()
    assert editor.canvas.winfo_width() >= 607
    assert editor.canvas.winfo_height() >= 607
    for child in editor.undo_button.master.winfo_children():
        assert child.winfo_rootx() + child.winfo_width() <= root.winfo_rootx() + root.winfo_width()
    ImageGrab.grab(bbox=(root.winfo_rootx(), root.winfo_rooty(), root.winfo_rootx() + root.winfo_width(), root.winfo_rooty() + root.winfo_height())).save(artifacts / 'gui.png')
    export_png(p, artifacts / 'grid.png')
    storage.save(p, storage.snapshot_path(p.name, 'inspection'))
    editor.close()
    restored = storage.load(storage.working_path(p.name))
    assert restored.cells == p.cells
    assert restored.undo_stack == [] and restored.redo_stack == []
    snapshot = storage.load(storage.snapshot_path(p.name, 'inspection'))
    assert snapshot.undo_stack
    root = tk.Tk()
    launcher(root, storage)
    root.update()
    ImageGrab.grab(bbox=(root.winfo_rootx(), root.winfo_rooty(), root.winfo_rootx() + root.winfo_width(), root.winfo_rooty() + root.winfo_height())).save(artifacts / 'launcher.png')
    root.destroy()
print('GUI interactions, layout, snapshots, reopening, close history, and exports passed.')
