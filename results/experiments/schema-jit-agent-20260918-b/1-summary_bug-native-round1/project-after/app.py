def summarize(values):
    count = len(values)
    if count == 0:
        return {'count': 0, 'total': 0, 'mean': None, 'min': None, 'max': None}
    total = sum(values)
    return {'count': count, 'total': total, 'mean': total / count, 'min': min(values), 'max': max(values)}
