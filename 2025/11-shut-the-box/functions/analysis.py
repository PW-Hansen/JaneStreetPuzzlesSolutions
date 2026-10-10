"""Shared workflow for arrow, number, and region deductions."""
from .arrows import analyze_arrows
from .numbers import propagate_numbers, number_counts
from .regions import propagate_regions, propagate_exterior


def analyze_grid(cells, rows, columns):
    def numbers(boxes, sources, conflicts):
        return propagate_numbers(cells, boxes, sources, rows, columns, conflicts)
    def regions(boxes, sources, conflicts):
        return propagate_regions(boxes, sources, rows, columns, conflicts)
    def exterior(boxes, sources, conflicts):
        return propagate_exterior(boxes, sources, rows, columns, conflicts)
    analysis = analyze_arrows(cells, rows, columns, extra_rules=(numbers, regions, exterior))
    analysis.numbers = number_counts(cells, analysis.boxes, rows, columns)
    return analysis
