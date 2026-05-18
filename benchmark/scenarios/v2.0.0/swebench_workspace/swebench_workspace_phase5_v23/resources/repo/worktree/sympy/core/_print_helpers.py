# Reduced source stub for sympy/core/_print_helpers.py.
# Reconstructed from the SWE-bench gold patch context.


class Printable:
    """
    This also adds support for LaTeX printing in jupyter notebooks.
    """

    # Note, we always use the default ordering (lex) in __str__ and __repr__,
    # regardless of the global setting. See issue 5487.
    def __str__(self):
