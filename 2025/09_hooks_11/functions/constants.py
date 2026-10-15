CELL_SIZE = 60
MARGIN = 60
COLORS = ('#ffffff', '#ffd5d5', '#ffe0b2', '#fff3ac', '#ccebc5', '#bde6ee', '#cbd7ff', '#dfc9f0', '#f4c8df', '#d0d0d0')
COLOR_KEYPAD = ((7, 8, 9), (4, 5, 6), (1, 2, 3), (0,))
HOOK_NODE_LIMIT = 200_000
HOOK_CANDIDATE_LIMIT = 1_000
# Hook sizes here are cell counts, rather than arm lengths.
HOOK_ALLOWED_DIGITS = {3: frozenset({2}), 5: frozenset({3, 4, 5})}
HOOK_ANCHOR_ADJACENT_ALLOWED_DIGITS = {5: frozenset({3, 4})}
HOOK_ANCHOR_SINGLE_EDGE_ALLOWED_DIGITS = {5: frozenset({3, 4, 5})}
PENTOMINO_NODE_LIMIT = 1_000_000
PENTOMINO_CANDIDATE_LIMIT = 1_000
PENTOMINO_PLACEMENT_LIMIT = 20_000
PENTOMINO_SUM_MODULUS = 5
PENTOMINO_CELL_COUNT = 5
REMAINING_PENTOMINO_COUNT = 3
EXCLUDED_PENTOMINOES = frozenset({'P'})
PENTOMINO_OUTLINE_COLORS = ('#16734a', '#a04400', '#1b65ad', '#9a2385', '#267d88', '#7944aa',
                           '#b0304a', '#637516', '#9a581c', '#365bae', '#14836c', '#984972')
PENTOMINO_SHAPES = {
    'F': ((0, 1), (0, 2), (1, 0), (1, 1), (2, 1)),
    'I': ((0, 0), (1, 0), (2, 0), (3, 0), (4, 0)),
    'L': ((0, 0), (1, 0), (2, 0), (3, 0), (3, 1)),
    'N': ((0, 0), (1, 0), (1, 1), (2, 1), (3, 1)),
    'P': ((0, 0), (0, 1), (1, 0), (1, 1), (2, 0)),
    'T': ((0, 0), (0, 1), (0, 2), (1, 1), (2, 1)),
    'U': ((0, 0), (0, 2), (1, 0), (1, 1), (1, 2)),
    'V': ((0, 0), (1, 0), (2, 0), (2, 1), (2, 2)),
    'W': ((0, 0), (1, 0), (1, 1), (2, 1), (2, 2)),
    'X': ((0, 1), (1, 0), (1, 1), (1, 2), (2, 1)),
    'Y': ((0, 0), (1, 0), (2, 0), (3, 0), (1, 1)),
    'Z': ((0, 0), (0, 1), (1, 1), (2, 1), (2, 2)),
}
MODES = ('Select', 'Digit/Letter Entering', 'Border Drawing', 'Coloring')
