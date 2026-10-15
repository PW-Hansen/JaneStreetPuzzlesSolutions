CELL_SIZE = 60
MARGIN = 60
COLORS = ('#ffffff', '#ffd5d5', '#ffe0b2', '#fff3ac', '#ccebc5', '#bde6ee', '#cbd7ff', '#dfc9f0', '#f4c8df', '#d0d0d0')
COLOR_KEYPAD = ((7, 8, 9), (4, 5, 6), (1, 2, 3), (0,))
HOOK_NODE_LIMIT = 200_000
HOOK_CANDIDATE_LIMIT = 1_000
# Hook sizes here are cell counts, rather than arm lengths.
HOOK_ALLOWED_DIGITS = {3: frozenset({2})}
HOOK_ANCHOR_ADJACENT_ALLOWED_DIGITS = {5: frozenset({3, 4})}
MODES = ('Select', 'Digit/Letter Entering', 'Border Drawing', 'Coloring')
