# Jane Street November 2025 puzzle: Shut the Box — Python solver

A Python solver, interactive Tkinter editor, and 3D fold viewer for Jane Street's November 2025 monthly puzzle, Shut the Box.

This project is practice for AI-assisted software development. The code and documentation were developed with Codex, following instructions and corrections from the author. REFLECTIONS.md was written solely by the author.

## Puzzle rules

Cut away orthogonally connected groups of cells, each touching the grid boundary. The remaining cells must be connected, contain no holes, and fold into the six faces of a rectangular box without overlaps.

Arrow cells are outside the box and point toward the nearest box cells in their row or column. Numbered cells are in-box; their numbers count box cells in the centered 3×3 neighborhood, including themselves. Each grey circle must face another circle directly opposite it; each grey square must have an orthogonally adjacent square on the same face.

The answer is the product of the six face sums of numbered cells. The full statement is in [docs/rules.md](docs/rules.md).

## Getting started

Requires Python with Tkinter and Pillow. Install the dependency, then open the editor:

```sh
python -m pip install -r requirements.txt
python puzzle_gui.py
```

The launcher creates named puzzles or opens working grids and snapshots. New puzzles default to 20 rows and 20 columns; dimensions are fixed after creation. Cells use 35×35 pixels, configured by `CELL_SIZE` in `functions/constants.py`, and the window fits the grid without scrollbars.

To open, inspect, or solve the supplied puzzle:

```sh
python puzzle_gui.py puzzle
python gui_puzzle_3d.py puzzle
python solve_puzzle.py puzzle
python solve_puzzle.py puzzle 5 6
```

The solver requires `saved_states/<name>/initial_state.json`. It preserves this input and the working grid, and writes a unique result to `saved_states/<name>/solved_state.json` and `solved_state.png` in the project root. Load the snapshot in the editor to inspect the result.

## Editing the grid

The editor opens in Select mode. Use the mode buttons or these shortcuts:

| Shortcut | Mode | Action |
| --- | --- | --- |
| Ctrl+0 | Select | Inspect cells without editing. |
| Ctrl+1 | Digit Entering | Select a cell and type 0–9. |
| Ctrl+2 | Arrow Entering | Click a directional quarter, or type N/E/S/W, to toggle an arrow. |
| Ctrl+3 | Circle/Square | Click or press Space to cycle blank, circle, and square. |
| Ctrl+4 | Shading | Click or press Space to cycle unknown, out-box, and in-box. |

Activating the current editing mode returns to Select. Arrow keys move selection; Escape clears it. Right-click clears the current mark, or removes the clicked arrow. Backspace/Delete clears the current mode's content; Select ignores editing input.

Digits and shapes can coexist; arrows cannot coexist with either. Incompatible additions are ignored. The inspector reports box status as **yes**, **no**, or **unknown**, plus clue counts, possible arrow distances, and deduction sources. In-box cells are initially light green, out-box cells light grey, and unknowns unshaded. Blue dashes identify automatic shading; blue outlines mark selection.

Undo: Ctrl+Z. Redo: Ctrl+Y or Ctrl+Shift+Z. New edits clear redo history.

## Rules and placement analysis

Arrow, number, and region deductions run automatically after edits, loads, resets, and undo/redo, repeating until stable. They recompute from manual input, so removing an assumption retracts unsupported deductions. Contradictions preserve manual input and withhold inferred shading.

- **Arrows:** marked directions must first encounter box cells at the same minimum distance. Unmarked directions cannot contain box cells that close. Assignments shared by all possible distances are inferred.
- **Numbers:** count the centered 3×3 neighborhood, including the clue cell. A satisfied count excludes remaining unknowns; if every unknown is needed, all become in-box.
- **Connectivity:** unknown bottlenecks needed to join confirmed box regions become in-box. Unknown components unable to reach any confirmed box cell become out-box. Diagonal contact does not connect regions.
- **Exterior reachability:** every out-box region must reach the grid edge orthogonally. Necessary unknown escape cells become out-box; unknown pockets unable to reach the boundary become in-box.

**Attempt placements** tests each unknown as in-box and out-box, applying these rules to both branches. One consistent branch is committed; two leave the cell unknown; neither stops analysis and identifies the failing cell. Passes repeat until one makes no changes.

The sidebar shows progress and elapsed time. **Abort** retains earlier forced placements without committing a speculative branch. Editing and persistence controls are blocked during analysis. One run's committed placements form one undoable, autosaved action.

## Box dimensions and folds

**Determine valid box dimensions** enumerates positive integer triples `a >= b >= c` for possible box-cell totals, from the confirmed count through confirmed plus unknown. Odd totals are skipped:

```text
2 * (a*b + b*c + c*a) = total
```

This read-only calculation checks surface area rather than folding.

**Try region folds** starts with the largest confirmed region, testing candidate dimensions, positive-face anchor positions, and four orientations. Rotationally equivalent positions share a representative; reflections remain distinct. Box edges force folds, and grid adjacencies must remain uncut. Overlaps, inconsistent adjacencies, and anchors with no possible same-face grid neighbor are rejected; a 1×1 anchor face always fails.

Survivors must include every confirmed box cell and fill every surface square using connected groups of unknown cells. Alternative connections are tried, and complete assignments are checked against the automatic rules. The results dialog lists dimensions, anchor positions, and rotations; **View cell mapping** shows the grid-to-surface mapping.

The GUI anchor comes from `"fold_anchor": [row, column]` in `configs/<name>.json`, or the selected cell if absent. Coordinates are one-based, and the anchor must lie in the largest confirmed region. The supplied configuration uses R6C9.

A completed search with exactly one survivor applies all box statuses and face labels as one undoable, autosaved change. Zero, multiple, or aborted results leave the grid unchanged.

**Current limitation:** circle-opposite-circle and same-face square-pairing rules are not checked. Surviving folds are not yet fully verified puzzle solutions.

## 3D viewer and answer key

Run `python gui_puzzle_3d.py` to choose a puzzle, or supply its name. It uses the same fold search and GUI anchor rules.

Drag to rotate and use the mouse wheel to zoom. **Previous/Next fold** switches candidates; face buttons give straight-on views. **Separate faces** spreads the faces apart. Click a cell to inspect its grid coordinates and clue; **Grid coordinates** replaces clue labels with row/column labels. **Reset view** restores the camera and face spacing.

Faces use muted colors: +X red, -X cyan, +Y green, -Y magenta, +Z blue, and -Z yellow. A white outline marks the anchor. Applied face colors also appear in the editor and PNG exports. Grid edits clear face labels to avoid stale colors; selection alone does not.

A completed unique result is applied and saved unless the saved grid changed during search. The viewer loads once; reopen after edits, and reload an already open editor to see changes saved by the viewer.

**Compute answer key** in either GUI shows each face's number sum and their product. It requires an applied fold with all six face assignments, no unknown cells, and no contradictions. A face without numbers has sum zero.

## Solving the full puzzle

```sh
python solve_puzzle.py puzzle
python solve_puzzle.py puzzle 5 6
```

The solver always loads `saved_states/<name>/initial_state.json`; missing or invalid input reports an error. It applies automatic rules, runs Attempt placements to stability, then searches folds and complete surface fillings.

Optional row and column arguments select a one-based anchor, which must be confirmed in-box after placement analysis. Without them, the solver ranks confirmed box cells by centered 3×3 box count, then centered 5×5 count, then earliest row-major index. Counts include the center, clip at grid edges, and exclude unknowns. The chosen anchor is printed and its connected region is folded first. CLI selection is independent of GUI anchor configuration.

A unique result prints the six face sums and answer key, then uses the shared Print state function to save `solved_state.json` and `solved_state.png`. Existing outputs with those names are replaced. Zero or multiple survivors produce no solved export. Exit codes are 0 for a unique result, 1 for errors, 2 for unresolved results, and 130 for interruption.

## Saving, exporting, and resetting

Working grids autosave to `grids/<name>.json`. Buttons below the grid provide additional controls:

- **Save state:** save a named snapshot under `saved_states/<name>/`.
- **Load state:** restore the grid, face labels, selection, and undo/redo history. Older `saved states` folders are also recognized; `saved_states` takes precedence for duplicate names.
- **Print state:** save a matching snapshot and `<state>.png` in the project root, including the current selection highlight.
- **Reset edits:** restore original cell data while preserving the puzzle's identity and dimensions.
- **Reset shading:** restore original shading and clear face labels, then recompute deductions.

The GUI asks before replacing existing snapshots or PNGs. Failed loads leave the current grid intact. Resets are undoable; snapshots retain captured history, while normal editor close clears working history.

## Code organization and tests

- `puzzle_gui.py`: Tkinter editor, launcher, and dialogs.
- `gui_puzzle_3d.py`: interactive fold viewer.
- `solve_puzzle.py`: command-line arguments and solver entry point.
- `functions/model.py` and `storage.py`: editing, history, validation, and persistence.
- `functions/analysis.py`, `arrows.py`, `numbers.py`, `regions.py`, and `placements.py`: shared deductions and placement analysis.
- `functions/dimensions.py`, `folding.py`, `anchors.py`, and `fold_application.py`: dimension enumeration, folds, anchor selection, and applying unique results.
- `functions/solver.py`, `answer_key.py`, and `state_export.py`: shared solver workflow, answer calculation, and snapshot/PNG output.
- `functions/rendering.py`, `view3d.py`, and `constants.py`: drawing, 3D projection, and shared constants.
- `tests/`: automated backend tests.
- `docs/`: puzzle rules and GUI requirements.

Modules in `functions/` do not import root entry points. Run the tests from the project root:

```sh
python -m unittest discover -s tests
```
