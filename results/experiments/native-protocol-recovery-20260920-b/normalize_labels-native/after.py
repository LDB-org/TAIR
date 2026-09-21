"""Deduplicate a list of string labels.

Provides :func:`unique_labels`, which returns the first occurrence of each
distinct label, where distinctness is determined by the Unicode casefold of
the label after stripping leading and trailing whitespace. Empty normalized
keys are discarded.
"""


def unique_labels(values):
    """Return the first occurrence of each distinct label, preserving order.

    Parameters
    ----------
    values : list of str
        The input list of labels. It is not mutated.

    Returns
    -------
    list of str
        The original (unmodified) string for the first occurrence of each
        distinct normalized key, in order of first appearance. Labels whose
        normalized key is empty are discarded.

    Notes
    -----
    Distinctness is determined by ``value.strip().casefold()``. The returned
    strings are the original input strings, not the normalized forms.
    """
    seen = set()
    result = []
    for value in values:
        key = value.strip().casefold()
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
