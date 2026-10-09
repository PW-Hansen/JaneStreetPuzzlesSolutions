"""Shared Tkinter analysis settings dialog."""
import math
from tkinter import messagebox, simpledialog, ttk
from functions.constants import DEFAULT_ANALYSIS_WEIGHTS


class AnalysisWeightsDialog(simpledialog.Dialog):
    def body(self, master):
        self.entries = []
        labels = ('Per nearby conditional', 'Bordering the grid edge',
                  'Per adjacent green cell / in a green cell')
        for row, (label, value) in enumerate(zip(labels, DEFAULT_ANALYSIS_WEIGHTS)):
            ttk.Label(master, text=label).grid(row=row, column=0, sticky='w', padx=8, pady=6)
            entry = ttk.Entry(master, width=12)
            entry.insert(0, value)
            entry.grid(row=row, column=1, padx=8, pady=6)
            self.entries.append(entry)
        return self.entries[0]

    def validate(self):
        try:
            self.weights = tuple(float(entry.get()) for entry in self.entries)
            if any(not math.isfinite(value) or value <= 0 for value in self.weights):
                raise ValueError()
        except ValueError:
            messagebox.showerror('Invalid weights', 'Enter a positive finite number for each weight.', parent=self)
            return False
        return True

    def apply(self):
        self.result = self.weights

