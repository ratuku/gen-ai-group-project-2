def average(values):
    """Return the arithmetic mean of a non‑empty numeric sequence.

    Parameters
    ----------
    values : Sequence[Number]
        A sequence of numeric values.

    Returns
    -------
    float
        The arithmetic mean of the values.

    Raises
    ------
    ValueError
        If *values* is empty.
    """
    if not values:
        raise ValueError("average() requires at least one value")
    return sum(values) / len(values)
