def chunks(values, size):
    if size <= 0:
        raise ValueError("size must be positive")
    if not values:
        return []
    return [values[i:i + size] for i in range(0, len(values), size)]
