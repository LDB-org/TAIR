def summarize(values):
    values = list(values)
    count = len(values)
    if count == 0:
        return {
            "count": 0,
            "total": 0,
            "mean": None,
            "minimum": None,
            "maximum": None,
        }
    total = sum(values)
    return {
        "count": count,
        "total": total,
        "mean": total / count,
        "minimum": min(values),
        "maximum": max(values),
    }
