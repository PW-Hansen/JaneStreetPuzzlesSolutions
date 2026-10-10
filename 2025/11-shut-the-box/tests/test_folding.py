import unittest
from collections import Counter
from functions.folding import (cuboid_surface, initial_placement, surface_step, fold_region,
                               folding_trials, largest_box_region, configured_anchor)


class FoldingTests(unittest.TestCase):
    def test_surface_size_neighbors_and_reversible_transport(self):
        opposite = dict(north='south', south='north', east='west', west='east')
        for dimensions in ((1, 1, 1), (3, 2, 1), (7, 6, 2)):
            surface = set(cuboid_surface(dimensions))
            a, b, c = dimensions
            self.assertEqual(len(surface), 2 * (a*b + b*c + c*a))
            for cell in surface:
                for rotation in range(4):
                    placement = initial_placement(cell, rotation)
                    self.assertEqual(len({surface_step(placement, d, dimensions).cell for d in opposite}), 4)
                    for direction, reverse in opposite.items():
                        neighbor = surface_step(placement, direction, dimensions)
                        self.assertIn(neighbor.cell, surface)
                        self.assertEqual(surface_step(neighbor, reverse, dimensions), placement)

    def test_four_orientations_are_distinct_and_no_mirrors(self):
        cell = next(cuboid_surface((3, 2, 1)))
        frames = [initial_placement(cell, rotation) for rotation in range(4)]
        self.assertEqual(len(set(frames)), 4)
        for frame in frames:
            r, d = frame.right, frame.down
            cross = (r[1]*d[2]-r[2]*d[1], r[2]*d[0]-r[0]*d[2], r[0]*d[1]-r[1]*d[0])
            self.assertEqual(cross, cell.normal)

    def test_unit_face_always_rejects_anchor(self):
        boxes = [None] * 9
        boxes[4] = True
        for cell in cuboid_surface((1, 1, 1)):
            for rotation in range(4):
                trial = fold_region({4}, boxes, 3, 3, 4, (1, 1, 1), cell, rotation)
                self.assertEqual(trial.reason, 'isolated anchor')

    def test_all_same_face_neighbors_nonbox_rejects_anchor(self):
        boxes = [False] * 9
        boxes[4] = True
        cell = next(cuboid_surface((2, 2, 2)))
        trial = fold_region({4}, boxes, 3, 3, 4, (2, 2, 2), cell, 0)
        self.assertEqual(trial.reason, 'isolated anchor')

    def test_known_cube_net_preserves_every_uncut_adjacency(self):
        # Six 2x2 faces: one above, four across, one below.
        blocks = {(0, 1), (1, 0), (1, 1), (1, 2), (1, 3), (2, 1)}
        region = {r * 8 + c for r in range(6) for c in range(8) if (r//2, c//2) in blocks}
        boxes = [index in region for index in range(48)]
        anchor = 2 * 8 + 2
        valid = []
        for cell in cuboid_surface((2, 2, 2)):
            for rotation in range(4):
                trial = fold_region(region, boxes, 6, 8, anchor, (2, 2, 2), cell, rotation)
                if trial.reason is None: valid.append(trial)
        self.assertTrue(valid)
        trial = valid[0]
        self.assertEqual(len(trial.mapping), 24)
        self.assertEqual(len({p.cell for p in trial.mapping.values()}), 24)
        self.assertEqual(set(p.cell for p in trial.mapping.values()), set(cuboid_surface((2, 2, 2))))
        for index, placement in trial.mapping.items():
            from functions.folding import grid_neighbors
            for direction, neighbor in grid_neighbors(index, 6, 8):
                if neighbor in region:
                    self.assertEqual(surface_step(placement, direction, (2, 2, 2)), trial.mapping[neighbor])

    def test_too_long_strip_collides(self):
        boxes = [True] * 10
        cell = next(cuboid_surface((2, 2, 2)))
        reasons = {fold_region(set(range(10)), boxes, 1, 10, 0, (2, 2, 2), cell, rotation).reason
                   for rotation in range(4)}
        self.assertIn('overlap', reasons)
        self.assertNotIn(None, reasons)

    def test_patch_around_box_corner_requires_severing_a_connection(self):
        boxes = [True] * 9
        # A 3x3 patch around the face corner cannot keep all its connections.
        from functions.folding import SurfaceCell
        cell = SurfaceCell((3, 3, 0), (0, 0, -1))
        trial = fold_region(set(range(9)), boxes, 3, 3, 4, (2, 2, 2), cell, 2)
        self.assertIn(trial.reason, ('severed connection', 'overlap'))

    def test_largest_region_and_configuration_are_general(self):
        boxes = [True, True, False, True, False, False, False, True, True, True]
        self.assertEqual(largest_box_region(boxes, 2, 5), {3, 7, 8, 9})
        self.assertEqual(configured_anchor({'fold_anchor': [2, 3]}, None, 2, 5), 7)
        self.assertEqual(configured_anchor({}, 3, 2, 5), 3)
        with self.assertRaises(ValueError): configured_anchor({'fold_anchor': [6, 9]}, None, 2, 5)
        with self.assertRaises(ValueError): list(folding_trials(boxes, 2, 5, 0))

    def test_trials_cover_all_positions_and_four_rotations(self):
        boxes = [True, True, True, True, None, None]
        trials = list(folding_trials(boxes, 2, 3, 0))
        self.assertEqual(len(trials), 4)  # All cube faces share one anchor orbit.
        self.assertEqual({t.dimensions for t in trials}, {(1, 1, 1)})
        counts = Counter(t.anchor for t in trials)
        self.assertEqual(len(counts), 1)
        self.assertTrue(all(any(value > 0 for value in t.anchor.normal) for t in trials))
        self.assertTrue(all(count == 4 for count in counts.values()))
        self.assertEqual({t.rotation for t in trials}, {0, 1, 2, 3})
        self.assertTrue(all(t.reason == 'isolated anchor' for t in trials))


if __name__ == '__main__':
    unittest.main()

class ExtendedFoldingTests(unittest.TestCase):
    def strip_trial(self, boxes, dimensions=(4, 2, 2)):
        from functions.folding import SurfaceCell
        region = largest_box_region(boxes, 1, len(boxes))
        return fold_region(region, boxes, 1, len(boxes), 0, dimensions,
                           SurfaceCell((1, 1, 0), (0, 0, -1)), 2)

    def test_unknown_connector_included_without_changing_input(self):
        from functions.folding import extend_fold
        boxes = [True, True, None, True]
        trial = self.strip_trial(boxes)
        self.assertIsNone(trial.reason)
        result = extend_fold(trial, boxes, 1, 4)
        self.assertIsNone(result.reason)
        self.assertEqual(set(result.mapping), {0, 1, 2, 3})
        self.assertIsNone(boxes[2])
        self.assertEqual(set(trial.mapping), {0, 1})

    def test_nonbox_wall_rejects_disconnected_confirmed_cell(self):
        from functions.folding import extend_fold
        boxes = [True, True, False, True]
        result = extend_fold(self.strip_trial(boxes), boxes, 1, 4)
        self.assertEqual(result.reason, 'cannot include all confirmed box cells')

    def test_connection_that_wraps_and_overlaps_is_rejected(self):
        from functions.folding import extend_fold
        boxes = [True, True] + [None]*7 + [True]
        result = extend_fold(self.strip_trial(boxes, (2, 2, 2)), boxes, 1, 10)
        self.assertIsNotNone(result.reason)

    def test_already_complete_region_keeps_its_mapping(self):
        from functions.folding import extend_fold
        boxes = [True, True, None]
        trial = self.strip_trial(boxes)
        result = extend_fold(trial, boxes, 1, 3)
        self.assertEqual(result.mapping, trial.mapping)

    def test_connector_is_checked_against_number_clues(self):
        from functions.folding import extend_fold
        boxes = [True, True, None, True]
        cells = [dict(digit=None, shape=None, arrows=[], shading=0) for _ in boxes]
        cells[1]['digit'] = '2'
        result = extend_fold(self.strip_trial(boxes), boxes, 1, 4, cells)
        self.assertIsNotNone(result.reason)


class SurfaceCompletionTests(unittest.TestCase):
    def fixture(self):
        blocks = {(0, 1), (1, 0), (1, 1), (1, 2), (1, 3), (2, 1)}
        net = {r*8+c for r in range(6) for c in range(8) if (r//2, c//2) in blocks}
        unknown = {5*8+2, 5*8+3}
        region = net - unknown
        boxes = [True if i in region else None if i in unknown else False for i in range(48)]
        for cell in cuboid_surface((2, 2, 2)):
            trial = fold_region(region, boxes, 6, 8, 18, (2, 2, 2), cell, 0)
            if trial.reason is None:
                return boxes, trial, unknown
        self.fail('No initial cube-net placement')

    def test_adjacent_unknown_pair_fills_missing_surface_strip(self):
        from functions.folding import extend_fold
        boxes, trial, unknown = self.fixture()
        result = extend_fold(trial, boxes, 6, 8, require_full=True)
        self.assertIsNone(result.reason)
        self.assertEqual(len(result.mapping), 24)
        self.assertTrue(unknown <= result.mapping.keys())
        self.assertEqual({p.cell for p in result.mapping.values()}, set(cuboid_surface((2, 2, 2))))
        self.assertTrue(all(boxes[i] is None for i in unknown))

    def test_insufficient_unknown_cells_rejects_completion(self):
        from functions.folding import extend_fold
        boxes, trial, unknown = self.fixture()
        boxes[min(unknown)] = False
        result = extend_fold(trial, boxes, 6, 8, require_full=True)
        self.assertEqual(result.reason, 'cannot fill the box surface')

    def test_complete_assignment_checks_number_contradiction(self):
        from functions.folding import extend_fold
        boxes, trial, unknown = self.fixture()
        cells = [dict(digit=None, shape=None, arrows=[], shading=0) for _ in boxes]
        for i, box in enumerate(boxes):
            cells[i]['shading'] = 2 if box is True else 1 if box is False else 0
        cells[4*8+2]['digit'] = '1'
        result = extend_fold(trial, boxes, 6, 8, cells, require_full=True)
        self.assertEqual(result.reason, 'cannot fill the box surface')

class AnchorSymmetryTests(unittest.TestCase):
    def test_opposite_corners_of_rectangle_are_equivalent(self):
        from functions.folding import SurfaceCell, symmetric_anchor_key
        dims = (7, 6, 2)
        key = lambda center: symmetric_anchor_key(SurfaceCell(center, (0, 0, 1)), dims)
        self.assertEqual(key((1, 11, 4)), key((13, 1, 4)))
        # A reflection on this fixed face is not a proper rotation.
        self.assertNotEqual(key((3, 3, 4)), key((11, 3, 4)))

    def test_square_face_quarter_turn_is_equivalent(self):
        from functions.folding import SurfaceCell, symmetric_anchor_key
        dims = (4, 4, 2)
        self.assertEqual(symmetric_anchor_key(SurfaceCell((1, 3, 4), (0, 0, 1)), dims),
                         symmetric_anchor_key(SurfaceCell((5, 1, 4), (0, 0, 1)), dims))

    def test_distinct_face_sizes_are_not_merged(self):
        from functions.folding import SurfaceCell, symmetric_anchor_key
        dims = (7, 6, 2)
        self.assertNotEqual(symmetric_anchor_key(SurfaceCell((14, 1, 1), (1, 0, 0)), dims),
                            symmetric_anchor_key(SurfaceCell((1, 12, 1), (0, 1, 0)), dims))

    def test_cube_faces_share_orbits(self):
        from functions.folding import symmetric_anchor_key
        self.assertEqual(len({symmetric_anchor_key(cell, (2, 2, 2))
                              for cell in cuboid_surface((2, 2, 2))}), 1)
