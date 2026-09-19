def summarize(values):
    return {'count': len(set(values)), 'total': sum(values), 'mean': sum(values)/len(values), 'min': min(values), 'max': max(values)}
