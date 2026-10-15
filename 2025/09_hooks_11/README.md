# Puzzle editor

Requires Python with Tkinter and Pillow (`pip install Pillow`). Run
`python puzzle_gui.py` for the create/open launcher, or
`python puzzle_gui.py "Puzzle name"` to resume an existing named puzzle.
New puzzles ask for a name, rows and columns in one dialog. Cells are 60 pixels;
larger grids have scrollbars.

Modes and shortcuts:

- **Select (Ctrl+0)**: inspect without editing. Arrow keys move selection,
  including outside clue slots; Escape clears selection.
- **Digit/Letter Entering (Ctrl+1)**: click inside a cell or in the margin
  above/below a column or beside a row. Type up to 12 letters or digits.
  The first key after selecting replaces the entry; following keys append.
  Digits/numbers are black; letters are red. Right-click or Delete clears the entry;
  Backspace removes its last character.
- **Border Drawing (Ctrl+2)**: click within 14 pixels of an internal edge
  to toggle a thick black border. Right-click removes that border.
  Delete/Backspace clears the selected cell's internal borders. Typing has
  no effect.
- **Coloring (Ctrl+3)**: select one of nine colors with keys 1–9 or the
  number-pad palette (7–9 on top, 4–6 in the middle, 1–3 below).
  Click to apply; clicking the same color clears it. Key 0 selects
  no color. Right-click/Delete/Backspace clears only the cell color.

Activating the current editing mode returns to Select. Text, colors and
borders coexist. Ctrl+Z undoes; Ctrl+Y or Ctrl+Shift+Z redoes. A new edit
clears redo. Loading a snapshot and resetting edits can also be undone.
History is cleared on closing. Explicit snapshots retain their saved history
and selection; loading a snapshot restores them and adds an undo step for
the load itself.

Edits automatically save under `grids/<name>.json`. Save state creates a
separate JSON snapshot under `saved states/<name>/`; Load state opens a
snapshot from that puzzle's folder. Print state asks for a name, exports
the displayed grid (including its selection) to `<state name>.png` in the
project root, and saves a matching snapshot. Existing names require an
overwrite confirmation. Failed loads leave the current puzzle intact.

Reset edits clears all manually entered text (including outside entries),
colors and drawn internal borders, preserving the puzzle's name and
dimensions. No original clues are supplied by this project; a newly
created puzzle is blank.

**Draw hooks** starts at the single in-grid 1-clue and grows the enclosing
square by one row and one column at each step. Each new L-shaped hook has
equal-length arms. Branches containing two distinct numbers in one hook
are rejected, as are hooks containing a number greater than their cell
count. Repeated copies of the same number are allowed; the number need
not equal the hook's arm length. Outside 2-clues must be able to see the
three-cell hook along their row or column: a confirmed filled cell before
that hook blocks the view. Blank cells may stay empty to allow the view.
Every outside 2-clue must pass this check. Outside 3/4/5 clues additionally
constrain the five-cell hook as described below. Other outside digit clues,
letters, colors and existing manual borders do not constrain this search.
Other puzzle rules (digit
counts, connectivity, empty 2×2 regions, pentominoes and outside visibility)
are not checked by this operation.

The three-cell hook only permits digit 2. The five-cell hook permits only
3 or 4 when it shares two edges with the singleton 1-hook. It also permits
5 when it shares exactly one edge, or when the three-cell hook entirely
separates it from the singleton.
For each proposed five-cell hook, digits already entered elsewhere in the
grid are unavailable. Givens inside the hook must agree with its candidate
digit. Reject the hook if none of 3, 4 or 5 remains possible. For a candidate
digit with outside clues, every matching clue must be able to reach this
hook before a confirmed filled cell, without passing through two or more
cells of the three-cell hook first (only one of those three cells can be
empty). Passing through one potentially empty cell is allowed; cells past
the first five-cell-hook cell do not count. These checks filter each
candidate digit separately, rather than requiring the hook to satisfy
outside clues for digits assigned to other hooks.
These checks restrict entered digits without filling empty cells. The
allowed-digit rules by cell count are in `functions/constants.py`.

After a complete search, borders shared by every layout automatically
become canonical black borders, visible even in Confirmed view. Cancelled
or limited searches (and searches with no layouts) establish no canonical
borders. These deductions are saved with analysis, undone with the search,
and invalidated when entries change, preserving manually drawn borders.

Other result borders appear in purple as speculative borders. **Previous/Next** browse
layouts, **Confirmed view** hides the preview, and **Use hooks** adds the
preview borders to confirmed black borders while preserving manual
markings. Analysis and committing a layout can be undone and redone.
Results, preview selection and elapsed time are saved with the puzzle and
snapshots. Changing entries invalidates analysis; undo restores it.
Reset edits also clears analysis. Editing, loading, undoing or resetting
during a search cancels it and discards pending results.

**Abort** stops a search and keeps any layouts already found as incomplete
results. The final elapsed time remains visible. Search is bounded by
`HOOK_NODE_LIMIT` and `HOOK_CANDIDATE_LIMIT` in `functions/constants.py`
(200,000 branches and 1,000 layouts by default). Cancellation and limits
are labeled incomplete; zero layouts in an incomplete search does not
establish that no layout exists. The grid must be square and contain
exactly one in-grid numeric 1-clue.

In the **Pentominoes** analysis tab, **Draw pentominoes** requires results
from Draw hooks and at least one outside letter clue. It tests all distinct
rotations/reflections and grid positions of each named shape, separately
for every available hook layout. Repeated clues for a letter constrain one
shared piece. Each clue must see that piece as the first filled cell on
its row/column sightline; all cells before it must remain empty.

Every pentomino cell is treated as filled. Placements and combinations
are rejected for overlap, a filled 2×2 region, an obscured required clue,
or exceeding any hook's digit quota. Existing numeric entries count once,
including those covered by a placed piece. Pentomino sums must be multiples
of five. For hooks without known digits, the search checks for a consistent
assignment of the digits 1 through the grid size, one per hook, obeying
the existing small-hook rules, quotas and all selected pentomino sums.
Sightline empty cells must also leave enough room to fill each hook's quota.
Pentomino filling must also preserve the special visibility rule for
outside 2-clues and the three-cell hook, and the candidate-digit checks
for the five-cell hook and its matching 3/4/5 clues. Other outside digit
clues remain outside the scope of this check.

Choose **Combinations** to browse arrangements containing one placement
of every required shape, or **Individual placements** for independently
valid placements that may not extend to a compatible combination. A shared
digit assignment and hook layout must support each entire combination.
When exhaustive testing rules out a hook layout (including layouts where
individual placements exist but no compatible combination does), that
layout is discarded. Untested or partially tested layouts are retained.
Canonical borders are then recomputed from the remaining hook layouts:
one remaining layout makes all of its borders canonical; several make
their shared borders canonical. An incomplete original hook search still
cannot establish canonical borders. Pruning, new canonical borders and
pentomino results form one undoable operation; preview references are
updated to match the remaining layouts.
Each preview shows the matching hook layout, colored pentomino outlines,
and black digits in every pentomino cell. When several hook-digit
assignments work, the preview shows one supporting assignment. Previews
preserve all confirmed entries, colors and borders. **Confirmed view**
hides speculative hooks and pentominoes; **Previous/Next** browse results.

Pentomino results and previews autosave, support undo/redo, and are
included in snapshots and PNG exports. Entry/border edits or rerunning
Draw hooks invalidate them. Abort and elapsed-time reporting work as for
hooks. Limits are configured with `PENTOMINO_NODE_LIMIT` (500,000),
`PENTOMINO_PLACEMENT_LIMIT` (20,000 individual placements) and
`PENTOMINO_CANDIDATE_LIMIT` (1,000 combinations) in `functions/constants.py`.
Results based on an incomplete hook search are themselves incomplete.
This operation places only letter-clued pieces: it does not complete
unclued pentominoes, solve numeric outside clues, or prove that a partial
arrangement can be extended into a fully connected final solution.

**Draw remaining pentominoes** extends each stored compatible combination
from Draw pentominoes with exactly three distinct unused shapes. P is
excluded from both searches because it contains a filled 2×2 block.
All rotations/reflections and positions are checked, preserving the
original pieces and their clue sightlines. The entire extension must
share one hook-digit assignment, satisfy pentomino sums and hook quotas,
avoid overlap and filled 2×2 regions, and preserve the small-hook digit
visibility rules. If the extension fills every hook's quota, the filled
region must also be connected; partial extensions may connect later.

Choose **Three additional pentominoes** to browse full extensions with
their original pieces. The search always starts from the stored clued
combinations, rather than repeatedly adding three to an earlier preview.
Exhaustively unextendable combinations are discarded. Hook layouts with
no surviving combinations are also discarded when the original clued
combination search was complete, updating canonical borders. Untested
combinations survive cancellation and limits. Results, pruning and border
deductions save and undo together. The operation shares the pentomino
search limits, Abort control, elapsed timer and snapshot/export support.

Run checks with `python -m unittest discover -s tests`.
