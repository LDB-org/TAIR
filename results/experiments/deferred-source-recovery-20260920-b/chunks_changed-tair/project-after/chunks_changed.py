def chunks(values, size):
    if size <= 0:
        raise ValueError("size must be positive")
    if not values:
        return []
    result = []
    for i in range(0, len(values), size):
        chunk = list(values[i:i + size])
        while len(chunk) < size:
            chunk.append(None)
        result.append(chunk)
    return result
