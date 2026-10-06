"""Run the full puzzle's GUI operation sequence without opening a window."""

import argparse
from pathlib import Path
from time import perf_counter

from functions.persistence_functions import read_state, write_state
from functions.solve_functions import solve_sequence


ROOT = Path(__file__).resolve().parent
REGION_SEQUENCE = (12, 13, 14, 15, 16, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1)


def solve(state, log=print):
    return solve_sequence(state, REGION_SEQUENCE, log)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'grids' / 'full_puzzle.json')
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'saved states' / 'full_puzzle' / 'solved-full-puzzle.json')
    args = parser.parse_args()
    started = perf_counter()
    try:
        saved, solutions = solve(read_state(args.input), log=lambda message: print(message, flush=True))
        write_state(args.output, saved)
        print(f'Saved {args.output} ({perf_counter() - started:.2f}s total).', flush=True)
        print(f'Validated complete solutions: {solutions}.', flush=True)
        return 0 if solutions else 1
    except (OSError, ValueError) as error:
        print(f'Could not solve puzzle: {error}', flush=True)
        return 1
    except KeyboardInterrupt:
        print('Stopped. Input grid unchanged.', flush=True)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
