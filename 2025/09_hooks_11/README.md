# Jane Street September 2025 puzzle: Hooks 11 — Python solver

A Python solver and interactive Tkinter editor for Jane Street's September 2025 monthly puzzle, Hooks 11.

This project is practice for AI-assisted software development. The code and documentation were developed with Codex, following instructions and corrections from the author. REFLECTIONS.md was written solely by the author.

## Puzzle rules

Partition the 9×9 grid into nested L-shaped hooks, with arm lengths from 9 down to 1. Place nine 9s in one hook, eight 8s in another, and so on. A hook's digit need not equal its arm length.

Filled cells must be orthogonally connected, and every 2×2 region must contain an empty cell. The filled cells must decompose into nine distinct pentomino shapes, treating rotations and reflections as equivalent. Each pentomino's digit sum must be a multiple of five.

An outside clue identifies the first number or pentomino seen along its row or column. The answer is the product of the areas of orthogonally connected empty regions. The full statement is in [docs/rules.md](docs/rules.md).

## Getting started

Requires Python with Tkinter and Pillow. Install the dependency, then open the editor:

```sh
python -m pip install Pillow
python puzzle_gui.py
```

The launcher creates named puzzles or opens working grids and snapshots. New puzzles ask for their name, rows and columns in one dialog; dimensions are fixed after creation. Cells use 60×60 pixels, configured by `CELL_SIZE` in `functions/constants.py`, and larger grids have scrollbars. Hook analysis requires a square grid.

To open or solve the supplied full puzzle:

```sh
python puzzle_gui.py full_puzzle
python solve_puzzle.py full_puzzle
```

The smaller `example` puzzle can also be opened in the editor. The solver requires `saved states/<name>/initial_state.json`. A completed search with exactly one candidate writes `saved states/<name>/solved_state.json` and `solved_state.png` in the project root. Load the snapshot in the editor to inspect it.

## Editing the grid

The editor opens in Select mode. Use the mode buttons or these shortcuts:

| Shortcut | Mode | Action |
| --- | --- | --- |
| Ctrl+0 | Select | Inspect cells without editing. |
| Ctrl+1 | Digit/Letter Entering | Select a cell or outside clue slot and type letters or digits. |
| Ctrl+2 | Border Drawing | Click near an internal edge to toggle a thick black border. |
| Ctrl+3 | Coloring | Choose a color with 1–9, then click cells to apply or toggle it. Key 0 selects no color. |

Activating the current editing mode returns to Select. Arrow keys move selection, including outside clue slots; Escape clears it. Text, borders and colors coexist. Digits are black, letters red, and selection has a blue outline.

In text mode, the first key after selecting replaces the entry; later keys append, up to 12 characters. Clue slots lie above or below columns and beside rows. Right-click/Delete clears the entry; Backspace removes its last character.

In border mode, click within 14 pixels of an edge. Right-click removes that edge; Backspace/Delete clears the selected cell's internal borders. Typing has no effect. In coloring mode, the palette follows a number-pad layout: 7–9 on top, 4–6 in the middle, 1–3 below, and 0 underneath. Right-click/Backspace/Delete clears only the cell color. Select ignores editing input.

Undo: Ctrl+Z. Redo: Ctrl+Y or Ctrl+Shift+Z. New edits clear redo history. Analysis results and their deductions form undoable changes.

## Hook analysis

**Draw hooks** starts with the single in-grid 1-clue, then grows the enclosing square by one row and one column at each step. Each added hook has equal-length arms. Branches are rejected if a hook contains distinct digits or a digit greater than its cell count. Existing colors and manually drawn borders do not constrain the search.

Hook sizes below refer to **cell counts**, not arm lengths:

- **Three-cell hook:** only digit 2 is allowed. Every outside 2-clue must have an unobstructed possible view of this hook; a confirmed filled cell before it blocks the view.
- **Five-cell hook:** its digit must be 3, 4 or 5. Digit 5 is rejected when the hook shares two edges with the singleton, but allowed with one edge or none. A digit already entered outside this hook is unavailable; givens inside it must agree.
- **Outside 3/4/5 clues:** for each candidate digit in the five-cell hook, every matching clue must be able to reach that hook without a confirmed blocker or crossing two or more three-cell-hook cells first. Crossing one potentially empty cell is allowed. Cells beyond the first five-cell-hook cell do not count. A hook with no remaining candidate digit is rejected.

These are targeted hook deductions, rather than a complete check of all puzzle rules. Their allowed-digit configuration is in `functions/constants.py`.

After a complete hook search, borders shared by every layout become **canonical black borders**, visible in Confirmed view. Other candidate borders appear in purple. **Previous/Next** browses layouts; **Confirmed view** hides speculative additions; **Use hooks** adds the preview's borders to the confirmed manual borders.

## Pentomino analysis

In the **Pentominoes** tab, **Draw pentominoes** requires hook results and outside letter clues. It tests every distinct rotation/reflection and position of each required shape on each available hook layout. Repeated letter clues constrain one shared piece: every clue must see that piece before any other filled cell.

Every pentomino cell is filled. Placements and combinations are rejected for overlap, filled 2×2 regions, blocked clue sightlines, or hook counts exceeding their digit quota. Existing digits covered by a piece count once. Each pentomino sum must be divisible by five. Unknown hook digits are assigned consistently from 1 through the grid size, one per hook, respecting the small-hook rules and available space.

All outside numeric clues are checked as well. A wrong filled digit blocks the view unless an earlier available cell could still receive the matching digit. Hook quotas, reserved empty cells, 2×2 restrictions and the current digit assignment constrain that possibility.

Choose **Individual placements** to browse independently valid placements, or **Combinations** for arrangements containing one placement of every required shape. Each combination must work on one hook layout with one shared digit assignment. If several assignments work, the preview shows one supporting assignment.

An exhaustively disproved hook layout is discarded, including cases where individual placements exist but no compatible combination does. Canonical borders are recomputed from the survivors: one layout confirms all its borders; several confirm their intersection. Untested or partially tested layouts are retained. An incomplete original hook search cannot establish canonical borders.

Previews show colored pentomino outlines, black digits, and the matching hook layout. They preserve confirmed entries, colors and borders. **Previous/Next** browses results; **Confirmed view** hides speculative hooks and pentominoes.

### Remaining pentominoes and forced digits

**Draw remaining pentominoes** extends each stored clued combination with exactly three distinct unused shapes. P is excluded from both pentomino searches because it contains a filled 2×2 block. Extensions preserve the original pieces and clue sightlines, and obey the same quota, sum, overlap and visibility checks. If every hook quota is filled, the filled region must also be connected; partial arrangements may connect later.

Choose **Three additional pentominoes** to browse extensions. Rerunning the operation starts from the stored clued combinations, rather than adding three more pieces to an earlier extension. Proven unextendable combinations are discarded. Unsupported hook layouts are also discarded when the original clued search was complete, updating canonical borders.

Before accepting a combination, both analyses check digit completion from the smallest unfinished hook outward. They test legal ways to meet its quota, force cells shared by every legal completion, and reject combinations with no legal completion. They proceed to the next hook only when the current one is completed; otherwise they stop without guessing. Forced digits remain part of the speculative preview.

### Progress, limits and invalidation

Analysis runs incrementally, with progress, elapsed time and **Abort** controls. The final time remains visible. Abort keeps results already found as incomplete; editing, loading, resetting or undo/redo during a search cancels it and discards pending results. Proven rejections can still be applied safely; unproven alternatives are retained.

Limits are configured in `functions/constants.py`:

| Setting | Default |
| --- | ---: |
| `HOOK_NODE_LIMIT` | 200,000 branches |
| `HOOK_CANDIDATE_LIMIT` | 1,000 layouts |
| `PENTOMINO_NODE_LIMIT` | 1,000,000 branches |
| `PENTOMINO_PLACEMENT_LIMIT` | 20,000 placements |
| `PENTOMINO_CANDIDATE_LIMIT` | 1,000 combinations |

Both pentomino searches share these limits. Cancellation, limits and incomplete input searches are labeled incomplete; zero candidates in such a search does not prove impossibility.

Results and preview selections autosave and support undo/redo. Entry edits invalidate hook and pentomino analysis; border edits invalidate pentomino analysis. Rerunning Draw hooks clears pentomino results. Manual colors and borders are preserved when derived information is invalidated.

**Current scope:** the clued analysis places only letter-clued pieces; the remaining analysis adds exactly three. A partial arrangement is not proof that a connected full solution exists. Answer generation performs completion checks but does not independently verify every puzzle rule.

## Answer key

In the **Answer key** tab, **Generate answer key** lists the areas of orthogonally connected empty regions and their product. It uses the displayed grid, including selected previews and forced digits, without committing them. Hook borders and cell colors do not divide empty regions.

The calculation requires each digit n exactly n times, connected filled cells, and no filled 2×2 region. Incomplete or invalid grids report an explanation. Changing the displayed digits clears the previous answer. The solver uses the same calculation after its unique result.

## Solving the full puzzle

```sh
python solve_puzzle.py full_puzzle
```

The solver always loads `saved states/<name>/initial_state.json`; missing or invalid input reports an error. It runs **Draw hooks**, **Draw pentominoes**, then **Draw remaining pentominoes**, using the GUI's shared backend and limits. Operation order and snapshot names are configured in `functions/constants.py`.

A completed search with exactly one candidate saves `solved_state.json`, exports `solved_state.png`, and prints the empty-region areas and answer key. If the result is still a partial grid, it explains why the answer is unavailable. Existing solved outputs are replaced; the initial snapshot and working grid are preserved.

Zero or multiple candidates, or any incomplete search even with one candidate, produce an inconclusive result without changing solved exports or generating an answer. Dependent stages are skipped if no usable input candidates remain. Exit codes are 0 for a completed unique result, 1 for errors, 2 for inconclusive results, and 130 for interruption.

## Saving, exporting, and resetting

Working grids autosave to `grids/<name>.json`. Buttons below the grid provide additional controls:

- **Save state:** save a named snapshot under `saved states/<name>/`.
- **Load state:** restore data, analysis results, preview selection, cell selection and captured undo/redo history. Loading itself adds an undo step.
- **Print state:** save a matching snapshot and `<state>.png` in the project root, including previews and the current selection highlight.
- **Reset edits:** clear all entered text, including outside clues, cell colors, drawn borders and analysis. Preserve the puzzle's name and dimensions. New puzzles start blank; original clues are not stored separately from manual entries.

The GUI asks before replacing snapshots or PNGs. Failed loads leave the current puzzle intact. Resets are undoable; snapshots retain captured history, while normal editor close clears working history.

## Code organization and tests

- `puzzle_gui.py`: Tkinter editor, launcher and dialogs.
- `solve_puzzle.py`: command-line arguments and solver entry point.
- `functions/model.py`: editing, history, validation and persistence.
- `functions/hooks.py` and `pentominoes.py`: hook enumeration, pentomino searches, visibility checks and forced-digit propagation.
- `functions/analysis_workflow.py` and `solver.py`: shared operation application, reporting and command-line workflow.
- `functions/display_state.py`, `rendering.py` and `state_export.py`: preview contents, drawing and snapshot/PNG output.
- `functions/answer_key.py` and `constants.py`: answer calculation and shared configuration.
- `tests/`: backend and GUI behavior tests.
- `docs/`: puzzle rules and GUI requirements.

Modules in `functions/` do not import root entry points. Run the tests from the project root:

```sh
python -m unittest discover -s tests
```
