def summarize(values):
    if not values:
        return {'count': 0, 'total': 0, 'mean': None, 'min': None, 'max': None}
    return {'count': len(values), 'total': sum(values), 'mean': sum(values)/len(values), 'min': min(values), 'max': max(values)}
