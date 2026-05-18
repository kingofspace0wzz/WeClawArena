import numpy as np

def _cstack(left, right):
    noutp = left.shape[0] + right.shape[0]
    cleft = left
    cright = np.zeros((noutp, right.shape[1]))
    cright[-right.shape[0]:, -right.shape[1]:] = 1
    return np.hstack([cleft, cright])
