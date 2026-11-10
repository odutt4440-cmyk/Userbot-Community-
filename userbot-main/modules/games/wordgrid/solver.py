class GridSolver:
    def __init__(self, grid):
        self.grid = grid
        self.rows = len(grid)
        self.cols = len(grid[0]) if self.rows > 0 else 0
        self.directions = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]

    def solve(self, word):
        word = word.upper()
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] == word[0]:
                    for dr, dc in self.directions:
                        if self._check(word, r, c, dr, dc): return True
        return False

    def _check(self, word, r, c, dr, dc):
        for i in range(len(word)):
            nr, nc = r + i * dr, c + i * dc
            if not (0 <= nr < self.rows and 0 <= nc < self.cols and self.grid[nr][nc] == word[i]):
                return False
        return True
