def chunks(values, size):
    if size <= 0:
        raise ValueError("size must be positive")
    if not values:
        return []
    result = []
    for i in range(0, len(values), size):
        chunk = values[i:i + size]
        if len(chunk) < size:
            chunk = chunk + [None] * (size - len(chunk))
        result.append(chunk)
    return result
