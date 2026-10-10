import json
import tempfile
import unittest
from pathlib import Path
from functions.model import Puzzle, click_direction
from functions.storage import Storage
from functions.rendering import export_png, scene
from functions.constants import CELL_SIZE, SHAPE_COLOR


class PuzzleTests(unittest.TestCase):
    def test_compatibility_and_layer_independence(self):
        p = Puzzle('test', 2, 2)
        p.edit(0, 'Digit Entering', digit='7')
        p.edit(0, 'Circle/Square')
        p.edit(0, 'Shading')
        self.assertFalse(p.edit(0, 'Arrow Entering', direction='north'))
        self.assertEqual(p.cells[0], dict(digit='7', arrows=[], shape='circle', shading=1))
        p.edit(0, 'Circle/Square', action='clear')
        self.assertEqual(p.cells[0]['digit'], '7')
        p.edit(0, 'Digit Entering', action='clear')
        for direction in ('north', 'east', 'south', 'west'):
            p.edit(0, 'Arrow Entering', direction=direction)
        self.assertEqual(len(p.cells[0]['arrows']), 4)
        self.assertFalse(p.edit(0, 'Circle/Square'))
        self.assertFalse(p.edit(0, 'Digit Entering', digit='8'))
        p.edit(0, 'Arrow Entering', action='right', direction='north')
        self.assertEqual(len(p.cells[0]['arrows']), 3)
        self.assertEqual(p.cells[0]['shading'], 1)

    def test_select_and_history(self):
        p = Puzzle('test', 1, 1)
        self.assertFalse(p.edit(0, 'Select', digit='4'))
        p.edit(0, 'Digit Entering', digit='4')
        p.edit(0, 'Shading')
        p.undo()
        self.assertEqual(p.cells[0]['digit'], '4')
        self.assertEqual(p.cells[0]['shading'], 0)
        p.redo()
        self.assertEqual(p.cells[0]['shading'], 1)
        p.undo()
        p.edit(0, 'Circle/Square')
        self.assertFalse(p.redo())
        p.reset()
        p.undo()
        self.assertEqual(p.cells[0]['shape'], 'circle')

    def test_persistence_and_snapshot_history(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            storage = Storage(directory)
            p = Puzzle('test', 20, 20)
            p.edit(37, 'Digit Entering', digit='0')
            p.selected = 37
            storage.save(p)
            snapshot = storage.snapshot_path(p.name, 'first')
            storage.save(p, snapshot)
            p.edit(37, 'Shading')
            storage.save(p)
            loaded = storage.load(snapshot, 'test')
            self.assertEqual(loaded.cells[37]['shading'], 0)
            self.assertEqual(loaded.selected, 37)
            loaded.undo()
            self.assertIsNone(loaded.cells[37]['digit'])
            loaded.redo()
            self.assertEqual(loaded.cells[37]['digit'], '0')
            self.assertEqual(storage.load(storage.working_path('test')).cells[37]['shading'], 1)
            png = Path(directory) / 'grid.png'
            export_png(loaded, png)
            from PIL import Image
            with Image.open(png) as image:
                self.assertEqual(image.size, (20 * CELL_SIZE + 7, 20 * CELL_SIZE + 7))

    def test_invalid_load_and_names(self):
        p = Puzzle('test', 1, 1)
        data = p.to_dict()
        data['cells'][0]['arrows'] = ['north']
        data['cells'][0]['digit'] = '5'
        with self.assertRaises(ValueError): Puzzle.from_dict(data)
        with self.assertRaises(ValueError): Puzzle('../bad', 1, 1)
        with self.assertRaises(ValueError): Puzzle('CON', 1, 1)
        with self.assertRaises(ValueError): Puzzle('test', 0, 20)

    def test_diagonal_quarters(self):
        for point, direction in [((15, 2), 'north'), ((28, 15), 'east'), ((15, 28), 'south'), ((2, 15), 'west')]:
            self.assertEqual(click_direction(*point, 30), direction)

    def test_shape_bounds_have_equal_integer_margins(self):
        p = Puzzle('test', 1, 1)
        for shape in ('circle', 'square'):
            p.cells[0]['shape'] = shape
            for size in (30, 35, 36, 41):
                item = next(item for item in scene(p, size) if item[2] == SHAPE_COLOR)
                x1, y1, x2, y2 = item[1]
                self.assertTrue(all(value == int(value) for value in item[1]))
                self.assertEqual(x1 - 3, 3 + size - x2)
                self.assertEqual(y1 - 3, 3 + size - y2)


if __name__ == '__main__':
    unittest.main()
