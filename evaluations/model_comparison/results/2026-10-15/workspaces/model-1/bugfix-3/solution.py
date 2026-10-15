def average(values):
    """Return the arithmetic mean of a non‑empty numeric sequence.

    Parameters
    ----------
    values : iterable
        A sequence of numeric values.  It may be a list, tuple, or any
        iterable that yields numbers.

    Returns
    -------
    float
        The average of the supplied values.

    Raises
    ------
    ValueError
        If ``values`` is empty.
    """
    # Convert to list to allow len() and sum() on arbitrary iterables
    seq = list(values)
    if not seq:
        raise ValueError("Cannot compute average of an empty sequence")
    return sum(seq) / len(seq)
