import unittest
from collections import defaultdict
from unittest.mock import patch
from functions.dimensions import dimension_triples, possible_dimension_totals


class DimensionTests(unittest.TestCase):
    def test_known_surfaces_and_ordering(self):
        self.assertEqual(dimension_triples(6), ((1, 1, 1),))
        self.assertEqual(dimension_triples(22), ((5, 1, 1), (3, 2, 1)))
        self.assertEqual(dimension_triples(24), ((2, 2, 2),))
        for count in (0, 1, 2, 3, 4, 5, 7):
            self.assertEqual(dimension_triples(count), ())

    def test_even_totals_only_and_unknown_limit(self):
        with patch('functions.dimensions.dimension_triples', wraps=dimension_triples) as calculate:
            totals = list(possible_dimension_totals(19, 5))
            self.assertEqual([row.cells for row in totals], [20, 22, 24])
            self.assertEqual([row.added_unknown for row in totals], [1, 3, 5])
            self.assertEqual([call.args[0] for call in calculate.call_args_list], [20, 22, 24])
        self.assertEqual(list(possible_dimension_totals(19, 0)), [])
        self.assertEqual([row.cells for row in possible_dimension_totals(24, 0)], [24])
        self.assertEqual([row.cells for row in possible_dimension_totals(6, 3)], [6, 8])

    def test_triples_against_independent_brute_force(self):
        expected = defaultdict(set)
        for a in range(1, 61):
            for b in range(1, a + 1):
                for c in range(1, b + 1):
                    area = 2 * (a * b + b * c + c * a)
                    if area <= 240: expected[area].add((a, b, c))
        for area in range(241):
            result = dimension_triples(area)
            self.assertEqual(set(result), expected[area])
            self.assertEqual(len(result), len(set(result)))

    def test_invalid_counts(self):
        for bad in (-1, 2.5, True, '6'):
            with self.assertRaises(ValueError): dimension_triples(bad)
            with self.assertRaises(ValueError): list(possible_dimension_totals(bad, 2))
            with self.assertRaises(ValueError): list(possible_dimension_totals(2, bad))


if __name__ == '__main__':
    unittest.main()
