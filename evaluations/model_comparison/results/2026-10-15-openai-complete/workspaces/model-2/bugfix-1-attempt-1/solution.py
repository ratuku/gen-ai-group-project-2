def average(values):
    if len(values) == 0:
        raise ValueError('average() arg is an empty sequence')
    return sum(values) / len(values)
