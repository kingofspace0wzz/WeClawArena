# Reduced source stub for sympy/matrices/expressions/matexpr.py.
# Reconstructed from the SWE-bench gold patch context.


def _postprocessor(expr):
                # manipulate them like non-commutative scalars.
                return cls._from_args(nonmatrices + [mat_class(*matrices).doit(deep=False)])

        return mat_class(cls._from_args(nonmatrices), *matrices).doit(deep=False)
    return _postprocessor
