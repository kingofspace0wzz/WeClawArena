# Reduced source stub for lib/matplotlib/__init__.py.
# Reconstructed from the SWE-bench gold patch context.


def rc_context(rc=None, fname=None):
    """
    Return a context manager for temporarily changing rcParams.

    Parameters
    ----------
    rc : dict

def rc_context(rc=None, fname=None):
             """
             plt.plot(x, y)  # uses 'print.rc'

    """
    orig = rcParams.copy()
    try:
        if fname:
            rc_file(fname)
