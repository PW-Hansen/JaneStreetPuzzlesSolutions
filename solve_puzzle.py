"""Command-line entry point for the shared checkpoint solver."""

import argparse
from pathlib import Path
from time import perf_counter

from functions.persistence import puzzles, read_session, snapshot_path, working_path, write_session
from functions.solver import solve
from functions.solver_output import save_solver_result
from functions.answer_key import compute_answer_key


def main(argv=None):
    parser = argparse.ArgumentParser(description="Continue checkpoint paths and visit the final tower.")
    parser.add_argument("input", nargs="?", help="Saved-state JSON path or working puzzle name; defaults to the only working puzzle.")
    parser.add_argument("--output", type=Path, help="Output JSON; defaults to the solver_result snapshot for this puzzle.")
    parser.add_argument("--png", type=Path, help="Final-state PNG; defaults to the JSON output path with a .png extension.")
    parser.add_argument("--early-step", type=int, default=3)
    parser.add_argument("--early-end", type=int, default=18)
    parser.add_argument("--first-interval", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true", help="Analyze without writing JSON or PNG output.")
    args = parser.parse_args(argv)
    started = perf_counter()
    try:
        source = args.input
        if source is None:
            names = puzzles()
            if len(names) != 1:
                raise ValueError("Specify a saved-state JSON path or puzzle name.")
            source = names[0]
        path = Path(source)
        session = read_session(path if path.is_file() else working_path(source))
        result = solve(session, args.early_step, args.early_end, args.first_interval,
                       report=lambda message: print(message, flush=True))
        print(result.message)
        if result.status == "failed":
            return 1
        if result.status == "solved":
            print(f"Answer key: {compute_answer_key(result.session.grid)}", flush=True)
        else:
            print("Answer key: undetermined (multiple solutions remain).", flush=True)
        if not args.dry_run:
            output = args.output or snapshot_path(result.session.grid["name"], "solver_result")
            output, png = save_solver_result(result.session, output, args.png)
            print(f"Saved: {output}", flush=True)
            print(f"Final state PNG: {png}", flush=True)
        return 0
    except (OSError, ValueError) as error:
        parser.exit(2, f"Error: {error}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Aborted. No result saved.\n")
    finally:
        print(f"Total time: {perf_counter() - started:.2f} seconds.", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
