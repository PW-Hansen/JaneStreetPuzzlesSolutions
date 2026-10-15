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
created puzzle is blank. There are no automated deductions or solver
operations in this editor.

Run checks with `python -m unittest discover -s tests`.
