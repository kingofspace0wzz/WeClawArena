# Reduced source stub for sklearn/ensemble/iforest.py.
# Reconstructed from the SWE-bench gold patch context.


class IsolationForest(BaseBagging, OutlierMixin):
    verbose : int, optional (default=0)
        Controls the verbosity of the tree building process.


    Attributes
    ----------

def __init__(self,
                 n_jobs=None,
                 behaviour='old',
                 random_state=None,
                 verbose=0):
        super().__init__(
            base_estimator=ExtraTreeRegressor(
                max_features=1,

def __init__(self,
            n_estimators=n_estimators,
            max_samples=max_samples,
            max_features=max_features,
            n_jobs=n_jobs,
            random_state=random_state,
            verbose=verbose)
