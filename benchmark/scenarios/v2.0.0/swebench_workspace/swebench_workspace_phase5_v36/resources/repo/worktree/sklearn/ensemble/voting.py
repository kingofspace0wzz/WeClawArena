# Reduced source stub for sklearn/ensemble/voting.py.
# Reconstructed from the SWE-bench gold patch context.


def fit(self, X, y, sample_weight=None):

        if sample_weight is not None:
            for name, step in self.estimators:
                if not has_fit_parameter(step, 'sample_weight'):
                    raise ValueError('Underlying estimator \'%s\' does not'
                                     ' support sample weights.' % name)
