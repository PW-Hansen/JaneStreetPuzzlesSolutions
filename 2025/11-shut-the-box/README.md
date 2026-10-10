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

Ctrl+Z undoes, and Ctrl+Y or Ctrl+Shift+Z redoes. New edits discard redo history. Reset edits restores the original cell data; Reset shading restores only original shading. Both are undoable and retain the puzzle name, dimensions, and original clues. Working history is cleared on normal close; saved snapshots retain their captured history. Newly created puzzles have blank original clues. Automatic arrow, number, and region deductions are supported as described below; there is no full box solver or candidate preview yet.

Run backend checks with `python -m unittest discover -s tests`. GUI smoke verification is available as `python tests/gui_smoke.py` and writes inspection images under `tests/artifacts/`.




Arrow rules run automatically after edits, resets, undo/redo, and loads. Cell details report **Box: yes** (light green), **no** (light grey), or **unknown** (unshaded), plus the source. Numbered/shape clues are box cells; arrow clues are outside. A short blue dash identifies automatic shading. Your manual shading is stored separately, and deductions are recomputed from it so removing an assumption retracts unsupported results. Shading mode cycles your manual input through unknown/no/yes; clearing removes that manual input even if an automatic deduction remains.

For each arrow clue, every indicated direction must first encounter a box cell at the same minimum distance. Unmarked directions cannot have a box cell at that distance or closer. Propagation tests possible distances and applies only assignments shared by all remaining distances, repeating across clues until stable. Cell details list possible distances for an arrow; the analysis panel reports contradictions. If input is inconsistent, inferred arrow shading is withheld and manual input is preserved. Snapshots and working files store manual edits and clues; deterministic deductions are restored by recomputation. Reset shading clears manual shading back to its original values and then reapplies deductions. Arrow, number, box-connectivity, and non-box boundary-reachability propagation are supported; box-folding constraints remain to be implemented.



Number clues count box cells in the surrounding 3×3 neighborhood, **including the numbered cell itself**; edge and corner clues count only cells inside the grid. When the target count is met, all remaining unknown neighbors become no. When every unknown is needed to reach the target, they become yes. Too many confirmed box cells or too few possible box cells produce a contradiction. Cell details show the current count for a selected number clue. The analysis panel reports arrow and number deductions separately, and blue dashes mark both kinds of automatic shading.

Every edit rebuilds deductions from the current manual input, checking affected number clues (including diagonal neighbors) and propagating consequences across both rule types until stable. Changing or deleting a number, clearing shading, undo/redo, loading, and resets all recompute the same analysis. Contradictory input preserves manual edits and withholds automatic arrow/number deductions. Number propagation does not yet combine overlapping clues algebraically or search speculative assignments.


Region rules require all confirmed box cells to connect orthogonally. The analysis considers both yes and unknown cells as possible paths, with no cells acting as walls. An unknown cell becomes yes only if removing it would separate confirmed box cells, making it unavoidable in any connected completion. This handles lone greens, multi-cell regions, successive bottlenecks, and unknown dead-end pockets. Alternative routes remain unknown; diagonal contact does not connect regions. A single already connected green region does not grow without another region to connect to.

If confirmed box regions cannot connect even through all unknown cells, the analysis reports a contradiction and withholds inferred shading. Region deductions run automatically together with arrow and number rules until stable, retract after input changes, and participate in the same undo/redo operation as the edit. Cell details identify their source as region rules; a blue dash marks their automatic shading. The analysis panel reports the number of region deductions. Exterior reachability also prevents enclosed non-box regions, as described below; box folding remains outside these region rules.

Unknown components that cannot reach any confirmed box cell through yes/unknown cells are automatically marked no, including pockets bounded partly by the grid edge. Pockets with a possible exit remain unknown. Without any confirmed box cell, unknown components remain unknown because the future box location is not established. Clearing a blocking no cell retracts unsupported pocket deductions, including through undo/redo. These exclusions participate in the same combined propagation and contradiction handling as other region deductions.


Every non-box region must reach the grid boundary orthogonally through non-box cells. Unknown cells are considered possible escape routes, and an unknown becomes no only if every route from a confirmed non-box region to the boundary requires it. Separate removed regions may reach different boundary cells; they need not connect inside the grid. Multiple possible escape routes stay unknown. A trapped confirmed non-box region reports a contradiction. An unknown pocket with no possible route to the boundary must instead be box. These deductions are reported as region rules, propagate with the other constraints, and retract through ordinary edits, resets, loads, and undo/redo.
