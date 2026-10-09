"""Arithmetic lookahead using a worklist of (score, visit, operations, last)."""


class MovementSearch:
    def __init__(self, score, visit, lookahead=3):
        if type(score) is not int:
            raise ValueError("The selected cell needs an integer score.")
        if type(visit) is not int or visit < 0:
            raise ValueError("The selected cell needs a nonnegative visit number.")
        if type(lookahead) is not int or lookahead < 0:
            raise ValueError("Lookahead must be a nonnegative integer.")
        self.max_visit = visit + lookahead
        self.worklist = [(score, visit, "", "")]

    def advance(self):
        """Process one entry; return it only if it has reached max_visit."""
        score, visit, operations, last = self.worklist.pop()
        if visit == self.max_visit:
            return score, visit, operations, last
        next_visit = visit + 1
        self.worklist.append((score + next_visit, next_visit, operations + "+", last))
        if last != "*":
            self.worklist.append((score * next_visit, next_visit, operations + "*", "*"))
        if last != "/" and score % next_visit == 0:
            self.worklist.append((score // next_visit, next_visit, operations + "/", "/"))
        return None
