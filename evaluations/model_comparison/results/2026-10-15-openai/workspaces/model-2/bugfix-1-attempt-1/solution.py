def average(values):
    if not values:
        raise ValueError('average() arg is an empty sequence')
    return sum(values) / len(values)
