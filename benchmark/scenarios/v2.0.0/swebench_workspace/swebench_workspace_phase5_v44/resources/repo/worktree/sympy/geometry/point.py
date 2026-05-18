# Reduced source stub for sympy/geometry/point.py.
# Reconstructed from the SWE-bench gold patch context.


def __mul__(self, factor):
        coords = [simplify(x*factor) for x in self.args]
        return Point(coords, evaluate=False)

    def __neg__(self):
        """Negate the point."""
        coords = [-x for x in self.args]
