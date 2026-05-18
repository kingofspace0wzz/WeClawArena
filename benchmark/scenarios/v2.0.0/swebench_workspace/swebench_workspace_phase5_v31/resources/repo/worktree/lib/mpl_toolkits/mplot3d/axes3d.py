# Reduced source stub for lib/mpl_toolkits/mplot3d/axes3d.py.
# Reconstructed from the SWE-bench gold patch context.


def apply_aspect(self, position=None):

    @martist.allow_rasterization
    def draw(self, renderer):
        self._unstale_viewLim()

        # draw the background patch
