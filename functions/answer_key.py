"""Puzzle answer: total neighbor sums over unvisited cells."""


def compute_answer_key(grid):
    for r, row in enumerate(grid["visits"]):
        for c, visit in enumerate(row):
            if visit is not None and grid["scores"][r][c] is None:
                raise ValueError("Every visited cell needs a score to calculate the answer key.")
    answer = 0
    for r, row in enumerate(grid["visits"]):
        for c, visit in enumerate(row):
            if visit is not None:
                continue
            for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if (0 <= nr < grid["rows"] and 0 <= nc < grid["columns"]
                        and grid["visits"][nr][nc] is not None):
                    answer += grid["scores"][nr][nc]
    return answer
