# Reduced source stub for sympy/solvers/diophantine.py.
# Reconstructed from the SWE-bench gold patch context.


def diophantine(eq, param=symbols("t", integer=True), syms=None,
            if syms != var:
                dict_sym_index = dict(zip(syms, range(len(syms))))
                return {tuple([t[dict_sym_index[i]] for i in var])
                            for t in diophantine(eq, param)}
        n, d = eq.as_numer_denom()
        if n.is_number:
            return set()
