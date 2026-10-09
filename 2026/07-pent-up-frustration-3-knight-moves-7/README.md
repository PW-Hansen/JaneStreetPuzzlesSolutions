# Jane Street July 2026 puzzle: ‘Pent-Up’ Frustration 3 / Knight Moves 7 — Python solver

A Python solver and interactive Tkinter editor for [‘Pent-Up’ Frustration 3 / Knight Moves 7](https://www.janestreet.com/puzzles/pent-up-frustration-3-knight-moves-7-index/), Jane Street's July 2026 monthly puzzle.

Disclaimer: This project is practice for AI-assisted software development. The code and documentation were developed with Codex, following instructions and corrections from the author. The “Reflections on this project” section is reserved for the author's own writing.

## Puzzle rules

The 8×8 board is divided into 13 regions: the 12 pentominoes and a 2×2 tetromino. Each square begins as a unit cube. Add one additional cube to exactly one square in each region, creating its tower.

A knight starts at the bottom-left square with score 0. Reconstruct its path until it has visited every tower, without visiting any square twice. A legal move travels 0, 1, and 2 units along the three distinct dimensions; it may pass through towers.

On move N, add N to the score when staying at the same altitude, multiply by N when moving up, and divide by N when moving down. Division is permitted only when the result is an integer.

The knight recorded its score every three moves through visit 18. After that, it recorded scores every K moves, for some larger fixed interval K.

For the answer, fill in the scores of the visited squares. For each unvisited square, sum the scores of its orthogonally adjacent visited squares, then add those neighbor sums together. The solver prints this answer key when it finds a unique solution.

The full puzzle statement is also retained in [docs/rules.md](docs/rules.md).

## Reflections on this project
Going into this specific project, I wanted to experiment with having an AGENTS.md in place, which was supposed to restrict the AI to prevent issues that propped up in prior software solutions to Jane Street puzzles - such as just writing everything in one single files or having mutual imports - and instructed Codex to always consult this file before carrying out a task.

I also created docs/gui_requirements.md to specify what I wanted from the GUI to make development a bit more structured there.

I also initially worked with a ticket system, with the GUI creation being broken into something like a dozen different tickets, but ended up dropping that and instructed Codex to look at gui_requirements.md and build the entire thing in one go, and then manually inspected it afterward to ensure that it worked to my satisfaction. 

The reason for this is that despite only taking a minute or two to implement, individual tickets wound up taking ~5% of my 5h usage on a Plus plan. As such, I judged that the tradeoff for greater attention to one aspect or feature of the GUI and its backend wasn't worth burning through 50% or more of my allotted 5h usage in ~30 minutes. This is especially true since the GUI is just a tool to help me visualize and study the puzzle if I get stumped on how to make progress or speed up the solving time, rather than a significant focus in and of itself.

My suspicion is that instructing Codex to check AGENTS.md before each task is to blame for these higher-than-expected usage costs, rather than the existence of the file in the first place, and that total usage would have been lower, had I merely asked Codex to consult it at the start of the project and then again if I made any changes to it. This is something I intend to test in my next solution of a Jane Street Puzzle.

## Getting started

Requires Python 3.10 or newer with Tkinter and Pillow. Install the dependency, then open the editor:

```sh
python -m pip install -r requirements.txt
python puzzle_gui.py
```

The launcher asks for a puzzle name, row count, and column count. Use eight rows and eight columns for the supplied puzzle. Dimensions are fixed after creation. The launcher also reopens working puzzles and their named snapshots; a new editor window starts in Select mode.

To open or solve the supplied puzzle:

```sh
python puzzle_gui.py puzzle
python solve_puzzle.py "saved states/puzzle/initial_state.json"
```

The solver preserves its input and writes a `solver_result` snapshot and PNG under `saved states/puzzle/`. Load that snapshot in the GUI to inspect the result. You can instead pass a working puzzle name; running `python solve_puzzle.py` without an input uses the sole working puzzle.

Example measured runtimes on this machine:

| Operation | Runtime |
| --- | --- |
| Full solver from `initial_state.json`, including JSON and PNG output | 2.11 seconds |
| Original combination search on a nine-group saved state | 146.9 seconds |
| Ordered combination search on the same state | 0.22–0.23 seconds |

The full solver found interval K = 7 and reached the final tower at visit 54. Timings vary with the machine and retained paths. The combination-search measurements include search setup but exclude GUI scheduling; both searches returned the same one valid combination.

## Editing the grid

The editor opens in selection mode. Use the toolbar or these shortcuts:

| Shortcut | Mode | Action |
| --- | --- | --- |
| Ctrl+0 | Select | Inspect cells without editing them. |
| Ctrl+1 | Score | Enter an integer score in the selected cell. |
| Ctrl+2 | Cell border drawing | Toggle a shared edge between thin and thick. |
| Ctrl+3 | Visit number | Enter an integer visit number in the selected cell. |
| Ctrl+4 | Tower | Toggle a tower using the upper half of a cell or a non-tower using its lower half. |

Activating the current editing mode again returns to Select. Arrow keys move the selection; Escape clears it. In numeric modes, the first digit replaces the previous value and subsequent digits append. Backspace removes the last digit; Delete or right-click clears that mode's value. Signed integers and zero are supported. **Set value** accepts an integer, or an empty field to clear the value. Select and border modes ignore numeric typing, Backspace, and Delete.

Right-clicking a shared edge makes it thin. In Tower mode, right-clicking the upper or lower half clears the corresponding mark; Delete clears the tower designation.

Scores and visit numbers coexist. Normally the score is centered and the visit number is small at the top right. In Visit number mode, the visit number is centered and the score is small at the top left.

A tower has a black bar just below its northern border; a non-tower has a black line near the bottom. Both remain visible in every mode. Only Tower mode shades towers blue, non-towers light grey, and remaining tower candidates light green. The inspector reports tower status as **yes**, **no**, or **unknown**.

Undo: Ctrl+Z. Redo: Ctrl+Y or Ctrl+Shift+Z. Ctrl+S saves immediately.

## Path analysis and deductions

**Generate valid movements** starts from a selected cell with a known score and nonnegative visit number. **Moves ahead** defaults to 3. Results list operation strings, such as `+*/` or `+++`, and their final integer scores after exactly that many moves. Starting at visit N, operands are N+1, N+2, and so on.

Fractional divisions are rejected. Multiplication and division must alternate when additions are ignored: `*+*` and `/+/` are invalid. A confirmed starting tower initializes the previous operation as `*`; a confirmed non-tower initializes it as `/`; unknown status leaves it blank. Addition preserves this restriction. This button checks arithmetic sequences without checking knight paths.

**Continue path** uses the same lookahead and keeps sequences ending at the score of a cell with no visit number. If those sequences identify exactly one target cell, it checks actual knight paths, respecting known scores, previous visits, tower assignments, and region constraints. Equal-altitude moves use planar offsets `(1, 2)`; altitude changes use planar offsets `(0, 2)`.

A unique path is applied. Multiple paths apply only their shared scores, visit numbers, and tower information, with the alternatives retained. Multiple target cells or no valid path leave the grid unchanged.

Retained paths are rechecked after score, visit, tower, and border edits. Impossible alternatives are eliminated. Newly shared deductions are applied even when several paths remain; a single surviving path is applied automatically. The inspector shows remaining alternative counts. If no retained path survives, the GUI reports it without applying a path.

Arithmetic analysis can be aborted with explicitly partial results. Aborting path analysis applies no partial deductions. Completed path results are rejected if the grid changed during analysis. Applied deductions and their initiating edit form one undoable, automatically saved action.

## Combination search

**Find valid combinations** chooses one alternative from every retained path group. It rejects conflicting cell visits or values, incompatible tower states, two towers in a region, and combinations requiring every cell in a region to be a non-tower. A shared endpoint with the same visit, score, and tower state represents one visit and is permitted.

For a continuous path from visit 0, the search also requires that the knight can continue to visit every tower through legal moves without revisiting squares. Separate fragments are checked for compatibility until the intervening visits are known.

The search chooses the group with the fewest remaining compatible alternatives at each step. Cached pairwise checks filter other groups before copying grids. A branch stops immediately if another group has no compatible alternative; full grid and completion checks still determine validity.

Valid combinations are retained together so later edits preserve their compatibility. Shared deductions are applied; a unique combination is applied in full. The result reports the number of combinations. Abort, stale results, and a search with no valid combinations leave the existing state unchanged.

**Visit final tower** requires a continuous path from visit 0, a scored endpoint, and exactly one region whose tower has not been visited. It searches from the highest visit number to that region's confirmed tower or a cell that could be its tower. It respects known information, integer arithmetic, retained combinations, and no revisiting. A unique continuation is applied; multiple continuations are retained with shared deductions applied. Each path stops when the final tower is reached.

## Solving the full puzzle

The command-line solver uses the same backend searches as the GUI:

```sh
python solve_puzzle.py "saved states/puzzle/initial_state.json"
python solve_puzzle.py puzzle --dry-run
```

It starts at the bottom-left score 0 and runs Continue path in three-move segments through visit 18, advancing from each determined checkpoint. Existing checkpoint visits are reused.

After visit 18, it tries a fixed interval K starting at 4. A successful segment advances to the next checkpoint using the same K. Failure restores the visit-18 state and tries K+1. It stops trying intervals when the required visits would exceed the grid's capacity:

```text
maximum K = (rows × columns − 19) // remaining scored cells
```

For the supplied 8×8 grid and five remaining scored cells, the maximum K is 9. Once all scored cells have visit numbers, the solver checks path combinations and searches for the final tower. Unique solutions are applied; multiple solutions retain their alternatives and shared deductions.

`--early-step`, `--early-end`, and `--first-interval` configure the schedule. `--output PATH` selects the result JSON destination; `--png PATH` selects the image destination. Without `--png`, the PNG uses the JSON path with a `.png` extension.

Every run prints total elapsed time, including loading and output generation. `--dry-run` writes neither JSON nor PNG. Ctrl+C stops without saving partial results. A search that finds no solution exits with code 1.

Successful unique solutions also print `Answer key: <value>`, including during dry runs. Multiple remaining solutions report the answer as undetermined rather than calculating it from the shared partial grid.

## Region operations

Thick borders divide the grid into orthogonally connected regions. Each region must have exactly one tower.

Designating a tower immediately marks every other cell in its region as a non-tower. If all but one cell are excluded, the remaining cell becomes a tower. These deductions use the same backend operations for manual edits and analysis, and save and undo together. Contradictions are rejected without partially changing the grid.

Clearing a forced tower also clears the region's explicit exclusions that would immediately force it again. Alternatively, clear an exclusion with a lower-half right-click or use Undo. An exclusion required by a retained tower stays in effect. Changing borders recomputes the deductions. Older saved files migrate automatically.

Backend callers can use `Session.mark_tower(cell)` or `Session.mark_tower(cell, is_tower=False)` without activating Tower mode.

## Saving, exporting, and resetting

Working grids autosave to `grids/<name>.json`. **Save state** writes a named snapshot under `saved states/<name>/`; **Load state** restores a snapshot, including history, selection, display mode, and retained paths. Replacing an existing snapshot asks for confirmation. Opening a new editor window uses Select mode.

Undo/redo history survives saving and reopening. A new edit after Undo clears the redo history.

**Print state** asks for a name and exports a PNG in the project root, plus a matching snapshot. This export preserves the current display layout, mode shading, and selection highlight.

Successful command-line solves write `saved states/<name>/solver_result.json` and a matching PNG by default. Solver PNGs show scores, visit numbers, borders, and tower markings without selection highlights or mode shading. The input file is preserved. Results can be loaded through the GUI.

**Reset visit numbers** clears visits and retained paths while preserving scores, borders, tower markings, dimensions, and the puzzle name. Undo restores the cleared information.

## Code organization and tests

- `puzzle_gui.py`: Tkinter editor and calls into the shared backend.
- `solve_puzzle.py`: command-line arguments, progress reporting, elapsed time, and result output.
- `functions/constants.py`: shared display constants and project paths.
- `functions/state.py`, `regions.py`, `persistence.py`, and `workflow.py`: editing, deductions, history, regions, and save/load workflows.
- `functions/movements.py`, `path_analysis.py`, `path_candidates.py`, `path_combinations.py`, `path_ordering.py`, and `path_completion.py`: arithmetic, knight paths, retained alternatives, compatibility, ordering, and completion checks.
- `functions/final_tower.py`, `solver.py`, and `solver_output.py`: final-tower searches, checkpoint scheduling, and solver output.
- `functions/answer_key.py`: answer-key calculation from unvisited cells' orthogonal visited neighbors.
- `functions/rendering.py`: shared grid drawing, hit testing, and PNG export.
- `tests/`: automated regression and GUI integration tests.
- `grids/` and `saved states/`: working puzzles, snapshots, and solver results.
- `docs/rules.md` and `docs/gui_requirements.md`: puzzle rules and interface requirements.
- `AGENTS.md`: project organization and development rules.

Modules in `functions/` do not import root entry points, and the project import graph must remain free of cycles.

Run the test suite from the project root:

```sh
python -m unittest discover -s tests -v
```

GUI integration tests open temporary Tkinter windows.
