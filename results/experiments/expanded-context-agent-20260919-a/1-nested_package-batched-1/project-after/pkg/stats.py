def moving_average(values, window):
    if window <= 0:
        raise ValueError("window must be positive")
    if len(values) < window:
        return []
    return [sum(values[i:i + window]) / window for i in range(len(values) - window + 1)]
