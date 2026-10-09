from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRIDS_DIRECTORY = PROJECT_ROOT / "grids"
SNAPSHOTS_DIRECTORY = PROJECT_ROOT / "saved states"
CELL_SIZE = 64
PADDING = 10
THICK_WIDTH = 4
MODES = ("Select", "Score", "Cell border drawing", "Visit number", "Tower")
