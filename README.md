# Jane Street May 2026 puzzle: Arch Madness — Python solver

A Python solver and interactive Tkinter editor for [Arch Madness](https://www.janestreet.com/puzzles/arch-madness-index/), Jane Street's May 2026 monthly puzzle.

Disclaimer: This project is practice for AI-assisted software development, and except for my occassionally making small adjustments or corrections to a typo or mistake in a prompt, all the code was written by Codex, as was the README except for this line and the "Reflections on this project" section, which I wrote, and the puzzle rules, which was copy-pasted from the link above.

## Puzzle rules

Draw 90-degree arcs in some of the white cells. Arcs may not go in green cells. An arc has radius 1, connecting one corner of a cell to the opposite corner. (A cell may contain at most one arc.)

When finished, the arcs must divide the grid into regions, and those regions must have integer area. (Arcs are not allowed to “dangle” – that is, the two parts of a cell containing an arc must belong to distinct regions.)

For each region, compute the number of “smooth” (continuously differentible) pieces that comprise its perimeter. Multiply that number by the region’s area to get its SCORE.

A cell labeled with a number indicates the score of the region that contains at least half (and possibly all) of that cell.

## Reflections on this project
I worked on this project over two days, and by the time I stopped on the first day I had something that could solve the full puzzle... in about 10 minutes. If it was given a specific order to analyze clues in that I had discovered worked well.

This was entirely too long, and even that only came after I prompted Codex to not consider the full 5 possibilities (4 possible arc orientation + no arc) for cells when analyzing clues (cells with numbers in them), but instead to consider simplified (positive diagonal, negative diagonal, no arc) arcs.

I did not consider a solving time acceptable, so I suggested other ways I thought could potentially speed up the search, but nothing seemed to make things better. Most of my suggestions led to a worse performance. By the second day, one improvement I did was that if there were multiple valid solutions for a clue, low-depth sanity checks should be run on clues next to the solution to see if any of the accepted state for a specific clue would break another clue, in which case the accepted state would be rejected. This did help, but not anywhere near enough. I eventually asked Codex for suggestions, but none of the three suggestions it provided led to a performance increase when applied to the full puzzle.

After that, I spent some time simply playing around with potential arc placements on an empty grid, and realized that a region must have an even number of shared cell borders with the edge of the grid. Using that insight, I instructed Codex to create a greedy search mode so that when a clue was analyzed, it would try to create the largest possible region when it gained one region border, try to disprove that, then move on to the second-largest, and so on.

Furthermore, I had explicitly instructed Codex to allow for the possibility that a region could be created from a single smooth piece, meaning that if it was considering a clue with a value of 25, it would need to entertain the possibility that the clue would be part of a region with an area of 25, but whose perimeter was a single continuously differentible piece. I instructed Codex to also make the greedy search mode require that regions be composed of at least 3 distinct perimeter pieces.

And when I ran that greedy search mode with the previously mentioned order, it solved the puzzle in a bit more than 3 seconds.

After sitting down and thinking further about it, I proved to my own satisfaction that it was impossible to create a region with less than 3 distinct perimeter pieces, after which I moved the that rule from the greedy search to the regular search, which made the solution time plummet massively.

This has been a valuable lesson about thinking very carefully about the problem at hand and trying to determine restrictions, requirements, or rules which are not immediately clear, rather than just handing an AI a task and tell it to get going without proper consideration.

## Getting started

Requires Python with Tkinter and Pillow. Install the dependency, then open the editor:

```sh
python -m pip install -r requirements.txt
python puzzle_gui.py
```

The launcher asks for a puzzle name and grid size. Enter `9` for a square or `8x12` for eight rows and twelve columns. The name identifies the saved grid; reopen it with `python puzzle_gui.py example`. Grid dimensions are fixed after creation.

To open or solve the supplied puzzle:

```sh
python puzzle_gui.py full_puzzle
python solve_puzzle.py full_puzzle
python solve_puzzle.py full_puzzle -greedy
```

The solver requires and preserves `saved states/<name>/initial_state.json`. It defaults to dynamic ordering with weights **0.8, 0.5, 0.75**. Use `--set` for the puzzle's order in `solution_clue_analysis_order.json`, or `--custom-weights` to enter weights in a popup. These flags are mutually exclusive; either works with `-greedy`.

```sh
python solve_puzzle.py full_puzzle --set -greedy
python solve_puzzle.py full_puzzle --custom-weights
```

Approximate runtimes on the author's PC:

| Command | Runtime |
| --- | --- |
| `python solve_puzzle.py full_puzzle` | 8.29 seconds |
| `python solve_puzzle.py full_puzzle --greedy` | 2.89 |
| `python solve_puzzle.py full_puzzle --set` | 2.44 seconds |
| `python solve_puzzle.py full_puzzle --set --greedy` | 1.46 seconds |

Timings vary with the machine and settings, and also varies slightly from run to run.

## Editing the grid

The editor opens in selection mode. Use the toolbar or these shortcuts:

| Shortcut | Mode | Action |
| --- | --- | --- |
| Ctrl+0 | Select | Select cells without changing marks. |
| Ctrl+1 | Green cells | Click to toggle a green cell. |
| Ctrl+2 | Digits | Select a cell and type its clue. |
| Ctrl+3 | Arcs | Click to cycle through four arc orientations, then no arc. |
| Ctrl+4 | Map | Inspect and edit permitted arc configurations. |

Pressing the shortcut for the current editing mode returns to selection mode. Escape clears the selection; arrow keys move it. Backspace edits a clue. Right-click or Delete clears the current mode's mark. Digits and arcs can coexist; making a cell green removes its arc.

Undo: Ctrl+Z. Redo: Ctrl+Y or Ctrl+Shift+Z. Ctrl+S saves the grid.

Map mode shows four arcs and a central no-arc option. Toggle possibilities using the checkboxes or right-clicking the miniatures; at least one must remain. Future searches respect these exclusions and existing marks.

## Clue analysis and deductions

**Factorization** lists possible area × perimeter-piece combinations. **Analyze selected clue** grows its region, rejecting contradictions and area or confirmed perimeter discontinuities incompatible with those factors. Completed candidates require integer area, the correct score, and compatible clues.

Search stops after finding more than 25 accepted states, or when aborted. Completed searches apply a unique state or configurations shared by all states, retaining proven exclusions. Untested cells outside a candidate region remain unrestricted.

The analysis options are:

- **Simplify arcs:** reduce five choices to three in undecided non-clue cells, initially counting them as half a cell. Fixed arcs retain exact area; completed candidates are resolved and checked with actual arcs. Growth beyond the second-highest arithmetic factor area switches back to regular arcs; the three-piece rule independently bounds valid areas.
- **Prioritize cells:** favor constrained frontier cells, with bonuses for neighboring green cells, neighboring clues, the grid edge, and each adjacent cell already in the partial region.
- **Check other clues:** run bounded searches using simplified arcs when another clue becomes sufficiently constrained. Cutoffs do not prove contradictions.

Completed searches with multiple states run sanity checks on neighboring clues, with a separate 2,500-branch limit per check. Cutoffs retain candidates; single-state results skip these checks.

**Scan local conditionals (3 cells)** finds nearby incompatibilities and cascading implications, shown for the selected cell in the right-hand panel. **Wipe local conditionals** removes rules while preserving arcs and exclusions.

Completed searches with fewer than 25 states save their candidates. Blue rings identify clues with multiple saved states. Selecting one loads its candidates at **State 0 — confirmed grid**; Previous/Next previews blue speculative arcs over black confirmed arcs. Incompatible placed arcs invalidate saved candidates.

**Abort analysis** stops the search. Timers remain visible after completion. The console reports clue starts, rejected candidates, and separate main-search and sanity-check timings and branch counts.

## Greedy search

The greedy search assumes **a region has only one uninterrupted connection with the grid edge**. This is not universally true, but is useful, especially for smaller regions. Grid corners do not interrupt that connection.

The three-piece minimum is enforced by both greedy and non-greedy searches, not treated as a greedy assumption. For example, either search rejects a 25-clue region growing beyond area 5.

At the boundary, greedy search tries the longest permitted contact with an even number of unit cell borders, then shorter contacts if needed. It adds whole-cell area for claimed no-arc cells and respects exclusions for terminating arcs, grouping equivalent arcs when simplification is enabled.

**Analyze selected clue (greedy)** previews candidates without committing deductions. The command-line `-greedy` option permits provisional deductions throughout a solve.

If greedy search fails, the solver retries that clue and future clues non-greedily. Further failure restores the state before the latest successful greedy search and retries from there, cascading backward if necessary. Completed grids must pass region and clue verification.

## Analyzing all clues

Both batch buttons start by scanning local conditionals:

- **Analyze all clues (dynamic order)** asks for weights per nearby conditional, grid-edge contact, and adjacent green cell or being green. Defaults are **0.8, 0.5, 0.75**. Multiply the clue value by applicable weights; lower scores go first. Recompute after each analysis.
- **Analyze all clues (set order)** reads the current puzzle's entry in `solution_clue_analysis_order.json`: one-based `row`, `column`, and expected `clue`. The supplied order starts with the edge 9s, beginning at r3c9. Edit this file to change or add orders.

Passes repeat until the grid is complete or a pass places no new arcs. Total time freezes at completion and is printed to the console.

## Region operations

- **Check smooth arcs** colors arcs that join smoothly together, separating non-smooth connections.
- **Determine regions** colors separated regions. A region containing both sides of an arc is left uncolored.
- **Compute region areas** displays exact areas inside the grid. Each region counts whole cells, arc insides of area π/4, and arc outsides of area 1−π/4. Equal inside and outside counts give integer area without floating-point comparisons.
- **Compute scores** displays area × smooth perimeter-piece count.
- **Verify regions** colors valid regions green and invalid regions grey, checking arc separation, integer area, and clue scores.
- **Clear colors** removes analysis colors and labels.

## Saving, exporting, and resetting

Named grids autosave to `grids/<name>.json`. **Save state** creates a named snapshot in `saved states/<name>/`; **Load state** restores a snapshot for that puzzle. Snapshots preserve deductions, saved candidates, and editor state as well as the grid.

**Print state** asks for a name and exports a PNG in the project root, plus a matching saved-state snapshot.

The command-line solver writes progress to `saved states/<name>/checkpoint_state.json`. Only a complete, validated grid is written to `saved states/<name>/solved_state.json`. Both can be loaded through the GUI. Greedy checkpoints may contain provisional deductions.

**Reset arcs** removes arcs and clears learned exclusions, conditionals, and saved analysis candidates while preserving clues and green cells.

## Code organization and tests

- `puzzle_gui.py`: Tkinter editor and interaction with the shared functions.
- `solve_puzzle.py`: command-line solving, ordering, reporting, and checkpoint output.
- `functions/constants.py`: shared constants, default weights, and project paths.
- `solution_clue_analysis_order.json`: named fixed clue orders.
- `functions/`: grid geometry and regions, state handling, rendering, dialogs, searches, deductions, and rollback scheduling. These modules do not import files in the project root.
- `tests/`: automated regression tests.
- `grids/` and `saved states/`: working grids and named snapshots.

Run the test suite from the project root:

```sh
python -m unittest discover -s tests
```
