def summarize(values):
    if not values:
        return {'count': 0, 'total': 0, 'mean': None, 'min': None, 'max': None}
    total = sum(values)
    return {
        'count': len(values),
        'total': total,
        'mean': total / len(values),
        'min': min(values),
        'max': max(values),
    }
