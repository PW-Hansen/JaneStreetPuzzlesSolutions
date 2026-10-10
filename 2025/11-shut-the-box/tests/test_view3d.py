import unittest
from math import pi
from functions.folding import FoldTrial, cuboid_surface, initial_placement
from functions.view3d import project_fold, pick_cell, rotate, world_point


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.dimensions = (3, 2, 1)
        surface = next(cuboid_surface(self.dimensions))
        self.trial = FoldTrial(self.dimensions, surface, 0, None,
                               {0: initial_placement(surface, 0)})

    def test_axis_views_show_correct_faces(self):
        for yaw, pitch, normal, count in (
            (0, 0, (0, 0, 1), 6), (pi, 0, (0, 0, -1), 6),
            (-pi/2, 0, (1, 0, 0), 2), (0, pi/2, (0, 1, 0), 3)):
            projected, _, _ = project_fold(self.trial, 800, 600, yaw, pitch)
            self.assertEqual(len(projected), count)
            self.assertEqual({p.surface.normal for p in projected}, {normal})

    def test_fit_and_pick_each_visible_cell(self):
        projected, _, _ = project_fold(self.trial, 800, 600, -.55, .45)
        for cell in projected:
            self.assertEqual(pick_cell(projected, cell.center).surface, cell.surface)
            for x, y in cell.polygon:
                self.assertTrue(29.99 <= x <= 770.01)
                self.assertTrue(29.99 <= y <= 570.01)
        self.assertIsNone(pick_cell(projected, (0, 0)))

    def test_mapping_survives_projection(self):
        normal = self.trial.anchor.normal
        yaw = pi/2 if normal == (-1, 0, 0) else -pi/2
        projected, _, _ = project_fold(self.trial, 800, 600, yaw, 0)
        mapped = [p for p in projected if p.index == 0]
        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0].placement, self.trial.mapping[0])

    def test_separation_moves_faces_along_their_normals(self):
        for cell in cuboid_surface(self.dimensions):
            placement = initial_placement(cell, 0)
            base = world_point(cell, self.dimensions, 0, placement.right, placement.down)
            shifted = world_point(cell, self.dimensions, 2, placement.right, placement.down)
            self.assertEqual(tuple(b-a for a, b in zip(base, shifted)),
                             tuple(2*n for n in cell.normal))

    def test_rotation_preserves_lengths(self):
        point = (2, -3, 4)
        rotated = rotate(point, .7, -.4)
        self.assertAlmostEqual(sum(v*v for v in rotated), sum(v*v for v in point))
