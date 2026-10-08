"""Shared constants and project paths; independent of the GUI and solver."""
from pathlib import Path

PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]

DEFAULT_STATE = PROJECT_DIRECTORY / "puzzle_state.json"

DATA_DIRECTORY = PROJECT_DIRECTORY / "grids"

SOLUTION_ORDER_PATH = PROJECT_DIRECTORY / 'solution_clue_analysis_order.json'

SAVED_STATES_DIRECTORY = PROJECT_DIRECTORY / 'saved states'

ARC_CYCLE = (None, "tl", "tr", "br", "bl")

MINIMUM_REGION_PIECES = 3

DEFAULT_ANALYSIS_WEIGHTS = (.8, .5, .75)

