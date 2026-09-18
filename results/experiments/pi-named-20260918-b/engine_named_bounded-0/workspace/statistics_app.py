import json


def summarize_numbers(values):
    if not values:
        return {'count': 0, 'total': 0, 'min': None, 'max': None}
    return {
        'count': len(values),
        'total': sum(values),
        'min': min(values),
        'max': max(values),
    }


if __name__ == '__main__':
    print(json.dumps(summarize_numbers([3, -1, 3, 0.5])))

