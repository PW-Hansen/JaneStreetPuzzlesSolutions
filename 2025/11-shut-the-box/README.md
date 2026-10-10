# Puzzle editor

Run `python puzzle_gui.py` for the launcher, then create a named puzzle or open a working puzzle/snapshot. New puzzles default to 20 rows and 20 columns. Run `python puzzle_gui.py <name>` to reopen a named puzzle directly. Cells currently use 35×35 pixels, configured by CELL_SIZE in functions/constants.py. The window fits the full grid and controls, with no grid scrollbars; its minimum size keeps the grid visible. Python with Tkinter and Pillow is required; install Pillow with `python -m pip install -r requirements.txt`. The GUI and PNG exports share antialiased circle, arrow, and digit rendering. Shape bounds use equal integer margins on opposite sides of the cell.

The editor starts in **Select** mode. Ctrl+0 selects this mode; Ctrl+1 through Ctrl+4 activate Digit Entering, Arrow Entering, Circle/Square, and Shading. Activating the current editing mode returns to Select. Arrow keys move selection, and Escape clears it.

| Mode | Left-click / typing | Right-click | Backspace / Delete |
|---|---|---|---|
| Select | Select only; typing has no effect | Select only | No effect |
| Digit Entering | Select, then type 0–9 | Clear digit | Clear digit |
| Arrow Entering | Toggle arrow in clicked diagonal quarter; N/E/S/W toggles directions | Remove clicked arrow | Clear all arrows |
| Circle/Square | Cycle blank, grey circle, grey square; Space also cycles | Clear shape | Clear shape |
| Shading | Cycle blank, light grey, light green; Space also cycles | Clear shading | Clear shading |

Arrows cannot coexist with digits or shapes. Incompatible additions are ignored, preserving existing content. Digits can coexist with shapes and render on top. Shading sits below all content. Blue outlines indicate selection and appear in Print state exports.

Edits autosave to `grids/<name>.json`. Save state writes a separate snapshot to `saved states/<name>/<state>.json`; Load state lists only the current puzzle's snapshots and restores their history. Print state saves the matching snapshot and `<state>.png` in the project root. Existing files require confirmation before replacement. A failed load leaves the current puzzle intact.

Ctrl+Z undoes, and Ctrl+Y or Ctrl+Shift+Z redoes. New edits discard redo history. Reset edits restores the original cell data; Reset shading restores only original shading. Both are undoable and retain the puzzle name, dimensions, and original clues. Working history is cleared on normal close; saved snapshots retain their captured history. Newly created puzzles have blank original clues. Automatic arrow deductions are supported as described below; there is no full box solver or candidate preview yet.

Run backend checks with `python -m unittest discover -s tests`. GUI smoke verification is available as `python tests/gui_smoke.py` and writes inspection images under `tests/artifacts/`.




Arrow rules run automatically after edits, resets, undo/redo, and loads. Cell details report **Box: yes** (light green), **no** (light grey), or **unknown** (unshaded), plus the source. Numbered/shape clues are box cells; arrow clues are outside. A short blue dash identifies automatic shading. Your manual shading is stored separately, and deductions are recomputed from it so removing an assumption retracts unsupported results. Shading mode cycles your manual input through unknown/no/yes; clearing removes that manual input even if an automatic deduction remains.

For each arrow clue, every indicated direction must first encounter a box cell at the same minimum distance. Unmarked directions cannot have a box cell at that distance or closer. Propagation tests possible distances and applies only assignments shared by all remaining distances, repeating across clues until stable. Cell details list possible distances for an arrow; the analysis panel reports contradictions. If input is inconsistent, inferred arrow shading is withheld and manual input is preserved. Snapshots and working files store manual edits and clues; deterministic deductions are restored by recomputation. Reset shading clears manual shading back to its original values and then reapplies deductions. This supports arrow propagation, not the numbered-neighbor, connectivity, or box-folding constraints yet.

