# Reduced source stub for sympy/matrices/common.py.
# Reconstructed from the SWE-bench gold patch context.


def entry(i, j):
                return self[i, j]
            elif pos <= j < pos + other.cols:
                return other[i, j - pos]
            return self[i, j - pos - other.cols]

        return self._new(self.rows, self.cols + other.cols,
                         lambda i, j: entry(i, j))
