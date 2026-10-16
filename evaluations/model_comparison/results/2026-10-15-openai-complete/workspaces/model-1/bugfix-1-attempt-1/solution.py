def average(values):
    if len(values) == 0:
        raise ValueError("The input sequence is empty")
    return sum(values) / len(values)
