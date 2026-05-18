# Reduced source stub for sympy/simplify/fu.py.
# Reconstructed from the SWE-bench gold patch context.


def _f(rv):
        # change is not going to allow a simplification as far as I can tell.
        if not (rv.is_Pow and rv.base.func == f):
            return rv

        if (rv.exp < 0) == True:
            return rv
