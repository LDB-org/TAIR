def mean(values):
    values = list(values)
    if not values:
        return None
    return sum(values) / len(values)
