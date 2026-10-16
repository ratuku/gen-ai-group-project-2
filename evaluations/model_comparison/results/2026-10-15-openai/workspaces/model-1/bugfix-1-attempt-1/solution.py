def average(values):
    if not values:
        raise ValueError("Cannot compute the average of an empty sequence")
    return sum(values) / len(values)
