# Reduced source stub for sympy/matrices/sparse.py.
# Reconstructed from the SWE-bench gold patch context.


def col_join(self, other):
        """
        >>> C == A.row_insert(A.rows, Matrix(B))
        True
        """
        if not self:
            return type(self)(other)
        A, B = self, other
        if not A.cols == B.cols:
            raise ShapeError()

def row_join(self, other):
        """
        >>> C == A.col_insert(A.cols, B)
        True
        """
        if not self:
            return type(self)(other)
        A, B = self, other
        if not A.rows == B.rows:
            raise ShapeError()
