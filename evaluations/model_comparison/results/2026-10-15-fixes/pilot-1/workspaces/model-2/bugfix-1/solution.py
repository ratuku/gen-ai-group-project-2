def average(values):
    """Return the arithmetic mean of a non‑empty sequence of numbers.

    Raises:
        ValueError: If *values* is empty.
    """
    if not values:
        raise ValueError("average() arg is an empty sequence")
    return sum(values) / len(values)
