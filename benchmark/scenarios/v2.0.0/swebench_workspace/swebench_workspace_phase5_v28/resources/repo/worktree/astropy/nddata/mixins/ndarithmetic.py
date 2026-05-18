# Reduced source stub for astropy/nddata/mixins/ndarithmetic.py.
# Reconstructed from the SWE-bench gold patch context.


def _arithmetic_mask(self, operation, operand, handle_mask, axis=None, **kwds):
        elif self.mask is None and operand is not None:
            # Make a copy so there is no reference in the result.
            return deepcopy(operand.mask)
        elif operand is None:
            return deepcopy(self.mask)
        else:
            # Now lets calculate the resulting mask (operation enforces copy)
            return handle_mask(self.mask, operand.mask, **kwds)

    def _arithmetic_wcs(self, operation, operand, compare_wcs, **kwds):
