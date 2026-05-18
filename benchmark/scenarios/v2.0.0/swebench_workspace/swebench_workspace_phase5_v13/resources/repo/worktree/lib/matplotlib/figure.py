# Reduced source stub for lib/matplotlib/figure.py.
# Reconstructed from the SWE-bench gold patch context.


def __getstate__(self):
        # Set cached renderer to None -- it can't be pickled.
        state["_cachedRenderer"] = None

        # add version information to the state
        state['__mpl_version__'] = mpl.__version__
