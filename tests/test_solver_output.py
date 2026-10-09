from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

from functions.solver import SolveResult
from functions.solver_output import save_solver_result
from functions.state import Session, new_grid
from solve_puzzle import main


class SolverOutputTests(unittest.TestCase):
    def test_export_uses_shared_renderer_without_changing_session_mode(self):
        s = Session(new_grid("output", 2, 3))
        s.mode = "Tower"
        s.selected = (0, 0)
        before = s.serialize()
        with patch("functions.solver_output.write_session") as write, \
                patch("functions.solver_output.export_png") as export:
            output, png = save_solver_result(s, Path("results/result.json"))
        write.assert_called_once_with(output, s)
        self.assertEqual(png, Path("results/result.png"))
        rendered = export.call_args.args[0]
        self.assertEqual(rendered.mode, "Select")
        self.assertIsNone(rendered.selected)
        self.assertEqual(export.call_args.kwargs["path"], png)
        self.assertEqual(s.serialize(), before)

    def test_outputs_cannot_overwrite_each_other(self):
        s = Session(new_grid("output", 2, 3))
        with patch("functions.solver_output.write_session") as write:
            with self.assertRaises(ValueError):
                save_solver_result(s, "result.json", "result.json")
        write.assert_not_called()

    def test_cli_logs_total_time_and_both_output_paths(self):
        s = Session(new_grid("output", 2, 3))
        result = SolveResult(s, "solved", 7, 1, "Solved.")
        stream = StringIO()
        with patch("solve_puzzle.read_session", return_value=s), \
                patch("solve_puzzle.solve", return_value=result), \
                patch("solve_puzzle.perf_counter", side_effect=[10.0, 12.5]), \
                patch("solve_puzzle.save_solver_result", return_value=(Path("result.json"), Path("result.png"))) as save, \
                redirect_stdout(stream):
            code = main(["output", "--output", "result.json", "--png", "result.png"])
        self.assertEqual(code, 0)
        save.assert_called_once_with(s, Path("result.json"), Path("result.png"))
        self.assertIn("Final state PNG: result.png", stream.getvalue())
        self.assertIn("Total time: 2.50 seconds.", stream.getvalue())

    def test_dry_run_and_failed_search_log_time_without_writing(self):
        s = Session(new_grid("output", 2, 3))
        for status, args, expected in (("solved", ["output", "--dry-run"], 0),
                                       ("failed", ["output"], 1)):
            with self.subTest(status=status):
                stream = StringIO()
                with patch("solve_puzzle.read_session", return_value=s), \
                        patch("solve_puzzle.solve", return_value=SolveResult(s, status, None, 0, status)), \
                        patch("solve_puzzle.perf_counter", side_effect=[10.0, 11.0]), \
                        patch("solve_puzzle.save_solver_result") as save, redirect_stdout(stream):
                    self.assertEqual(main(args), expected)
                save.assert_not_called()
                self.assertIn("Total time: 1.00 seconds.", stream.getvalue())
