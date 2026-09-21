import math

import numpy as np


def weld_exact(positions: np.ndarray, decimals: int) -> tuple[np.ndarray, np.ndarray]:
    rounded = np.round(positions, decimals) + 0.0  # + 0.0 folds -0.0 into 0.0
    uniq, inverse = np.unique(rounded, axis=0, return_inverse=True)
    return uniq, inverse.reshape(-1).astype(np.int64)


def axis_quanta(positions: np.ndarray, sig_digits: int) -> np.ndarray:
    max_abs = np.abs(positions).max(axis=0)
    return np.array([10.0 ** (math.ceil(math.log10(max(a, 1e-9))) - sig_digits) for a in max_abs])
