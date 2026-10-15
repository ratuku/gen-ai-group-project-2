def average(values):
    """Return the arithmetic mean of a non‑empty numeric sequence.

    Args:
        values (Sequence[Number]): A sequence (list, tuple, etc.) of numeric
            values.

    Returns:
        float: The mean of the values.

    Raises:
        ValueError: If *values* is empty.
    """
    if not values:
        raise ValueError("average() arg is an empty sequence")
    return sum(values) / len(values)
