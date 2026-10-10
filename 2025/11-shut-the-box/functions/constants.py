CELL_SIZE = 35
SHAPE_SIZE_RATIO = 0.65
DIGIT_SIZE_RATIO = 0.6
ANTIALIAS_SCALE = 4
ARROW_COLOR = '#000000'
# Relative to the cell center: slim stems and broad triangular heads.
ARROW_PROFILE = ((-.025, -.025), (.29, -.025), (.29, -.115),
                 (.46, 0), (.29, .115), (.29, .025), (-.025, .025))
DEFAULT_ROWS = 20
DEFAULT_COLUMNS = 20
SNAPSHOT_DIRECTORY = 'saved_states'
LEGACY_SNAPSHOT_DIRECTORY = 'saved states'
INITIAL_STATE_NAME = 'initial_state'
SOLVED_STATE_NAME = 'solved_state'
MODES = ('Select', 'Digit Entering', 'Arrow Entering', 'Circle/Square', 'Shading')
SHADING = ('#ffffff', '#e6e6e6', '#cce8cc')
SHAPE_COLOR = '#a0a0a0'
DIRECTIONS = ('north', 'east', 'south', 'west')
FACE_COLORS = {'+X': '#d98b8b', '-X': '#8bcaca',
               '+Y': '#91bf91', '-Y': '#c591c5',
               '+Z': '#8fadd1', '-Z': '#d6ca8b'}
