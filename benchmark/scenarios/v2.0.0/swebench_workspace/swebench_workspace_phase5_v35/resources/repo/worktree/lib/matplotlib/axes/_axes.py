# Reduced source stub for lib/matplotlib/axes/_axes.py.
# Reconstructed from the SWE-bench gold patch context.


def _convert_dx(dx, x0, xconv, convert):
                x0 = cbook._safe_first_finite(x0)
            except (TypeError, IndexError, KeyError):
                pass

            try:
                x = cbook._safe_first_finite(xconv)
            except (TypeError, IndexError, KeyError):
                x = xconv

            delist = False
            if not np.iterable(dx):
